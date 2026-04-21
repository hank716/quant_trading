"""Streamlit UI 入口 - Phase 0 骨架版"""
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="fin | 量化研究工作站", layout="wide")

st.title("🏗️ fin 量化研究工作站")
st.caption(f"v7 Phase 0 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")

st.info("系統啟動中，Phase 0 骨架版。後續 Phase 會接入 Supabase 狀態。")

with st.sidebar:
    st.header("狀態")
    st.metric("Phase", "0")
    st.metric("最新交易日", "尚未載入")
