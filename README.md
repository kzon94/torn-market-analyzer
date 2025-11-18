# Kzon's Torn Market Analyzer

This project is a Streamlit web application that analyzes player inventory listings from the Torn online game.

Users can paste their **Add Listing** text directly from Torn’s Item Market, and the app automatically parses item names, matches them against a local dictionary, retrieves market data from Torn’s public API, and computes detailed market analytics and price recommendations.

---

## Features

### Input Processing

* Accepts raw text copied from the Torn "Add Listing" market page.
* Parses item names, quantities, and ignores irrelevant UI elements.
* Automatically removes untradable or equipped items.
* Applies fuzzy matching to map item names to Torn item IDs.
* Uses a local dictionary file (`torn_item_dictionary.csv`).

### Market Data Retrieval

* Queries Torn's `itemmarket` endpoint using the user’s public API key.
* Fetches the first 10 lowest sell listings for each matched item.
* Includes built-in rate limiting with a token bucket system.

### Market Analytics

* Computes KPIs such as:

  * Minimum/maximum price
  * Weighted mean price
  * Mean price for the first 20 units
  * Price spread and volatility
  * Total market depth
* Generates recommended sale prices based on market structure and Torn’s 5% market fee.

### Output

* Displays parsed data, raw market listings, KPIs, and price recommendations.
* Allows downloading all processed datasets as CSV files:

  * `clean_data_id.csv`
  * `market_list.csv`
  * `market_kpis.csv`
  * `market_suggestions.csv`

### User Experience

* Clean, centered UI with a collapsible “How this app works” guide.
* Caches the user’s public API key locally for convenience.
* Fully responsive layout designed for ease of use.

---

## Project Structure

```
torn-market-analyzer/
│
├── app/
│   └── streamlit_app.py         # Main Streamlit UI and pipeline
│
├── src/
│   └── tma/
│       ├── config.py            # Global constants and dictionary configuration
│       ├── matching.py          # Text parsing, cleaning, fuzzy matching
│       ├── http_api.py          # API calls to Torn (itemmarket)
│       ├── rate_limit.py        # Token bucket for rate limiting
│       ├── analytics.py         # KPI calculations and price recommendations
│       ├── io_utils.py          # CSV export and formatting helpers
│       └── __init__.py
│
├── data/
│   └── torn_item_dictionary.csv # Local dictionary for item name mapping
│
├── LICENSE
├── README.md
└── requirements.txt
```

---

## Requirements

The application requires:

* Python 3.10 or later
* Streamlit
* Pandas
* NumPy
* Requests
* PyArrow


---

## Running Locally

1. Install dependencies:

```
pip install -r requirements.txt
```

2. Run the Streamlit app:

```
streamlit run app/streamlit_app.py
```

3. Open the link shown in terminal (usually `http://localhost:8501`).

---

## Notes About Torn API Usage

* Only **public API keys** are used.
* The app performs **read-only** calls to `itemmarket`.
* User keys are only cached locally via Streamlit and never transmitted elsewhere.
* The app respects Torn API rate limits through controlled request throttling.

---

## License

This project is licensed under the MIT License.
See the `LICENSE` file for full details.

