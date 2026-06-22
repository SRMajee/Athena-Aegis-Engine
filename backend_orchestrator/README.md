# Backend Orchestration Server (backend_orchestrator)

The **Backend Orchestration Server** is a Python FastAPI web server that handles front-facing REST endpoints, WebSocket broadcasts, database persistence (SQLModel over PostgreSQL), and asynchronous backtesting task queues (Redis and ARQ workers). It acts as the orchestration layer between the Next.js control panel and the compiled C++ execution core.

---

## 📊 Architecture & Integration Diagrams

### 1. Inbound Request Routing Flowchart
Visualizes how HTTP requests, WebSocket handshakes, and database updates are handled:

```mermaid
flowchart TD
    Client["Client (UI Terminal / HTTP)"] --> Router["FastAPI APIRouter"]
    Router --> Service["Domain Service (Main, Strategy, Backtest, System)"]
    
    subgraph Storage ["Infrastructure & Storage"]
        DB[("PostgreSQL Database")]
        Redis[("Redis Event Broker")]
    end

    subgraph Core ["Execution Core Interface"]
        Engine["EngineClient (gRPC)"]
        Subproc["Subprocess Runner"]
    end

    Service <-->|SQLModel ORM| DB
    Service <-->|ARQ Enqueue & Set/Get| Redis
    Service <-->|Async gRPC Commands| Engine
    Service -->|Start backtest binary| Subproc
```

### 2. High-Level Design (HLD)
Shows the backend modules and service layers:

```mermaid
graph TD
    subgraph REST ["API Route Handlers"]
        E_API["engine.py (Gateway/Market/Strategy)"]
        B_API["backtest.py (Submissions/Files)"]
        S_API["system.py (Health/Database)"]
    end

    subgraph Services ["Service Domain Layer"]
        MainSvc["MainService"]
        StratSvc["StrategyService"]
        BtSvc["BacktestService"]
        SysSvc["SystemService"]
    end

    subgraph Infra ["Infrastructure Layer"]
        gRPC["remote_client.py (EngineClient)"]
        TaskQ["task_queue.py (ARQ Worker Tasks)"]
        DB_Mod["db.py (Postgres Sessions)"]
        WS["websockets.py (Broadcast Pools)"]
    end

    E_API --> MainSvc
    E_API --> StratSvc
    B_API --> BtSvc
    S_API --> SysSvc

    MainSvc <--> gRPC
    StratSvc <--> gRPC
    BtSvc <--> TaskQ
    SysSvc <--> DB_Mod
    TaskQ <--> DB_Mod
    gRPC -->|Logs Queue| WS
```

### 3. Log Streaming Sequence Diagram
Traces the real-time log ingestion and broadcast flow:

```mermaid
sequenceDiagram
    autonumber
    participant UI as Next.js Terminal Log Panel
    participant WS as FastAPI Websocket Handler
    participant Lifespan as Lifespan Log Consumer
    participant Engine as C++ Engine gRPC Stream

    UI->>WS: ws://localhost:8085/ws/logs (Connect)
    activate WS
    WS->>WS: Add to AppState.ws.log_clients pool
    
    activate Lifespan
    Lifespan->>Engine: StreamLogs(Empty)
    loop Every Log Line
        Engine-->>Lifespan: Yield Log String
        Lifespan->>WS: Push log string to log_queue
        WS->>UI: Broadcast line to all log_clients
    end
    deactivate Lifespan
    deactivate WS
```

---

## 🗂️ Directory Layout

```
backend_orchestrator/
├── src/
│   ├── api/                 # HTTP routers & schemas (engine.py, backtest.py, system.py)
│   ├── services/            # Domain service logic classes (main.py, strategy.py, backtest.py)
│   ├── infra/               # Infrastructure (remote_client.py, db.py, task_queue.py, websockets.py)
│   ├── proto/               # Generated gRPC code (otrader_engine_pb2_grpc)
│   └── utils/               # Helpers (parquet tools, PDF charts generators)
├── tests/                   # Pytest API tests (test_gateway.py, test_strategies.py, etc.)
├── requirements.txt         # Package dependencies (fastapi, sqlmodel, arq)
├── pytest.ini               # Pytest configurations
└── server_fastapi.py        # Web app entry point & lifespan manager
```

---

## 💾 REST & Database Integrations

* **REST APIs**: Interfaces with the Next.js frontend using JSON payloads (defined in `api/schemas/`). Calls are validated by Pydantic models.
* **WebSocket Channels**:
  * `/ws/logs`: Pushes engine trace logs to the frontend at up to 60Hz.
  * `/ws/strategies`: Handles client strategy state subscription.
* **Database Access**: Uses SQLModel over `asyncpg` for PostgreSQL connection pooling. Mocks are injected in unit tests using `pytest-mock` by monkeypatching the `async_session_maker` function.
