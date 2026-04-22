"""Streamlit UI - fin 量化研究工作站"""
import os
import subprocess
from datetime import datetime

import streamlit as st

st.set_page_config(page_title="fin | 量化研究工作站", layout="wide")

# ---- DB client (lazy, cached) ----
@st.cache_resource
def get_db():
    from src.database.client import SupabaseClient
    return SupabaseClient()


@st.cache_resource
def get_crud():
    from src.database.crud import PipelineRunCRUD, CandidateCRUD, CoverageCRUD
    db = get_db()
    return PipelineRunCRUD(db), CandidateCRUD(db), CoverageCRUD(db)


# ---- Sidebar nav ----
pages = ["🏠 Home", "📋 Runs", "📦 庫存股", "📊 Coverage", "🤖 模型", "📁 Reports", "⚙️ Run Control"]
page = st.sidebar.radio("導覽", pages)
st.sidebar.caption(f"v7 Phase 5d | {datetime.now().strftime('%Y-%m-%d %H:%M')}")


# ================================================================== #
# Home
# ================================================================== #
if page == "🏠 Home":
    st.title("fin 量化研究工作站")
    run_crud, candidate_crud, _ = get_crud()
    db = get_db()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("最新 Run")
        runs = run_crud.latest(limit=1)
        if runs:
            r = runs[0]
            st.metric("Run ID", r.get("run_id", "—"))
            st.metric("交易日", r.get("trade_date", "—"))
            st.metric("狀態", r.get("status", "—"))
        else:
            st.info("尚無 run 記錄")

    with col2:
        st.subheader("最新候選標的")
        if runs:
            trade_date_str = runs[0].get("trade_date")
            if trade_date_str:
                from datetime import date
                try:
                    td = date.fromisoformat(str(trade_date_str)[:10])
                    candidates = candidate_crud.latest_by_date(td)
                    eligible = [c for c in candidates if c.get("list_type") == "eligible"]
                    watch = [c for c in candidates if c.get("list_type") == "watch"]
                    st.write(f"**Consider（{len(eligible)} 檔）**")
                    if eligible:
                        import pandas as pd
                        st.dataframe(pd.DataFrame(eligible)[["instrument", "score"]], use_container_width=True)
                    st.write(f"**Watch（{len(watch)} 檔）**")
                    if watch:
                        import pandas as pd
                        st.dataframe(pd.DataFrame(watch)[["instrument", "score"]], use_container_width=True)
                except Exception:
                    st.info("無法載入候選標的")
        else:
            st.info("尚無候選標的")


# ================================================================== #
# Runs
# ================================================================== #
elif page == "📋 Runs":
    st.title("近期 Run 記錄")
    run_crud, _, _ = get_crud()
    runs = run_crud.latest(limit=20)
    if runs:
        import pandas as pd
        df = pd.DataFrame(runs)
        cols = [c for c in ["run_id", "trade_date", "mode", "status", "started_at", "ended_at"] if c in df.columns]
        st.dataframe(df[cols], use_container_width=True)
    else:
        st.info("尚無 run 記錄（mock mode）")


