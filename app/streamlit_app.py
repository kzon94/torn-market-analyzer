import streamlit as st
import pandas as pd
import sys
from pathlib import Path

# ---------------------------------------------------------------------
# PATHS & IMPORTS
# ---------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tma.config import DICT_PATH, RATE_LIMIT_PER_MIN, FUZZY_THRESHOLD
from tma.matching import load_dict, clean_and_match_from_raw, aggregate_id_quantity
from tma.http_api import session_for_requests, fetch_100
from tma.rate_limit import TokenBucket
from tma.io_utils import to_csv_bytes
from tma.market_enrichment import (
    wide_to_long,
    enrich_all_items,
    build_summary_from_enriched,
)


# ---------------------------------------------------------------------
# APP CONFIG
# ---------------------------------------------------------------------

st.set_page_config(page_title="Kzon's Torn Market Analyzer", layout="centered")


# ---------------------------------------------------------------------
# SESSION STATE (PER-USER API KEY)
# ---------------------------------------------------------------------

if "api_key" not in st.session_state:
    st.session_state["api_key"] = ""


# ---------------------------------------------------------------------
# GLOBAL STYLES
# ---------------------------------------------------------------------

st.markdown(
    """
    <style>
      .block-container {
        max-width: 900px;
        margin: 0 auto;
        padding-top: 2rem;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------------

st.title("Kzon's Torn Market Analyzer")

st.markdown(
    """
    <p style="margin-top:-12px; font-size:0.95rem; color:#666;">
        Under development by 
        <a href="https://www.torn.com/profiles.php?XID=3968250" target="_blank" style="text-decoration:none;">
            Kzon [3968250]
        </a>. Coffee tips are always appreciated :)
    </p>
    """,
    unsafe_allow_html=True,
)

with st.expander("How this app works"):
    st.markdown(
        """
        - Copy the list of items from the **Add Listing** section of the Item Market.
        - Paste it in the text box below; prices and untradable/equipped items are ignored.
        - The app calls the Torn `itemmarket` API with your **public** key (read-only, rate-limited).
        - It fetches up to the first 100 listings per item and computes **anchor-aware price suggestions**:
            - **Fast-sell**: price to move stock quickly.
            - **Fair**: robust market median after removing outliers and price walls.
            - **Greedy**: upper “optimistic” price based on clean upper quantiles.
        - Your API key can be stored in your browser session for convenience and is **not** shared anywhere.
        """
    )


# ---------------------------------------------------------------------
# INPUT FORM
# ---------------------------------------------------------------------

submitted = False
raw = ""
api_key = ""
remember = True

with st.form("input_form", clear_on_submit=False):
    st.subheader("Item Market listings")

    st.markdown(
        "[Quick access to your listings](https://www.torn.com/page.php?sid=ItemMarket#/addListing)",
        unsafe_allow_html=False,
    )

    raw = st.text_area(
        "Paste your items",
        height=220,
        placeholder="Paste your full Add Listing items text here…",
    )

    api_key = st.text_input(
        "Enter your public Torn API key",
        value=st.session_state["api_key"],
        key="api_key_input",
    )

    remember = st.checkbox(
        "Remember API key during this session",
        value=True,
        help="Keeps your API key stored in this browser session only.",
    )

    submitted = st.form_submit_button("Run")


# ---------------------------------------------------------------------
# PIPELINE
# ---------------------------------------------------------------------

if submitted:
    # Basic validation
    if not DICT_PATH.exists():
        st.error("Dictionary CSV not found (data/torn_item_dictionary.csv).")
        st.stop()
    if not raw or not raw.strip():
        st.error("Listings text is empty.")
        st.stop()
    if not api_key.strip():
        st.error("API key required.")
        st.stop()

    # Update per-session API key (only for this user/session)
    if remember:
        st.session_state["api_key"] = api_key
    else:
        st.session_state["api_key"] = ""

    # 1) Cleaning & matching
    with st.spinner("Cleaning & matching…"):
        dict_map = load_dict(DICT_PATH)
        clean_rows = clean_and_match_from_raw(raw, dict_map, threshold=FUZZY_THRESHOLD)
        df_clean = pd.DataFrame(clean_rows)
        if df_clean.empty:
            st.warning("No matches found.")
            st.stop()

        wanted_cols = ["input_segment", "cleaned_name", "normalized_key", "quantity", "id", "confidence"]
        df_parsed_view = df_clean.reindex(columns=wanted_cols)
        st.success(f"Parsed {len(df_clean)} segments")
        st.dataframe(df_parsed_view, width="container")

    # 2) Aggregate quantities per item_id
    agg = aggregate_id_quantity(clean_rows)
    if not agg:
        st.warning("No valid item IDs after cleaning.")
        st.stop()

    # 3) Fetch market data (wide format: price_1…price_100, amount_1…amount_100)
    with st.spinner("Fetching market data…"):
        sess = session_for_requests()
        bucket = TokenBucket(RATE_LIMIT_PER_MIN)

        out_rows = [fetch_100(sess, bucket, api_key, iid, qty) for iid, qty in agg]
        df_market = pd.DataFrame(out_rows)

        # Normalize numeric columns for safety
        for i in range(1, 101):
            pcol = f"price_{i}"
            acol = f"amount_{i}"
            if pcol in df_market.columns:
                df_market[pcol] = pd.to_numeric(df_market[pcol], errors="coerce")
            if acol in df_market.columns:
                df_market[acol] = pd.to_numeric(df_market[acol], errors="coerce")

        for c in ["average_price", "my_quantity", "item_id"]:
            if c in df_market.columns:
                df_market[c] = pd.to_numeric(df_market[c], errors="coerce")

        st.success(f"Fetched {len(df_market)} items")
        st.subheader("Raw market data (wide format)")
        st.dataframe(df_market.head(30), width="container")

    # 4) Anchor-aware price suggestions
    with st.spinner("Computing anchor-aware price suggestions…"):
        # 4.1 Convert wide → long (one row per listing)
        df_long = wide_to_long(df_market)

        if df_long.empty:
            st.warning("No valid listings found in the market data.")
            st.stop()

        # 4.2 Enrich listings (stats, depth, suspected anchors)
        df_enriched = enrich_all_items(df_long)

        # 4.3 Build per-item summary (fast / fair / greedy + diagnostics)
        df_summary = build_summary_from_enriched(df_enriched)

        # Sort by item name for display
        df_summary_sorted = df_summary.sort_values("item_name").reset_index(drop=True)

        st.subheader("Sale suggestions (anchor-aware)")
        sugg_view = df_summary_sorted[
            [
                "item_id",
                "item_name",
                "my_quantity",
                "num_listings",
                "num_suspected_anchors",
                "fast_sell_price",
                "fair_price",
                "greedy_price",
                "clean_q1_price",
                "clean_median_price",
                "clean_q3_price",
            ]
        ]
        st.dataframe(sugg_view, width="container")

        # 5) Downloads
        st.subheader("Downloads")

        st.download_button(
            "Download clean_data_id.csv",
            data=to_csv_bytes(df_clean),
            file_name="clean_data_id.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download market_list.csv (wide)",
            data=to_csv_bytes(df_market),
            file_name="market_list.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download market_list_long.csv",
            data=to_csv_bytes(df_long),
            file_name="market_list_long.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download market_list_enriched.csv",
            data=to_csv_bytes(df_enriched),
            file_name="market_list_enriched.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download market_suggestions.csv",
            data=to_csv_bytes(df_summary_sorted),
            file_name="market_suggestions.csv",
            mime="text/csv",
        )
