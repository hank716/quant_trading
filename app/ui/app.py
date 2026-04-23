"""Streamlit UI — fin 投資助理 (Phase 10 post-cutover)."""
from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime, date
from pathlib import Path
from typing import Any

import streamlit as st
import yaml

st.set_page_config(page_title="fin | 投資助理", layout="wide")

# ================================================================== #
# Auth
# ================================================================== #
auth_path = Path("config/auth_users.yaml")
if auth_path.exists():
    try:
        import streamlit_authenticator as stauth
        auth_cfg = yaml.safe_load(auth_path.read_text())
        authenticator = stauth.Authenticate(
            auth_cfg["credentials"],
            auth_cfg["cookie"]["name"],
            auth_cfg["cookie"]["key"],
            auth_cfg["cookie"]["expiry_days"],
        )
        name, auth_status, username = authenticator.login("登入 fin", "main")
        if not auth_status:
            if auth_status is False:
                st.error("帳號或密碼錯誤")
            st.stop()
        profile = auth_cfg["credentials"]["usernames"][username].get("profile", "user_a")
        authenticator.logout("登出", "sidebar")
        st.sidebar.write(f"登入：{name}")
    except Exception as _auth_exc:
        st.warning(f"驗證模組載入失敗（{_auth_exc}）— 使用 Dev 模式")
        profile = "user_a"
        username = "dev"
else:
    profile = "user_a"
    username = "dev"

# ================================================================== #
# Sidebar nav
# ================================================================== #
PAGES = ["今日報告", "我的持股", "策略設定", "模型狀態", "回測分析", "監控 & 告警"]
page = st.sidebar.radio("導覽", PAGES)
st.sidebar.caption(f"Phase 10 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")


# ================================================================== #
# Cached resources
# ================================================================== #
@st.cache_resource
def _get_db():
    from src.database.client import SupabaseClient
    return SupabaseClient()


@st.cache_resource
def _get_crud():
    from src.database.crud import PipelineRunCRUD, CandidateCRUD, CoverageCRUD
    db = _get_db()
    return PipelineRunCRUD(db), CandidateCRUD(db), CoverageCRUD(db)


@st.cache_data(ttl=300)
def _search_mlflow_runs(experiment_ids: list | None = None, max_results: int = 20) -> "pd.DataFrame":
    import mlflow
    import pandas as pd
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "file:workspace/mlruns"))
    try:
        runs = mlflow.search_runs(
            experiment_ids=experiment_ids,
            order_by=["start_time DESC"],
            max_results=max_results,
        )
        return runs if not runs.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _load_profile_cfg(p: str) -> dict:
    path = Path(f"config/profiles/{p}.yaml")
    if path.exists():
        return yaml.safe_load(path.read_text()) or {}
    return {}


def _load_strategy_cfg() -> dict:
    path = Path("config/strategy_1m.yaml")
    if path.exists():
        return yaml.safe_load(path.read_text()) or {}
    return {}


