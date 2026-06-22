# Frontend Dashboard Terminal (frontend_terminal)

The **Frontend Dashboard Terminal** is a Next.js (App Router) web interface designed for real-time monitoring and controlling of the Athena Aegis Engine platform. It displays live trading parameters, strategy holdings, execution logs, and historical backtesting chart visualizations.

---

## 📊 Client-Side Integration Diagrams

### 1. State Ingestion & Layout Flowchart
Visualizes how inbound updates trigger component updates:

```mermaid
flowchart TD
    API["FastAPI Backend (Port 8085)"] -->|WebSocket Logs / Status| WSClient["Browser WS Connection"]
    API -->|REST HTTP responses| AxiosClient["HTTP API Helpers (lib/api.ts)"]

    WSClient -->|Ingest lines| Zustand["Zustand Global State Stores"]
    AxiosClient -->|Hydrate states| Zustand

    Zustand -->|Recharts data stream| LiveChart["LiveTelemetryChart Panel"]
    Zustand -->|Holdings arrays| Holdings["HoldingsTable Panel"]
    Zustand -->|Logs buffer| Logs["TerminalLogs Panel"]

    subgraph UI ["Dashboard Interface Layout"]
        Layout["Resizable Panel Container"]
        Layout -->|localStorage size key| LiveChart
        Layout -->|localStorage size key| Holdings
        Layout -->|localStorage size key| Logs
    end
```

### 2. High-Level Design (HLD)
Shows the dashboard terminal component boundaries:

```mermaid
graph TD
    subgraph ViewPages ["Dashboard Pages (app/)"]
        Layout["layout.tsx (Sidebar & StatusBar)"]
        Home["page.tsx (Dashboard Entry)"]
        Engine["engine/page.tsx (Gateway / Live Controls)"]
        Backtest["backtest/page.tsx (Backtest Runs)"]
    end

    subgraph ZustandStores ["Zustand State Store Hooks"]
        EngineStore["useEngineStore"]
        BtStore["useBacktestStore"]
        LogStore["useLogStore"]
    end

    subgraph Components ["UI Components"]
        H_Card["StatusBar Connection Widget"]
        Holdings["HoldingsTable"]
        LogPanel["TerminalLogPanel"]
        Charts["Recharts Chart visualizers"]
    end

    Layout --> EngineStore
    Home --> EngineStore
    Home --> LogStore
    Engine --> EngineStore
    Engine --> LogStore
    Backtest --> BtStore

    EngineStore -.-> H_Card
    EngineStore -.-> Holdings
    LogStore -.-> LogPanel
    BtStore -.-> Charts
```

### 3. Backtest UI Render Sequence
Visualizes the flow when triggering a backtest from the browser:

```mermaid
sequenceDiagram
    autonumber
    participant User as User Click
    participant Store as Zustand Backtest Store
    participant Api as lib/api.ts Client
    participant WS as WebSocket Ingestion
    participant Chart as Recharts View

    User->>Store: Click "Run Backtest"
    activate Store
    Store->>Api: submitBacktest(Payload)
    Api-->>Store: Return HTTP 202 (Job UUID)
    Store->>Store: Set status = RUNNING, progress = 0%
    
    activate WS
    WS->>Store: Inbound event "progress_update" (e.g. 45%)
    Store->>Store: Update progress bar UI
    deactivate WS

    activate WS
    WS->>Store: Inbound event "job_complete" (Payload)
    Store->>Store: Hydrate result series data
    deactivate WS

    Store->>Chart: Pass P&L curve series
    activate Chart
    Chart->>User: Render Zoomable Brush Chart
    deactivate Chart
    deactivate Store
```

---

## 🗂️ Folder Structure

```
frontend_terminal/
├── app/                     # Next.js App Router Pages (engine, backtest, system layout)
├── components/              # UI widgets (holding tables, forms, logs, and split containers)
├── lib/                     # Client libraries (Axios API calls, WS client wrapper, Types)
├── styles/                  # Styling configurations (Tailwind styles, global themes)
├── public/                  # Static media assets & icons
├── package.json             # NPM package scripts & dependencies
└── tailwind.config.ts       # Tailwind CSS design system rules
```

---

## 💾 Data & REST API Client Integration

* **HTTP REST Requests**: Axios wrappers inside `lib/api.ts` connect to the backend (Port 8085) for connectivity commands (`connect`, `disconnect`), strategy configurations (`init`, `start`, `stop`), and backtest scheduling.
* **WebSocket Feeds**:
  * Real-time logs are parsed and held inside the Zustand log store, capping the buffer size locally to prevent memory leaks during long trading sessions.
  * Resizable split panes use mouse drag handlers and commit the current width/height percentages to `localStorage` under `athena_aegis_strategy_layout` to persist configuration across browser restarts.
