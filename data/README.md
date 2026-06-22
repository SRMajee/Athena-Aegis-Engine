# Market Data Storage & Reports (data)

This directory is the local data repository for options tick and bar datasets (saved in zero-copy Apache Parquet format) and generated PDF performance reports.

---

## 📊 Data Ingestion & Layout Diagrams

### 1. File Path Resolution Flowchart
Describes how the backend orchestrator and C++ engine resolve local file locations for backtesting:

```mermaid
flowchart TD
    Symbol["Underlying Symbol (e.g., AAPL)"] --> Year["Year Folder (e.g., 2026)"]
    Year --> Month["Month Folder (e.g., 06)"]
    Month --> File["Daily Parquet File (AAPL/2026/06/2026-06-23.parquet)"]
    
    File --> Loader["C++ Parquet Reader"]
    Loader --> Ingest["Tick Stream Simulation"]
```

### 2. High-Level Design (HLD)
Shows the logical grouping of datasets and output reports:

```mermaid
graph TD
    subgraph DataRoot ["data/ Directory"]
        subgraph Symbols ["Asset Tickers"]
            SPY["SPY/ Options Parquets"]
            NVDA["NVDA/ Options Parquets"]
            AAPL["AAPL/ Options Parquets"]
        end
        
        subgraph Reports ["Reports Outlet"]
            PDF["reports/ (Job performance PDF files)"]
        end
        
        subgraph Temporary ["Temp Buffer"]
            Temp["temp/ (Intermediate cache files)"]
        end
    end

    Symbols -->|Engine Sim Ingestion| Engine["cpp_engine Backtester"]
    Engine -->|Generate Report Charts| PDF
```

### 3. Backtest Data Stream Sequence
Visualizes the read/write sequences of data files during a backtesting job execution:

```mermaid
sequenceDiagram
    autonumber
    participant Worker as ARQ Backtest Task
    participant Disk as Local Data Storage (Parquet)
    participant Engine as C++ Engine Binary
    participant DB as PostgreSQL DB
    participant PDF as Reports Directory

    Worker->>Engine: Launch binary with --data_path data/SYMBOL/...
    activate Engine
    Engine->>Disk: Read daily options bars (parquet)
    Disk-->>Engine: Stream zero-copy rows
    Note over Engine: Execute Deep Hedging strategy,<br/>compute portfolio analytics
    Engine->>DB: Write RiskSnapshots & execution trades
    Engine-->>Worker: Finished execution code (0)
    deactivate Engine
    Worker->>DB: Query job execution records
    Worker->>PDF: Write PDF report with charts to data/reports/
    Worker-->>Worker: Complete task
```

---

## 🗂️ Folder Structure

```
data/
├── [SYMBOL]/                # Options data directories grouped by ticker symbol
│   └── [YYYY]/              # Directory organized by Year (e.g., 2026)
│       └── [MM]/            # Directory organized by Month (e.g., 06)
│           └── *.parquet    # Daily options bar data parquet files
├── reports/                 # Output folder for generated backtest PDF reports
└── temp/                    # Temporary working cache directory
```

---

## 💾 Parquet Columns & Data Format

The daily options bar files stored in the symbol directories must conform to the following schema:

| Column Name | Type | Description |
| :--- | :--- | :--- |
| `ts_recv` | Timestamp | Timestamp when the bar was completed (UTC / local) |
| `symbol` | String | OCC Option Contract code (e.g., `AAPL260619C00150000`) |
| `bid_px` | Double | Inside bid price |
| `ask_px` | Double | Inside ask price |
| `underlying_bid_px` | Double | Bid price of the underlying asset |
| `underlying_ask_px` | Double | Ask price of the underlying asset |
| `strike` | Double | Contract strike price |
| `dte` | Double | Days to expiration scaled in years ($DTE / 365.25$) |
| `vol` | Double | Implied volatility |