def _write_yaml_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml_str = yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(yaml_str)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ================================================================== #
# Page 1 — 今日報告
# ================================================================== #
if page == "今日報告":
    st.title("今日報告")

    runs_df = _search_mlflow_runs(max_results=1)
    today_str = date.today().isoformat()

    if not runs_df.empty:
        latest = runs_df.iloc[0]
        run_id = latest.get("run_id", "")

        col1, col2, col3, col4 = st.columns(4)
        metric_cols = {
            "IC": col1, "Rank IC": col2, "Sharpe": col3, "MDD": col4,
        }
        for key, col in metric_cols.items():
            m_key = f"metrics.{key}"
            val = latest.get(m_key, None)
            col.metric(key, f"{val:.4f}" if val is not None else "—")

        st.caption(f"Run ID: `{run_id[:8]}…`  |  開始: {latest.get('start_time', '—')}")
        st.divider()

        candidates: list[dict] = []
        try:
            from qlib.workflow import R
            from qlib_ext import init_tw_qlib
            init_tw_qlib()
            recorder = R.get_recorder(run_id=run_id, experiment_name="workflow")
            pred = recorder.load_object("pred.pkl")
            if pred is not None:
                import pandas as pd
                if isinstance(pred.index, pd.MultiIndex):
                    latest_date = pred.index.get_level_values("datetime").max()
                    pred = pred.xs(latest_date, level="datetime")
                if isinstance(pred, pd.DataFrame):
                    pred = pred.iloc[:, 0]
                for sym, score in pred.nlargest(20).items():
                    candidates.append({"rank": len(candidates) + 1, "ticker": sym, "score": float(score), "thesis": ""})
        except Exception as _exc:
            st.warning(f"MLflow/Qlib 暫無資料：{_exc}")

        if candidates:
            st.subheader(f"Top-{len(candidates)} 候選標的")
            import pandas as pd
            for c in candidates:
                with st.expander(f"{c['rank']}. {c['ticker']}  score={c['score']:.4f}"):
                    st.write(c.get("thesis") or "（無說明）")
                    if st.button("加入持股", key=f"add_{c['ticker']}"):
                        try:
                            from app.control.portfolio_editor import add_holding
                            add_holding(profile, c["ticker"])
                            st.success(f"已加入 {c['ticker']}")
                        except Exception as exc:
                            st.error(f"加入失敗：{exc}")
        else:
            st.info("今日無候選標的資料")
    else:
        st.warning("MLflow 暫無資料")
        if st.button("手動觸發 Daily Run"):
            with st.spinner("執行中…"):
                try:
                    subprocess.run(
                        ["python", "-m", "app.orchestration.run_daily",
                         "--profile", profile, "--skip-sync"],
                        timeout=300,
                        check=False,
                    )
                    st.success("已觸發，請稍後重新整理頁面")
                    st.cache_data.clear()
                except Exception as exc:
                    st.error(f"觸發失敗：{exc}")


# ================================================================== #
# Page 2 — 我的持股
# ================================================================== #
elif page == "我的持股":
    import pandas as pd
    from app.control.portfolio_editor import load_portfolio, save_portfolio, add_holding, remove_holding

    st.title("我的持股")

    holdings = load_portfolio(profile)
    st.caption(f"共 {len(holdings)} 筆持股（profile: {profile}）")

    COLS = ["ticker", "name", "asset_type", "shares", "avg_cost", "note"]

    if holdings:
        df = pd.DataFrame(holdings, columns=COLS)
        for col in COLS:
            if col not in df.columns:
                df[col] = "" if col in ("name", "asset_type", "note") else 0
    else:
        df = pd.DataFrame(columns=COLS)

    edited = st.data_editor(
        df,
        use_container_width=True,
        num_rows="dynamic",
        key="portfolio_editor",
    )

    col_save, col_del = st.columns([1, 3])
    with col_save:
        if st.button("儲存", use_container_width=True):
            try:
                rows = edited.to_dict("records")
                rows = [r for r in rows if str(r.get("ticker", "")).strip()]
                save_portfolio(profile, rows)
                st.success(f"已儲存 {len(rows)} 筆")
                st.rerun()
            except Exception as exc:
                st.error(f"儲存失敗：{exc}")

    st.divider()
    st.subheader("新增持股")
    with st.form("add_holding_form"):
        c1, c2, c3 = st.columns(3)
        new_ticker = c1.text_input("股票代號")
        new_name = c2.text_input("名稱")
        new_note = c3.text_input("備註")
        submitted = st.form_submit_button("加入")
        if submitted and new_ticker.strip():
            try:
                add_holding(profile, new_ticker.strip(), name=new_name, note=new_note)
                st.success(f"已加入 {new_ticker}")
                st.rerun()
            except Exception as exc:
                st.error(f"加入失敗：{exc}")


