# Trained Neural Models Registry (models)

This directory serves as the persistent registry for compiled neural network weights exported in TorchScript serialization format (`.pt`). These models are loaded by the C++ engine runtime to perform optimal delta hedging predictions.

---

## 📊 Neural Model Lifecycle Diagrams

### 1. In-Engine Inference Flowchart
Describes how the C++ execution core loads the weights and evaluates a live feature tensor:

```mermaid
flowchart TD
    Init["Engine Start (read strategy_config.json)"] --> Load["Load JIT Module (torch::jit::load)"]
    Load --> Active["Model Ready in Memory"]
    
    Active --> Tick["Inbound Market Tick"]
    Tick --> Formatter["Feature Prep (Spot, Strike, DTE, IV, Delta)"]
    Formatter --> Tensor["Zero-Copy Input Tensor"]
    Tensor --> Eval["Forward Propagation (Module->forward)"]
    Eval --> Prediction["Output Delta Vector [0, 1]"]
```

### 2. High-Level Design (HLD)
Shows the model interface boundary between Python research training and C++ engine inference:

```mermaid
graph TD
    subgraph PythonResearch ["ML Research Lab (Python/PyTorch)"]
        Train["JIT Exporter (torch.jit.trace)"]
    end

    subgraph Registry ["Model Registry Folder (models/)"]
        LSTM["deep_hedge_lstm.pt (Recurrent Memory Model)"]
        FFNN["deep_hedge_ffnn.pt (Multilayer Feedforward Model)"]
        Adv["deep_hedge_adversarial.pt (Minimax Robust Model)"]
    end

    subgraph CppEngine ["Execution Core (C++/LibTorch)"]
        Loader["torch::jit::Module Loader"]
        Run["Inference Thread (torch_inference.dll)"]
    end

    Train -->|Save| LSTM & FFNN & Adv
    LSTM & FFNN & Adv -->|Read| Loader
    Loader --> Run
```

### 3. Model Registration & Loading Sequence
Visualizes the sequence of registering a model via REST API and invoking it in the live trading engine:

```mermaid
sequenceDiagram
    autonumber
    participant UI as Next.js Dashboard
    participant API as FastAPI Orchestrator
    participant DB as PostgreSQL DB
    participant Engine as C++ Engine Core

    UI->>API: POST /api/strategies (Model Selection)
    activate API
    API->>DB: Register strategy & record model path (.pt)
    API->>Engine: SendCommand (LoadModel: name, filepath)
    activate Engine
    Note over Engine: LibTorch loads model<br/>weights into active memory
    Engine-->>API: Command Acknowledged (SUCCESS)
    deactivate Engine
    API-->>UI: Strategy Active (HTTP 200)
    deactivate API
```

---

## 🗂️ Registry Folder Structure

```
models/
├── deep_hedge_adversarial.pt # Adversarial minimax deep hedging TorchScript model
├── deep_hedge_ffnn.pt        # Feedforward neural network deep hedging TorchScript model
└── deep_hedge_lstm.pt        # LSTM recurrent network deep hedging TorchScript model
```

---

## 💾 Model Interfaces

* **TorchScript Serialization**: PyTorch neural nets are converted to portable TorchScript using tracing. This decouples the execution core from the Python interpreter, allowing the C++ runtime to evaluate predictions with microsecond latency.
* **Loading Routine**:
  ```cpp
  #include <torch/script.h>
  
  torch::jit::Module module;
  try {
      module = torch::jit::load("models/deep_hedge_lstm.pt");
  } catch (const c10::Error& e) {
      std::cerr << "Error loading deep hedging model\n";
  }
  ```