# ================================================================== #
# 庫存股
# ================================================================== #
elif page == "📦 庫存股":
    import yaml
    import pandas as pd
    from pathlib import Path

    st.title("庫存股管理")

    profile = os.getenv("DEFAULT_PROFILE", "user_a")
    portfolio_path = Path(f"config/portfolio_{profile}.yaml")

    def _load_portfolio(path: Path) -> dict:
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return data.get("holdings", {})
        return {}

    def _save_portfolio(path: Path, holdings: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump({"holdings": holdings}, f, allow_unicode=True, default_flow_style=False)

    holdings = _load_portfolio(portfolio_path)

    if holdings:
        rows = [
            {"代號": code, "名稱": h.get("name", ""), "類型": h.get("asset_type", ""),
             "股數": h.get("shares", 0), "均成本": h.get("avg_cost", 0.0),
             "備註": h.get("note", "")}
            for code, h in holdings.items()
        ]
        df = pd.DataFrame(rows)
        edited = st.data_editor(df, use_container_width=True, num_rows="dynamic",
                                key="portfolio_editor")

        col_save, col_msg = st.columns([1, 3])
        with col_save:
            if st.button("💾 儲存變更", use_container_width=True):
                new_holdings = {}
                for _, row in edited.iterrows():
                    code = str(row["代號"]).strip()
                    if not code:
                        continue
                    new_holdings[code] = {
                        "name": row["名稱"],
                        "asset_type": row["類型"],
                        "shares": int(row["股數"]) if pd.notna(row["股數"]) else 0,
                        "avg_cost": float(row["均成本"]) if pd.notna(row["均成本"]) else 0.0,
                        "note": row["備註"],
                    }
                _save_portfolio(portfolio_path, new_holdings)
                st.success(f"已儲存 {len(new_holdings)} 筆持股到 {portfolio_path}")
    else:
        st.info(f"尚無持股資料（{portfolio_path}）")
        if st.button("建立空白庫存"):
            _save_portfolio(portfolio_path, {})
            st.rerun()


# ================================================================== #
# Coverage
# ================================================================== #
elif page == "📊 Coverage":
    import json
    import pandas as pd
    from pathlib import Path as _Path

    st.title("資料覆蓋率")
    _, _, coverage_crud = get_crud()
    snapshots = coverage_crud.latest(limit=30)

    # ---- Retrain gate status (load from latest run artifact) ----
    retrain_decision = None
    runs_dir = _Path(os.getenv("CACHE_DIR", "workspace/hotdata")).parent / "runs"
    if runs_dir.exists():
        run_dirs = sorted(runs_dir.iterdir(), reverse=True)
        for rd in run_dirs[:5]:
            rp = rd / "retrain_decision.json"
            if rp.exists():
                try:
                    retrain_decision = json.loads(rp.read_text())
                except Exception:
                    pass
                break

    col1, col2, col3 = st.columns(3)
    if snapshots:
        latest = snapshots[0]
        col1.metric("月營收覆蓋率", f"{latest.get('revenue_coverage', 0):.1%}")
        col2.metric("財報覆蓋率", f"{latest.get('financial_coverage', 0):.1%}")
    if retrain_decision:
        status = "🔴 需要 Retrain" if retrain_decision.get("should_retrain") else "🟢 不需要 Retrain"
        col3.metric("Retrain Gate", status)
        with st.expander("Retrain 決策詳情"):
            st.json(retrain_decision)

    # ---- 30-day coverage trend ----
    if snapshots:
        df = pd.DataFrame(snapshots)
        if "trade_date" in df.columns:
            df = df.sort_values("trade_date")
            st.subheader("30 日覆蓋率趨勢")
            chart_cols = [c for c in ["revenue_coverage", "financial_coverage"] if c in df.columns]
            if chart_cols:
                st.line_chart(df.set_index("trade_date")[chart_cols])

        # ---- Missing critical stocks ----
        latest_missing = snapshots[0].get("missing_critical", [])
        if latest_missing:
            st.subheader(f"⚠️ 缺件標的（{len(latest_missing)} 檔）")
            st.dataframe(pd.DataFrame({"stock_id": latest_missing}), use_container_width=True)
        else:
            st.success("無缺件標的")
    else:
        st.info("尚無 coverage 記錄（執行 run_daily.py 後才會產生）")


# ================================================================== #
# 模型 (Model)
# ================================================================== #
elif page == "🤖 模型":
    import json as _json
    import pandas as pd

    st.title("模型管理")

    @st.cache_resource
    def get_registry():
        from src.registry.model_registry import ModelRegistry
        return ModelRegistry(db=get_db())

    registry = get_registry()

    # ---- Champion ----
    st.subheader("Champion 模型")
    profile_key = os.getenv("DEFAULT_PROFILE", "user_a")
    family = st.selectbox("模型族", ["lgbm_binary"], key="model_family")
    champion = registry.get_champion(family)

    if champion:
        col1, col2, col3 = st.columns(3)
        col1.metric("Model ID", champion.get("model_id", "—"))
        col2.metric("Feature Set", champion.get("feature_set_version", "—"))
        metrics = champion.get("metrics") or {}
        col3.metric("AUC", f"{metrics.get('auc', '—')}")
        with st.expander("完整 metrics"):
            st.json(metrics)
    else:
        st.info("尚無 champion 模型（請先執行訓練流程）")

    st.divider()

    # ---- Per-user LightGBM params ----
    st.subheader("訓練參數（個人化）")
    st.caption("調整後儲存，下次 quant-trainer 服務啟動時生效。")

    param_key = f"lgbm_params_{profile_key}"
    defaults = {"n_estimators": 100, "num_leaves": 31, "learning_rate": 0.05, "min_child_samples": 5}
    if param_key not in st.session_state:
        st.session_state[param_key] = defaults.copy()
    p = st.session_state[param_key]

    c1, c2, c3, c4 = st.columns(4)
    p["n_estimators"]      = c1.number_input("n_estimators",      min_value=10,  max_value=1000, value=int(p["n_estimators"]),      step=10)
    p["num_leaves"]        = c2.number_input("num_leaves",        min_value=4,   max_value=256,  value=int(p["num_leaves"]),         step=4)
    p["learning_rate"]     = c3.number_input("learning_rate",     min_value=0.001, max_value=0.5, value=float(p["learning_rate"]),  step=0.005, format="%.3f")
    p["min_child_samples"] = c4.number_input("min_child_samples", min_value=1,   max_value=100,  value=int(p["min_child_samples"]), step=1)
    if st.button("💾 儲存訓練參數"):
        st.success(f"已儲存參數至 session（profile: {profile_key}）")

    st.divider()

    # ---- Candidates ----
    st.subheader("Candidate 模型")
    candidates = registry.list_candidates(family)
    if candidates:
        cdf = pd.DataFrame(candidates)
        show_cols = [c for c in ["model_id", "feature_set_version", "metrics", "created_at"] if c in cdf.columns]
        st.dataframe(cdf[show_cols], use_container_width=True)

        st.subheader("Promote Candidate")
        cand_ids = [c["model_id"] for c in candidates]
        promote_id = st.selectbox("選擇 Candidate", cand_ids, key="promote_select")
        promote_reason = st.text_input("原因", placeholder="e.g. AUC improvement 0.72 → 0.78")
        if st.button("⬆️ Promote 為 Champion", type="primary"):
            ok = registry.promote(promote_id, reason=promote_reason)
            if ok:
                st.success(f"已將 {promote_id} 提升為 champion！請重新整理頁面。")
                st.cache_resource.clear()
            else:
                st.error("Promote 失敗，請確認 model_id 存在。")
    else:
        st.info("目前無 candidate 模型")

    st.divider()

    # ---- SHAP top features ----
    st.subheader("SHAP 特徵重要度")
    runs_dir_str = os.path.join(os.getenv("CACHE_DIR", "workspace/hotdata"), "..", "runs")
    import pathlib as _pl
    runs_dir = _pl.Path(runs_dir_str).resolve()
    shap_data = None
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
        with st.expander("原始數值"):
            st.dataframe(shap_df, use_container_width=True)
    else:
        st.info("尚無 SHAP 摘要（執行含 champion 模型的 run_daily 後產生）")


# ================================================================== #
# Reports
# ================================================================== #
elif page == "📁 Reports":
    st.title("報告索引")
    db = get_db()
    reports = db.select("daily_reports_index", limit=20)
    if reports:
        import pandas as pd
        st.dataframe(pd.DataFrame(reports), use_container_width=True)
    else:
        st.info("尚無報告記錄")


# ================================================================== #
# Run Control
# ================================================================== #
elif page == "⚙️ Run Control":
    st.title("手動觸發")
    st.warning("以下操作會啟動 Docker 容器執行分析，請確認環境已就緒。")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("▶ 執行每日分析", use_container_width=True):
            with st.spinner("執行中..."):
                try:
                    r = subprocess.run(
                        ["docker", "compose", "-f", "compose/docker-compose.yml",
                         "--profile", "jobs", "run", "--rm", "quant-daily"],
                        capture_output=True, text=True, timeout=300,
                    )
                    if r.returncode == 0:
                        st.success("完成")
                        st.code(r.stdout[-2000:])
                    else:
                        st.error("失敗")
                        st.code(r.stderr[-2000:])
                except Exception as e:
                    st.error(f"錯誤：{e}")

    with col2:
        if st.button("🔄 同步市場資料", use_container_width=True):
            with st.spinner("同步中..."):
                try:
                    r = subprocess.run(
                        ["docker", "compose", "-f", "compose/docker-compose.yml",
                         "--profile", "jobs", "run", "--rm", "quant-sync"],
                        capture_output=True, text=True, timeout=600,
                    )
                    st.success("完成") if r.returncode == 0 else st.error("失敗")
                    st.code((r.stdout or r.stderr)[-2000:])
                except Exception as e:
                    st.error(f"錯誤：{e}")

    with col3:
        if st.button("📥 同步財報", use_container_width=True):
            with st.spinner("同步中（可能需數分鐘）..."):
                try:
                    r = subprocess.run(
                        ["docker", "compose", "-f", "compose/docker-compose.yml",
                         "--profile", "jobs", "run", "--rm", "quant-financials"],
                        capture_output=True, text=True, timeout=1800,
                    )
                    st.success("完成") if r.returncode == 0 else st.error("失敗")
                    st.code((r.stdout or r.stderr)[-2000:])
                except Exception as e:
                    st.error(f"錯誤：{e}")
