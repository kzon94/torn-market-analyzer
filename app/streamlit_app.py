import streamlit as st
import pandas as pd
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tma.config import DICT_PATH, RATE_LIMIT_PER_MIN, FUZZY_THRESHOLD
from tma.matching import load_dict, clean_and_match_from_raw, aggregate_id_quantity
from tma.http_api import session_for_requests, fetch_first10
from tma.rate_limit import TokenBucket
from tma.analytics import analyze_market
from tma.io_utils import to_csv_bytes, apply_display_formatting


# ---------- App config ----------
st.set_page_config(page_title="Kzon's Torn Market Analyzer", layout="centered")


# ---------- Cache (API key) ----------
@st.cache_resource(show_spinner=False)
def _api_key_cache():
    return {"value": ""}


# ---------- Global styles (solo centrar) ----------
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


# ---------- Header ----------
st.title("Kzon's Torn Market Analyzer")

with st.expander("How this app works", icon="❓"):
    st.markdown(
        """
        - Copy the list of items from the **Add Listing** section of the Item Market.
        - Paste it in the text box below; prices and untradable/equipped items are ignored.
        - The app calls the Torn `itemmarket` API with your **public** key (read-only, rate-limited).
        - It computes market KPIs and suggests listing prices based on the first 20 units.
        - Your API key is cached locally for convenience and is **not** shared anywhere.
        """
    )

cache = _api_key_cache()
submitted = False
raw = ""
api_key = ""
remember = True


# ---------- Input form ----------
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
        value=cache.get("value", ""),
    )

    remember = st.checkbox(
        "Remember API key in cache",
        value=True,
        help="Stores your API key locally in cache (not shared).",
    )

    submitted = st.form_submit_button("Run")


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

    # 1) Cleaning & matching
    with st.spinner("Cleaning & matching…"):
        dict_map = load_dict(DICT_PATH)
        clean_rows = clean_and_match_from_raw(raw, dict_map, threshold=FUZZY_THRESHOLD)
        df_clean = pd.DataFrame(clean_rows)
        if df_clean.empty:
            st.warning("No matches found.")
            st.stop()

        wanted_cols = ["input_segment", "normalized_key", "quantity", "id"]
        df_parsed_view = df_clean.reindex(columns=wanted_cols)
        st.success(f"Parsed {len(df_clean)} segments")
        st.dataframe(df_parsed_view, use_container_width=True)

    # 2) Aggregate quantities
    agg = aggregate_id_quantity(clean_rows)
    if not agg:
        st.warning("No valid item IDs after cleaning.")
        st.stop()

    # 3) Fetch market data
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
        st.dataframe(df_market.head(30), use_container_width=True)

    # 4) KPIs & suggestions
    with st.spinner("Computing KPIs & suggestions…"):
        kpis, sugg = analyze_market(df_market)
        kpis_view = kpis.drop(columns=["item_type", "units_used_for_20u"], errors="ignore")

        st.subheader("Market KPIs per item")
        st.dataframe(
            apply_display_formatting(kpis_view).sort_values("item_name").reset_index(drop=True),
            use_container_width=True,
        )

        st.subheader("Sale suggestions")
        st.dataframe(
            apply_display_formatting(sugg).sort_values("item_name").reset_index(drop=True),
            use_container_width=True,
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