# ================================================================== #
# Page 3 — 策略設定
# ================================================================== #
elif page == "策略設定":
    st.title("策略設定")
    strategy = _load_strategy_cfg()
    profile_cfg = _load_profile_cfg(profile)

    with st.form("strategy_form"):
        st.subheader("硬規則")
        hr = strategy.get("hard_rules", {})
        c1, c2 = st.columns(2)
        min_price = c1.number_input("min_price", value=float(hr.get("min_price", 1)), step=1.0)
        min_listing_days = c2.number_input("min_listing_days", value=int(hr.get("min_listing_days", 7)), step=1)
        exclude_kw_raw = st.text_area(
            "exclude_name_keywords（逗號分隔）",
            value=", ".join(hr.get("exclude_name_keywords", [])),
        )

        st.subheader("價格規則")
        pr = strategy.get("price_rules", {})
        c3, c4, c5 = st.columns(3)
        ma_window = c3.number_input("ma_window", value=int(pr.get("ma_window", 20)), step=1)
        lookback_days = c4.number_input("lookback_days", value=int(pr.get("lookback_days", 20)), step=1)
        min_return = c5.number_input(
            "min_return_over_lookback", value=float(pr.get("min_return_over_lookback", -0.18)), step=0.01, format="%.2f"
        )

        st.subheader("決策參數")
        dec = strategy.get("decision", {})
        c6, c7 = st.columns(2)
        max_consider = c6.number_input("max_consider", value=int(dec.get("max_consider", 5)), step=1)
        max_watch = c7.number_input("max_watch", value=int(dec.get("max_watch", 10)), step=1)

        st.subheader("Profile 設定")
        selector_opts = ["rule_based", "groq", "openai_compatible"]
        sel_idx = selector_opts.index(profile_cfg.get("selector_provider", "rule_based")) if profile_cfg.get("selector_provider", "rule_based") in selector_opts else 0
        selector_provider = st.selectbox("selector_provider", selector_opts, index=sel_idx)

        llm_opts = ["rule_based", "groq", "openai_compatible"]
        llm_idx = llm_opts.index(profile_cfg.get("llm_provider", "rule_based")) if profile_cfg.get("llm_provider", "rule_based") in llm_opts else 0
        llm_provider = st.selectbox("llm_provider", llm_opts, index=llm_idx)

        col_save, col_reset = st.columns(2)
        submitted = col_save.form_submit_button("儲存設定", type="primary")
        reset = col_reset.form_submit_button("還原預設")

    if submitted:
        try:
            kw_list = [k.strip() for k in exclude_kw_raw.split(",") if k.strip()]
            strategy.setdefault("hard_rules", {}).update(
                {"min_price": min_price, "min_listing_days": int(min_listing_days), "exclude_name_keywords": kw_list}
            )
            strategy.setdefault("price_rules", {}).update(
                {"ma_window": int(ma_window), "lookback_days": int(lookback_days), "min_return_over_lookback": min_return}
            )
            strategy.setdefault("decision", {}).update(
                {"max_consider": int(max_consider), "max_watch": int(max_watch)}
            )
            _write_yaml_atomic(Path("config/strategy_1m.yaml"), strategy)

            profile_cfg["selector_provider"] = selector_provider
            profile_cfg["llm_provider"] = llm_provider
            _write_yaml_atomic(Path(f"config/profiles/{profile}.yaml"), profile_cfg)
            st.success("設定已儲存")
        except Exception as exc:
            st.error(f"儲存失敗：{exc}")

    if reset:
        st.rerun()


