# Affinity-Core Backtesting Scripts

This directory contains utility scripts to list, query, download, and format options and equity data for backtesting.

---

### 1. List Available Symbols (`list_available_symbols.py`)
Lists all symbols currently indexed in the backtest engine database/directories, including their start and end dates.
* **Requirement**: The FastAPI backend must be running (port `8085`).
* **Usage**:
  ```bash
  python scripts/list_available_symbols.py
  ```

---

### 2. Download Option Data (`download_symbol.py`)
Downloads 5-minute options bar data for a specific ticker and date range from Alpaca and places them directly into the standard daily layout (`data/{SYMBOL}/{YYYY}/{MM}/{YYYY-MM-DD}.parquet`). They are instantly available for backtesting.
* **Requirement**: Alpaca API credentials configured in the root `.env` file.
* **Usage**:
  ```bash
  # Download a single day
  python scripts/download_symbol.py -s MSFT --start 2026-06-01

  # Download a date range
  python scripts/download_symbol.py -s NVDA --start 2026-06-01 --end 2026-06-05
  ```

---

### 3. List Downloadable Symbols/Expirations (`list_downloadable_symbols.py`)
Queries the Alpaca API for all options contracts currently listed for a given symbol, displaying the available expiration range (earliest to furthest dates) and contract counts.
* **Usage**:
  ```bash
  python scripts/list_downloadable_symbols.py -s AAPL
  ```

---

### 4. List All Option-Eligible Assets (`list_all_alpaca_symbols.py`)
Lists all active, options-eligible underlying symbols available on Alpaca.
* **Usage**:
  * Filter symbols starting with a prefix:
    ```bash
    python scripts/list_all_alpaca_symbols.py -f TS
    ```
  * Export the complete list of 6,200+ eligible symbols to a text file:
    ```bash
    python scripts/list_all_alpaca_symbols.py -o symbols.txt
    ```

---

### 5. Convert Raw SPY EOD Data (`convert_spy_eod.py`)
Normalizes the raw yearly `spy_eod_YYYY.parquet` files (2011 to 2023) by parsing the Quote/Expiry timestamps, mapping calls and puts to the standard schema, and outputting daily daily Parquet files.
* **Usage**:
  ```bash
  python scripts/convert_spy_eod.py
  ```
