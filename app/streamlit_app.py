import streamlit as st
import pandas as pd

from tma.config import DICT_PATH, RATE_LIMIT_PER_MIN, FUZZY_THRESHOLD
from tma.matching import load_dict, clean_and_match_from_raw, aggregate_id_quantity
from tma.http_api import session_for_requests, fetch_first10
from tma.rate_limit import TokenBucket
from tma.analytics import analyze_market
from tma.io_utils import to_csv_bytes, apply_display_formatting

st.set_page_config(page_title="Kzon's Torn Market Analyzer", layout="wide")

st.markdown(
    "<h1 style='margin-bottom:0.4rem'>Kzon's Torn Market Analyzer</h1>"
    "<p style='margin:0 0 1rem 0'>Paste the full text of your Torn Inventory window and enter your <b>public</b> API key.</p>",
    unsafe_allow_html=True,
)

left, right = st.columns([1.2, 1], vertical_alignment="top")

with left:
    with st.form("input_form", clear_on_submit=False):
        st.write("**Inventory text**")
        st.caption("Copy everything you see in your inventory window (all lines) and paste it below. We remove UI actions and floating numbers automatically.")
        raw = st.text_area(
            label="Inventory text",
            height=200,
            placeholder="Paste your full inventory window text here…",
            label_visibility="collapsed",
        )
        st.caption("Enter your *public* API key (used server-side for read-only itemmarket calls).")
        api_key = st.text_input(
            label="API key",
            type="password",
            placeholder="Enter your public API key…",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Run")

with right:
    st.markdown(
        """
        <div style="border:1px solid rgba(0,0,0,0.08); border-radius:8px; padding:14px 16px;">
          <h4 style="margin:0 0 0.6rem 0;">What this app does</h4>
          <ul style="margin:0; padding-left:1.1rem; line-height:1.45;">
            <li><b>Parses & cleans</b> your pasted inventory text (ignores UI phrases and floating numbers).</li>
            <li><b>Fuzzy-matches</b> item names against a local dictionary (threshold fixed at 80) and counts quantities.</li>
            <li><b>Queries Torn</b> <code>itemmarket</code> (first 10 sell listings) for each matched item using your <i>public</i> API key.</li>
            <li><b>Computes KPIs</b>: min/max price, mean price of first 20 units (ceil), depth cost, price spread & volatility.</li>
            <li><b>Suggests sale prices</b> (based on 20-unit mean, 5% market fee with ceil) and provides CSV downloads.</li>
          </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

if submitted:
    if not DICT_PATH.exists():
        st.error("Dictionary CSV not found (data/torn_item_dictionary.csv)."); st.stop()
    if not raw or not raw.strip():
        st.error("Inventory text is empty. Please paste the full inventory window text."); st.stop()
    if not api_key.strip():
        st.error("API key required."); st.stop()

    with st.spinner("Cleaning & matching…"):
        dict_map = load_dict(DICT_PATH)
        clean_rows = clean_and_match_from_raw(raw, dict_map, threshold=FUZZY_THRESHOLD)
        df_clean = pd.DataFrame(clean_rows)
        if df_clean.empty:
            st.warning("No matches found after cleaning. Check the pasted text."); st.stop()
        st.success(f"Parsed {len(df_clean)} segments")
        st.dataframe(df_clean, use_container_width=True)

    agg = aggregate_id_quantity(clean_rows)
    if not agg:
        st.warning("No valid item IDs after cleaning."); st.stop()

    with st.spinner("Fetching market (10 lowest sell listings per item)…"):
        sess = session_for_requests(); bucket = TokenBucket(RATE_LIMIT_PER_MIN)
        out_rows = [fetch_first10(sess, bucket, api_key, iid, qty) for iid, qty in agg]
        df_market = pd.DataFrame(out_rows)
        st.success(f"Fetched {len(df_market)} items")
        st.dataframe(df_market.head(30), use_container_width=True)

    with st.spinner("Computing KPIs & suggestions…"):
        kpis, sugg = analyze_market(df_market)
        st.subheader("Market KPIs per item")
        st.dataframe(apply_display_formatting(kpis).sort_values("item_name").reset_index(drop=True), use_container_width=True)

        st.subheader("Sale suggestions")
        st.dataframe(apply_display_formatting(sugg).sort_values("item_name").reset_index(drop=True), use_container_width=True)

        st.download_button("Download clean_data_id.csv", data=to_csv_bytes(df_clean), file_name="clean_data_id.csv", mime="text/csv")
        st.download_button("Download market_list.csv", data=to_csv_bytes(df_market), file_name="market_list.csv", mime="text/csv")
        st.download_button("Download market_kpis.csv", data=to_csv_bytes(kpis), file_name="market_kpis.csv", mime="text/csv")
        st.download_button("Download market_suggestions.csv", data=to_csv_bytes(sugg), file_name="market_suggestions.csv", mime="text/csv")