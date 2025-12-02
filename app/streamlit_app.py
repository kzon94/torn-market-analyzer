import sys
from pathlib import Path

import pandas as pd
import streamlit as st

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
from tma.market_enrichment import (
    wide_to_long,
    enrich_all_items,
    build_summary_from_enriched,
)

# ---------------------------------------------------------------------
# APP CONFIG
# ---------------------------------------------------------------------

st.set_page_config(page_title="Kzon's Torn Market Analyzer", layout="centered")

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
        - Paste it below; prices and untradable/equipped tags are ignored.
        - The app calls the Torn `itemmarket` endpoint with your **public** API key.
        - Up to the first 100 listings per item are loaded and cleaned.
        - Using those listings, the app computes fast / fair / greedy prices that try to ignore obvious anchors and meme walls.
        """
    )

# ---------------------------------------------------------------------
# INPUT FORM
# ---------------------------------------------------------------------

submitted = False
raw = ""
api_key = ""

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

    submitted = st.form_submit_button("Run")

# ---------------------------------------------------------------------
# PIPELINE
# ---------------------------------------------------------------------

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

    st.session_state["api_key"] = api_key

    # 1) Cleaning & matching
    with st.spinner("Cleaning & matching…"):
        dict_map = load_dict(DICT_PATH)
        clean_rows = clean_and_match_from_raw(raw, dict_map, threshold=FUZZY_THRESHOLD)
        df_clean = pd.DataFrame(clean_rows)
        if df_clean.empty:
            st.warning("No matches found.")
            st.stop()

        parsed_cols = [
            "input_segment",
            "cleaned_name",
            "normalized_key",
            "quantity",
            "id",
        ]
        df_parsed_view = df_clean.reindex(columns=parsed_cols)

    # 2) Aggregate quantities per item_id
    agg = aggregate_id_quantity(clean_rows)
    if not agg:
        st.warning("No valid item IDs after cleaning.")
        st.stop()

    # 3) Fetch market data (wide format)
    with st.spinner("Fetching market data…"):
        sess = session_for_requests()
        bucket = TokenBucket(RATE_LIMIT_PER_MIN)

        out_rows = [fetch_100(sess, bucket, api_key, iid, qty) for iid, qty in agg]
        df_market = pd.DataFrame(out_rows)

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

    # 4) Anchor-aware price suggestions
    with st.spinner("Computing anchor-aware price suggestions…"):
        df_long = wide_to_long(df_market)

        if df_long.empty:
            st.warning("No valid listings found in the market data.")
            st.stop()

        df_enriched = enrich_all_items(df_long)
        df_summary = build_summary_from_enriched(df_enriched)
        df_summary_sorted = df_summary.sort_values("item_name").reset_index(drop=True)

    # -----------------------------------------------------------------
    # MAIN PRICE OVERVIEW (USER-FRIENDLY)
    # -----------------------------------------------------------------

    st.subheader("Price overview")

    overview = df_summary_sorted[
        [
            "item_name",
            "my_quantity",
            "fast_sell_price",
            "fair_price",
            "greedy_price",
        ]
    ].copy()

    overview = overview.rename(
        columns={
            "item_name": "Item",
            "my_quantity": "My quantity",
            "fast_sell_price": "Fast-sell price",
            "fair_price": "Fair price",
            "greedy_price": "Greedy price",
        }
    )

    st.dataframe(overview, width="stretch")

    with st.expander("How are prices calculated?"):
        st.markdown(
            """
            **1. Clean order book**

            - For each item, up to 100 listings are loaded: price + quantity.
            - Listings are sorted by price and cumulative quantity is tracked to understand depth.
            - Volume is also aggregated by exact price level.

            **2. Robust center and spread**

            - A volume-weighted median and quartiles (Q1, Q3) are computed.
            - A robust spread (MAD – median absolute deviation) is used to detect extreme prices via robust z-scores.

            **3. Suspected anchors**

            - Markets are tagged as normal or thin/exclusive depending on volume and dominance of a single price level.
            - In normal markets, we flag listings with very large |z|, shallow depth and small volume as suspected anchors.
            - In thin markets, only very high prices with low volume are flagged.

            **4. Suggested prices**

            - Suspected anchors are removed before pricing (unless that would remove everything).
            - **Fair price**: clean median (volume-weighted in normal markets, per-listing in thin ones).
            - **Greedy price**: clean Q3 (upper quartile) of prices.
            - **Fast-sell price**:
              - Thin markets: around the 3rd cheapest clean listing.
              - Unit-style markets: around the N-th cheapest clean listing.
              - Bulk markets: first price where cumulative clean volume reaches a target number of units.
            """
        )

    # -----------------------------------------------------------------
    # DETAILED TABLES (EXPANDERS)
    # -----------------------------------------------------------------

    with st.expander("Parsed segments"):
        st.dataframe(df_parsed_view, width="stretch")

    with st.expander("Raw market data"):
        st.dataframe(df_market, width="stretch")

    with st.expander("Detailed pricing diagnostics"):
        st.dataframe(df_summary_sorted, width="stretch")