# ================================================================== #
# Page 4 — 模型狀態
# ================================================================== #
elif page == "模型狀態":
    import json as _json
    import pandas as pd

    st.title("模型狀態")

    family = st.selectbox("模型族", ["lgbm_binary", "lgbm_alpha"], key="model_family")

    st.subheader("Champion 模型")
    champion = None
    try:
        from app.control.champion import get_champion
        champion = get_champion(family)
    except Exception as exc:
        st.warning(f"Champion 查詢失敗：{exc}")

    if champion:
        run_id = champion.get("run_id", "")
        metrics = champion.get("metrics", {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Run ID", run_id[:8] if run_id else "—")
        c2.metric("IC", f"{metrics.get('IC', metrics.get('ic', '—'))}")
        c3.metric("Sharpe", f"{metrics.get('Sharpe', metrics.get('sharpe', '—'))}")
        c4.metric("MDD", f"{metrics.get('MDD', metrics.get('mdd', '—'))}")
        with st.expander("完整 metrics"):
            st.json(metrics)
    else:
        st.info("尚無 champion 模型")

    st.subheader("SHAP 特徵重要度")
    shap_data = None
    runs_dir = Path(os.getenv("CACHE_DIR", "workspace/hotdata")).parent / "runs"
    if runs_dir.exists():
        for rd in sorted(runs_dir.iterdir(), reverse=True)[:10]:
            sp = rd / "shap_summary.json"
            if sp.exists():
                try:
                    shap_data = _json.loads(sp.read_text())
                    st.caption(f"來源：{sp}")
                    break
                except Exception:
                    pass

    if shap_data and shap_data.get("top_features"):
        top = shap_data["top_features"]
        shap_df = pd.DataFrame(top).set_index("feature")
        st.bar_chart(shap_df["mean_abs_shap"])
    else:
        st.info("尚無 SHAP 摘要（執行含 champion 模型的 run_daily 後產生）")

    st.divider()
    st.subheader("Candidate 模型")
    candidates: list[dict] = []
    try:
        from app.control.champion import list_candidates
        candidates = list_candidates(family)
    except Exception as exc:
        st.warning(f"候選模型查詢失敗：{exc}")

    if candidates:
        cdf = pd.DataFrame(candidates)
        show_cols = [c for c in ["run_id", "metrics"] if c in cdf.columns]
        st.dataframe(cdf[show_cols], use_container_width=True)

        st.subheader("Promote Candidate")
        cand_ids = [c["run_id"] for c in candidates]
        promote_id = st.selectbox("選擇 Run", cand_ids, key="promote_select")
        promote_reason = st.text_input("原因", placeholder="e.g. IC improvement")
        if st.button("Promote 為 Champion", type="primary"):
            try:
                from app.control.champion import promote
                promote(promote_id, family, reason=promote_reason)
                st.success(f"已將 {promote_id[:8]} 提升為 champion")
                st.cache_data.clear()
            except Exception as exc:
                st.error(f"Promote 失敗：{exc}")
    else:
        st.info("目前無 candidate 模型")

    st.divider()
    if st.button("觸發 Retrain"):
        try:
            subprocess.Popen(
                ["python", "-m", "app.orchestration.run_training",
                 "--workflow", "qlib_ext/workflows/daily_lgbm.yaml"],
            )
            st.info("已在背景啟動 retrain，請稍後至 MLflow 查看進度")
        except Exception as exc:
            st.error(f"觸發失敗：{exc}")


# ================================================================== #
# Page 5 — 回測分析
# ================================================================== #
elif page == "回測分析":
    import pandas as pd

    st.title("回測分析")

    c1, c2 = st.columns(2)
    start_date = c1.date_input("開始日期", value=date(date.today().year, 1, 1))
    end_date = c2.date_input("結束日期", value=date.today())

    runs_df = _search_mlflow_runs(max_results=50)

    if runs_df.empty:
        st.warning("MLflow 暫無資料")
    else:
        if "start_time" in runs_df.columns:
            try:
                runs_df["start_date"] = pd.to_datetime(runs_df["start_time"]).dt.date
                mask = (runs_df["start_date"] >= start_date) & (runs_df["start_date"] <= end_date)
                filtered = runs_df[mask].copy()
            except Exception:
                filtered = runs_df.copy()
        else:
            filtered = runs_df.copy()

        metric_display = ["IC", "Rank IC", "Sharpe", "MDD"]
        metric_cols_present = [f"metrics.{m}" for m in metric_display if f"metrics.{m}" in filtered.columns]

        if not filtered.empty and metric_cols_present:
            latest = filtered.iloc[0]
            cols = st.columns(len(metric_display))
            for i, key in enumerate(metric_display):
                val = latest.get(f"metrics.{key}", None)
                cols[i].metric(key, f"{val:.4f}" if val is not None else "—")

        st.subheader("多 Run 比較")
        if not filtered.empty and "run_id" in filtered.columns:
            run_options = filtered["run_id"].tolist()
            selected_runs = st.multiselect(
                "選擇 Run（最多 5）",
                options=run_options,
                default=run_options[:min(3, len(run_options))],
                format_func=lambda x: x[:8],
            )
            if selected_runs:
                compare_df = filtered[filtered["run_id"].isin(selected_runs)][
                    ["run_id"] + [c for c in metric_cols_present]
                ].copy()
                compare_df.columns = [c.replace("metrics.", "") for c in compare_df.columns]
                compare_df["run_id"] = compare_df["run_id"].str[:8]
                st.dataframe(compare_df, use_container_width=True)
        else:
            st.info("選定日期範圍內無 MLflow run")

        st.subheader("回測圖表")
        try:
            import mlflow
            mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "file:workspace/mlruns"))
            if not filtered.empty:
                first_run_id = filtered.iloc[0]["run_id"]
                client = mlflow.tracking.MlflowClient()
                artifacts = client.list_artifacts(first_run_id)
                png_arts = [a for a in artifacts if a.path.endswith(".png")]
                if png_arts:
                    art_path = client.download_artifacts(first_run_id, png_arts[0].path)
                    st.image(art_path)
                else:
                    st.info("此 Run 無圖表 artifact")
        except Exception as exc:
            st.info(f"圖表載入失敗：{exc}")


