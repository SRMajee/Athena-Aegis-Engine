# Utility & Crawler Scripts (scripts)

This directory contains utility scripts to list, query, download, and format options and equity data for backtesting, as well as configuration indexers.

---

## 📊 Script Execution Diagrams

### 1. Market Data Crawler Flowchart
Visualizes how raw option chains are queried, downloaded, and structured for backtesting:

```mermaid
flowchart TD
    User["Developer Run (CMD/Shell)"] --> Run["download_symbol.py"]
    Run --> Config["Read Alpaca API Keys (.env)"]
    Config --> Client["Alpaca REST Client"]
    
    Client -->|Query Contracts| AlpacaChains["Alpaca Option Chains Endpoint"]
    Client -->|Download 5min Bars| AlpacaBars["Alpaca Options Bars Endpoint"]
    
    AlpacaChains & AlpacaBars --> Parser["Panda DataFrame Parser"]
    Parser --> Group["Group by Trade Date (YYYY-MM-DD)"]
    Group --> Writer["Write Parquet File (zero-copy layout)"]
    
    Writer --> DataPath["data/SYMBOL/YYYY/MM/YYYY-MM-DD.parquet"]
```

### 2. High-Level Design (HLD)
Shows the script utilities grouping:

```mermaid
graph TD
    subgraph DataCrawlers ["Data Crawlers (scripts/)"]
        Single["download_symbol.py (Single Day / Range)"]
        Bulk["download_bulk_symbols.py (Multiple Tick Class)"]
        Prefix["download_prefixed_symbols.py (Ticker Sets)"]
    end

    subgraph Normalizers ["Data Reformatter Scripts"]
        SPY["convert_spy_eod.py (Normalized yearly CSVs)"]
    end

    subgraph ConfigUtils ["Config Utilities (scripts/config_utilities/)"]
        Refs["find_references.py (Usage scanner)"]
        List["list_projects_config.py (Profile scanner)"]
        Json["print_project_json.py (Format serializer)"]
        Search["search_project_configs.py (Config searcher)"]
    end
```

### 3. Option Chain Ingestion Sequence
Details the network call flow to cache options contracts locally:

```mermaid
sequenceDiagram
    autonumber
    participant Dev as Developer / CLI
    participant Script as download_symbol.py
    participant SDK as Alpaca Python SDK
    participant API as Alpaca REST API
    participant Disk as Local Storage

    Dev->>Script: Run with --symbol MSFT --start 2026-06-01
    activate Script
    Script->>SDK: Initialize(API_KEY, SECRET_KEY)
    Script->>SDK: Get option chains (MSFT underlying)
    SDK->>API: GET /v2/options/contracts?underlying_symbol=MSFT
    API-->>SDK: Return 800+ contract definitions
    Script->>SDK: Fetch bar ticks for date range
    loop For each contract chain
        SDK->>API: GET /v2/options/bars (Contract symbol, start, end)
        API-->>SDK: Return bar time series
    end
    Script->>Script: Parse quote/expiry columns to standard schema
    Script->>Disk: Save to data/MSFT/2026/06/2026-06-01.parquet
    Script-->>Dev: Print download status summary
    deactivate Script
```

---

## 🗂️ Folder Structure

```
scripts/
├── config_utilities/        # Configuration scanning and formatting utilities
│   ├── find_references.py
│   ├── list_projects_config.py
│   ├── print_project_json.py
│   └── search_project_configs.py
├── README.md                # Documentation folder map
├── convert_spy_eod.py       # SPY EOD pricing reformatter
├── download_alpaca_options.py # Comprehensive underlying options crawler
├── download_bulk_symbols.py # Multi-contract range download utility
├── download_prefixed_symbols.py # Download ticker listings by prefix
├── download_symbol.py       # Query single underlying options bar data
├── list_all_alpaca_symbols.py # Query active options-eligible underlying assets
├── list_available_symbols.py # Scan local directories for data duration
├── list_downloadable_symbols.py # Query Alpaca API expiration dates
├── run_checksum_tests.ps1   # PowerShell checksum tests CI runner
├── verify_determinism.py    # NFR-03 Determinism validator (Subprocess)
└── verify_determinism_grpc.py # NFR-03 Determinism validator (gRPC Stream)
```

---

## 🔌 API & Integration Contracts

* **Alpaca REST Integration**: Crawler scripts utilize the `alpaca-py` library to query market option chains and bars. Authentication is injected using `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` environment variables.
* **Storage Schema**: The final downloaded files are serialized into standardized Parquet columns matching the backtesting engine’s Tick schema requirements.