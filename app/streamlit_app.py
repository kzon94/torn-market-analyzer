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


# ---------- Style ----------
IMG_HEIGHT_PX = 320
st.markdown(
    f"""
    <style>
      .tma-panel {{
        border:1px solid rgba(0,0,0,0.08);
        border-radius:8px;
        padding:14px 16px;
      }}
      .tma-img {{
        width:100%;
        height:{IMG_HEIGHT_PX}px;
        object-fit:contain;
        border:1px solid rgba(0,0,0,0.06);
        border-radius:8px;
        margin-top:12px;
        background: #fff;
      }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------- Header ----------
st.markdown(
    "<h1 style='margin-bottom:0.4rem'>Kzon's Torn Market Analyzer</h1>"
    "<p style='margin:0 0 1rem 0'>Paste the full text of your Torn Inventory window and enter your <b>public</b> API key.</p>",
    unsafe_allow_html=True,
)

left, right = st.columns([1.2, 1], vertical_alignment="top")

with left:
    with st.container():
        st.markdown("<div class='tma-panel'>", unsafe_allow_html=True)
        with st.form("input_form", clear_on_submit=False):
            st.write("**Inventory text**")
            st.caption("Copy everything you see in your inventory window (all lines) and paste it below.")
            raw = st.text_area(
                label="Inventory text",
                height=200,
                placeholder="Paste your full inventory window text here…",
                label_visibility="collapsed",
            )

            cache = _api_key_cache()
            st.caption("Enter your *public* API key (stored locally in cache).")
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

        # Espaciador para igualar la altura total con la imagen de la derecha
        st.markdown(f"<div style='height:{IMG_HEIGHT_PX}px'></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

with right:
    with st.container():
        st.markdown("<div class='tma-panel'>", unsafe_allow_html=True)
        st.markdown(
            """
            <h4 style="margin:0 0 0.6rem 0;">What this app does</h4>
            <ul style="margin:0; padding-left:1.1rem; line-height:1.45;">
              <li><b>Parses & cleans</b> your pasted inventory text.</li>
              <li><b>Fuzzy-matches</b> item names against a local dictionary (threshold fixed at 80).</li>
              <li><b>Queries Torn</b> <code>itemmarket</code> for each matched item using your public API key.</li>
              <li><b>Stores your API key locally in cache</b> for convenience — not shared anywhere.</li>
              <li><b>Computes KPIs</b>: min/max price, mean price, depth cost, price spread & volatility.</li>
              <li><b>Suggests sale prices</b> and provides CSV downloads.</li>
            </ul>
            """,
            unsafe_allow_html=True,
        )

        # Imagen colocada debajo de la caja de la derecha (dentro del mismo panel)
        # Si prefieres fuera del panel, mueve este bloque después del </div>.
        st.markdown(
            "<img src='inventory.png' alt='inventory.png' class='tma-img' />",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)


# ---------- Pipeline ----------
if submitted:
    if not DICT_PATH.exists():
        st.error("Dictionary CSV not found (data/torn_item_dictionary.csv)."); st.stop()
    if not raw or not raw.strip():
        st.error("Inventory text is empty."); st.stop()
    if not api_key.strip():
        st.error("API key required."); st.stop()

    if remember:
        cache["value"] = api_key

    with st.spinner("Cleaning & matching…"):
        dict_map = load_dict(DICT_PATH)
        clean_rows = clean_and_match_from_raw(raw, dict_map, threshold=FUZZY_THRESHOLD)
        df_clean = pd.DataFrame(clean_rows)
        if df_clean.empty:
            st.warning("No matches found."); st.stop()

        wanted_cols = ["input_segment", "normalized_key", "quantity", "id"]
        df_parsed_view = df_clean.reindex(columns=wanted_cols)
        st.success(f"Parsed {len(df_clean)} segments")
        st.dataframe(df_parsed_view, width='stretch')

    agg = aggregate_id_quantity(clean_rows)
    if not agg:
        st.warning("No valid item IDs after cleaning."); st.stop()

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
        st.dataframe(df_market.head(30), width='stretch')

    with st.spinner("Computing KPIs & suggestions…"):
        kpis, sugg = analyze_market(df_market)
        kpis_view = kpis.drop(columns=["item_type", "units_used_for_20u"], errors="ignore")

        st.subheader("Market KPIs per item")
        st.dataframe(
            apply_display_formatting(kpis_view).sort_values("item_name").reset_index(drop=True),
            width='stretch'
        )

        st.subheader("Sale suggestions")
        st.dataframe(
            apply_display_formatting(sugg).sort_values("item_name").reset_index(drop=True),
            width='stretch'
        )

        st.download_button(
            "Download clean_data_id.csv",
            data=to_csv_bytes(df_clean),
            file_name="clean_data_id.csv",
            mime="text/csv"
        )
        st.download_button(
            "Download market_list.csv",
            data=to_csv_bytes(df_market),
            file_name="market_list.csv",
            mime="text/csv"
        )
        st.download_button(
            "Download market_kpis.csv",
            data=to_csv_bytes(kpis),
            file_name="market_kpis.csv",
            mime="text/csv"
        )
        st.download_button(
            "Download market_suggestions.csv",
            data=to_csv_bytes(sugg),
            file_name="market_suggestions.csv",
            mime="text/csv"
        )