# ================================================================== #
# Page 6 — 監控 & 告警
# ================================================================== #
elif page == "監控 & 告警":
    import pandas as pd

    st.title("監控 & 告警")

    st.subheader("資料健康度")
    try:
        from src.monitoring.coverage_checker import CoverageChecker
        checker = CoverageChecker()
        coverage = checker.check()
        cov_cols = st.columns(len(coverage) if coverage else 1)
        for i, (field, pct) in enumerate(coverage.items()):
            cov_cols[i].metric(field, f"{pct:.1%}")
    except Exception as exc:
        st.warning(f"資料覆蓋率無法取得：{exc}")

    st.subheader("告警閾值設定（僅顯示）")
    c1, c2 = st.columns(2)
    c1.number_input("Coverage 最低閾值", value=0.8, step=0.05, format="%.2f", disabled=True)
    c2.number_input("MDD 警戒值", value=-0.15, step=0.01, format="%.2f", disabled=True)

    st.divider()
    st.subheader("Pipeline 狀態")
    try:
        run_crud, _, _ = _get_crud()
        recent_runs = run_crud.latest(limit=10)
        if recent_runs:
            rdf = pd.DataFrame(recent_runs)
            show_cols = [c for c in ["run_id", "status", "trade_date", "started_at", "ended_at"] if c in rdf.columns]
            st.dataframe(rdf[show_cols], use_container_width=True)
        else:
            st.info("尚無 pipeline run 記錄")
    except Exception as exc:
        st.warning(f"Supabase 無法連線：{exc}")

    st.divider()
    st.subheader("Discord 推播")
    last_sent = st.session_state.get("last_discord_send")
    st.write(f"最後推播時間：{last_sent or '未推播'}")

    if st.button("測試 Discord 推播"):
        try:
            from app.notify.discord_notifier import QlibDiscordNotifier
            profile_cfg = _load_profile_cfg(profile)
            discord_cfg = profile_cfg.get("discord", {})
            notifier = QlibDiscordNotifier(discord_cfg)
            result = notifier.send(f"[fin] 測試推播 {datetime.now().isoformat()}")
            if result.get("status") == "ok":
                st.success("推播成功")
                st.session_state["last_discord_send"] = datetime.now().isoformat()
            else:
                st.warning(f"推播結果：{result}")
        except Exception as exc:
            st.error(f"推播失敗：{exc}")


# ================================================================== #
# Sidebar — System
# ================================================================== #
with st.sidebar.expander("系統"):
    if st.button("手動 Sync 資料", use_container_width=True):
        try:
            subprocess.Popen(
                ["python", "-m", "app.orchestration.sync_qlib_data", "--lookback-days", "5"],
            )
            st.info("Sync 已在背景啟動")
        except Exception as exc:
            st.error(f"Sync 失敗：{exc}")

    if st.button("手動執行 Daily Run", use_container_width=True):
        try:
            subprocess.Popen(
                ["python", "-m", "app.orchestration.run_daily",
                 "--profile", profile, "--skip-sync"],
            )
            st.session_state["last_run_triggered"] = datetime.now().isoformat()
            st.info("Daily Run 已在背景啟動")
        except Exception as exc:
            st.error(f"觸發失敗：{exc}")

    last_run = st.session_state.get("last_run_triggered")
    if last_run:
        st.caption(f"最後 run 時間：{last_run}")

    st.write("服務健康")

    pipeline_ok = True
    st.write("Pipeline: " + ("🟢" if pipeline_ok else "🔴"))

    db_ok = False
    try:
        _get_db()
        db_ok = True
    except Exception:
        pass
    st.write("DB: " + ("🟢" if db_ok else "🔴"))

    pcloud_ok = None
    try:
        from src.storage.pcloud_client import PCloudClient
        token = os.getenv("PCLOUD_TOKEN")
        pcloud_ok = bool(token)
    except Exception:
        pass
    if pcloud_ok is None:
        st.write("pCloud: 🔴")
    elif pcloud_ok:
        st.write("pCloud: 🟢")
    else:
        st.write("pCloud: 🟡 (未設定 token)")
