"""Streamlit UI - fin 量化研究工作站"""
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
pages = ["🏠 Home", "📋 Runs", "📦 庫存股", "📊 Coverage", "📁 Reports", "⚙️ Run Control"]
page = st.sidebar.radio("導覽", pages)
st.sidebar.caption(f"v7 Phase 3 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")


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
    st.title("資料覆蓋率")
    _, _, coverage_crud = get_crud()
    snapshots = coverage_crud.latest(limit=30)
    if snapshots:
        import pandas as pd
        df = pd.DataFrame(snapshots)
        if "trade_date" in df.columns:
            df = df.sort_values("trade_date")
            st.line_chart(df.set_index("trade_date")[["revenue_coverage", "financial_coverage"]])
        st.dataframe(df, use_container_width=True)
    else:
        st.info("尚無 coverage 記錄")


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
