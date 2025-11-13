with center_col:
    with st.container():
        st.markdown("<div class='tma-center-container'>", unsafe_allow_html=True)

        # Header limpio sin crear bloques fantasma
        st.markdown(
            """
            <div class="tma-header">
              <div class="tma-title-block">
                <div style="font-size: 2rem; font-weight: 700; margin-bottom: 0.1rem;">
                    Kzon's Torn Market Analyzer
                </div>
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

        # FORMULARIO
        with st.form("input_form"):
            st.write("**Item Market listings**")

            st.markdown(
                '[Quick access to your items](https://www.torn.com/page.php?sid=ItemMarket#/addListing)',
                unsafe_allow_html=False,
            )

            raw = st.text_area(
                placeholder="Paste your full Add Listing items text here…",
                label="Listings text",
                height=220,
                label_visibility="collapsed"
            )

            api_key = st.text_input(
                placeholder="Enter your public API key…",
                label="API key",
                value=cache.get("value", ""),
                label_visibility="collapsed",
                key="api_key"
            )

            remember = st.checkbox(
                "Remember API key in cache",
                value=True,
                help="Stores your API key locally in cache (not shared).",
            )

            submitted = st.form_submit_button("Run")

        st.markdown("</div></div>", unsafe_allow_html=True)
