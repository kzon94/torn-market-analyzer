import streamlit as st
import pandas as pd

from tma.config import DICT_PATH, RATE_LIMIT_PER_MIN, FUZZY_THRESHOLD
from tma.matching import load_dict, clean_and_match_from_raw, aggregate_id_quantity
from tma.http_api import session_for_requests, fetch_first10
from tma.rate_limit import TokenBucket
from tma.analytics import analyze_market
from tma.io_utils import to_csv_bytes, apply_display_formatting


# ---------- App config ----------
st.set_page_config(page_title="Kzon's Torn Market Analyzer", layout="wide")


# ---------- Cache (API key) ----------
@st.cache_resource(show_spinner=False)
def _api_key_cache():
    return {"value": ""}


# ---------- Global styles ----------
st.markdown(
    """
    <style>
      .tma-center-container {
        max-width: 750px;           /* ~50% of screen */
        margin: 0 auto;
      }
      .tma-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        margin-bottom: 0.75rem;
      }
      .tma-title-block {
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
      }
      .tma-tooltip {
        position: relative;
        display: inline-block;
        cursor: help;
      }
      .tma-tooltip-icon {
        width: 22px;
        height: 22px;
        border-radius: 50%;
        border: 1px solid rgba(0,0,0,0.18);
        background: rgba(250,250,250,0.95);
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 600;
        font-size: 0.85rem;
        color: #444;
      }
      .tma-tooltip-content {
        visibility: hidden;
        opacity: 0;
        width: 360px;
        max-width: 80vw;
        background: #111;
        color: #fff;
        text-align: left;
        padding: 10px 12px;
        border-radius: 8px;
        position: absolute;
        z-index: 10;
        top: 130%;
        right: 0;
        font-size: 0.85rem;
        line-height: 1.4;
        transition: opacity 0.15s ease-in-out;
      }
      .tma-tooltip-content ul {
        padding-left: 1.1rem;
        margin: 0.2rem 0 0 0;
      }
      .tma-tooltip-content li {
        margin-bottom: 0.15rem;
      }
      .tma-tooltip:hover .tma-tooltip-content {
        visibility: visible;
        opacity: 1;
      }
      .tma-panel {
        border: 1px solid rgba(0,0,0,0.08);
        border-radius: 10px;
        padding: 16px 18px 18px 18px;
        background: rgba(255,255,255,0.9);
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------- Layout: center content (~50% width) ----------
left_spacer, center_col, right_spacer = st.columns([1, 2, 1])

submitted = False
raw = ""
api_key = ""
remember = True
cache = _api_key_cache()

with center_col:
    st.markdown("<div class='tma-center-container'>", unsafe_allow_html=True)

    # Header with title + "See how I work:" + tooltip
    st.markdown(
        """
        <div class="tma-header">
          <div class="tma-title-block">
            <h1 style="margin:0 0 0.15rem 0;">Kzon's Torn Market Analyzer</h1>
          </div>

          <div style="display:flex; align-items:center; gap:0.4rem;">
            <span style="font-size:0.92rem; color:#333;">See how I work:</span>
            <div class="tma-tooltip">
              <div class="tma-tooltip-icon">?</div>
              <div class="tma-tooltip-content">
                <div><b>How this app works</b></div>
                <ul>
                  <li>Copy the list of items from the <i>Add Listing</i> section of the Item Market and paste it here.</li>
                  <li>The app parses item names and quantities, ignoring prices and untradable / equipped items.</li>
                  <li>It calls the Torn <code>itemmarket</code> API with your public key (rate-limited, read-only).</li>
                  <li>It computes market KPIs and suggests listing prices based on the first 20 units and fee structure.</li>
                  <li>Your API key is cached locally for convenience and is not shared anywhere.</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div class='tma-panel'>", unsafe_allow_html=True)

    with st.form("input_form", clear_on_submit=False):
        st.write("**Item Market listings**")
    
        st.markdown(
            '[Quick access to your items](https://www.torn.com/page.php?sid=ItemMarket#/addListing)',
            unsafe_allow_html=False,
        )
    
        raw = st.text_area(
            label="Listings text",
            height=220,
            placeholder="Paste your full Add Listing items text here…",
            label_visibility="collapsed",
        )
    
        api_key = st.text_input(
            label="API key",
            value=cache.get("value", ""),
            placeholder="Enter your public API key…",
            label_visibility="collapsed",
            key="api_key",
        )

        remember = st.checkbox(
            "Remember API key in cache",
            value=True,
            help="Stores your API key locally in cache (not shared).",
        )

        submitted = st.form_submit_button("Run")

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ---------- Pipeline ----------
if submitted:
    if not DICT_PATH.exists():
        st.error("Dictionary CSV not found (data/torn_item_dictionary.csv).")
        st.stop()
    if not raw or not raw.strip():
        st.error("Listings text is empty.")
        st.stop()
    if not api_key.strip():
        st.error("API key required.")
        st.stop()

    if remember:
        cache["value"] = api_key

    with st.spinner("Cleaning & matching…"):
        dict_map = load_dict(DICT_PATH)
        clean_rows = clean_and_match_from_raw(raw, dict_map, threshold=FUZZY_THRESHOLD)
        df_clean = pd.DataFrame(clean_rows)
        if df_clean.empty():
            st.warning("No matches found.")
            st.stop()

        wanted_cols = ["input_segment", "normalized_key", "quantity", "id"]
        df_parsed_view = df_clean.reindex(columns=wanted_cols)
        st.success(f"Parsed {len(df_clean)} segments")
        st.dataframe(df_parsed_view, width="stretch")

    agg = aggregate_id_quantity(clean_rows)
    if not agg:
        st.warning("No valid item IDs after cleaning.")
        st.stop()

    with st.spinner("Fetching market data…"):
        sess = session_for_requests()
        bucket = TokenBucket(RATE_LIMIT_PER_MIN)
        out_rows = [fetch_first10(sess, bucket, api_key, iid, qty) for iid, qty in agg]
        df_market = pd.DataFrame(out_rows)

        for i in range(1, 11):
            pcol = f"price_{i}"
            acol = f"amount_{i}"
            if pcol in df_market.columns:
                df_market[pcol] = pd.to_numeric(df_market[pcol], errors="coerce").astype("Int64")
            if acol in df_market.columns:
                df_market[acol] = pd.to_numeric(df_market[acol], errors="coerce").astype("Int64")
        for c in ["average_price", "my_quantity", "item_id"]:
            if c in df_market.columns:
                df_market[c] = pd.to_numeric(df_market[c], errors="coerce").astype("Int64")

        st.success(f"Fetched {len(df_market)} items")
        st.dataframe(df_market.head(30), width="stretch")

    with st.spinner("Computing KPIs & suggestions…"):
        kpis, sugg = analyze_market(df_market)
        kpis_view = kpis.drop(columns=["item_type", "units_used_for_20u"], errors="ignore")

        st.subheader("Market KPIs per item")
        st.dataframe(
            apply_display_formatting(kpis_view).sort_values("item_name").reset_index(drop=True),
            width="stretch",
        )

        st.subheader("Sale suggestions")
        st.dataframe(
            apply_display_formatting(sugg).sort_values("item_name").reset_index(drop=True),
            width="stretch",
        )

        st.download_button(
            "Download clean_data_id.csv",
            data=to_csv_bytes(df_clean),
            file_name="clean_data_id.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download market_list.csv",
            data=to_csv_bytes(df_market),
            file_name="market_list.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download market_kpis.csv",
            data=to_csv_bytes(kpis),
            file_name="market_kpis.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download market_suggestions.csv",
            data=to_csv_bytes(sugg),
            file_name="market_suggestions.csv",
            mime="text/csv",
        )


