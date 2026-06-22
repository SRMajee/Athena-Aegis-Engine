# PyTorch Machine Learning Research Lab (research)

This directory hosts the PyTorch-based machine learning research lab for training Deep Hedging models. It supports standard Feed-Forward Neural Networks (FFNN), Long Short-Term Memory (LSTM) recurrent networks, and Minimax Adversarial models optimized using differentiable risk metrics (CVaR).

---

## 📊 Research & Training Diagrams

### 1. Training & Export Flowchart
Visualizes the training process from input data or synthetic path generation to the JIT TorchScript export:

```mermaid
flowchart TD
    DataReal["Real Options Data (data/*.parquet, *.csv)"] --> Load["Data Loading & Parsing"]
    DataSynth["Synthetic GBM Generator"] --> Load
    Load --> Features["Feature Tensor Preparation"]
    
    subgraph OptimizationLoop ["Training & Optimization Loop"]
        Features --> Forward["Forward Pass (NN Delta Prediction)"]
        Forward --> TradingPnl["Trading P&L & Turnover Calculation"]
        TradingPnl --> CVaR["Tail-Risk CVaR Loss Valuation"]
        CVaR --> Backprop["SGD / Adam Parameter Update"]
    end
    
    Backprop -->|Converged| Trace["JIT Compilation (torch.jit.trace)"]
    Trace --> Export["Exported Model (models/deep_hedge_*.pt)"]
```

### 2. High-Level Design (HLD)
Represents the neural network architectures and feature dimensions inside the lab:

```mermaid
graph TD
    subgraph InputFeatures ["Input Features (5-Dimension Tensor)"]
        S["Spot Price (S_t)"]
        SD["Strike Distance (S_t / K - 1)"]
        DTE["Days to Expiration (DTE_t)"]
        IV["Implied Volatility (IV_t)"]
        DP["Previous Delta (delta_{t-1})"]
    end

    subgraph ModelArchitectures ["Model Architectures"]
        LSTM["LSTMHedger (2x LSTM + Linear)"]
        FFNN["FFNNHedger (3x Dense + ReLU)"]
        Adversarial["MinimaxHedger (Generator vs Shocker)"]
    end

    subgraph LossFunctions ["Differentiable Risk Evaluators"]
        CVaRLoss["Conditional Value-at-Risk (CVaR Loss)"]
    end

    subgraph OutputTargets ["Model Export Outputs"]
        LSTM_pt["deep_hedge_lstm.pt"]
        FFNN_pt["deep_hedge_ffnn.pt"]
        Adv_pt["deep_hedge_adversarial.pt"]
    end

    S & SD & DTE & IV & DP --> LSTM & FFNN & Adversarial
    LSTM & FFNN & Adversarial --> CVaRLoss
    CVaRLoss --> LSTM_pt & FFNN_pt & Adv_pt
```

### 3. Minimax Training Sequence
Visualizes the epoch loop for training the adversarial Deep Hedging model:

```mermaid
sequenceDiagram
    autonumber
    participant Trainer as Training Script
    participant Gen as Hedger Generator (Agent)
    participant Adv as Market Shocker (Adversary)
    participant Loss as CVaR Evaluator
    participant Disk as Saved Models Folder

    loop For each Epoch
        Trainer->>Adv: Generate market perturbation parameters
        Adv-->>Trainer: Return perturbed spot price paths
        Trainer->>Gen: Predict optimal delta hedges along path
        Gen-->>Trainer: Return predicted delta sequence
        Trainer->>Loss: Calculate portfolio P&L tail loss
        Loss-->>Trainer: Return gradient loss
        Trainer->>Trainer: Backpropagate and update weights
    end
    Trainer->>Disk: Export JIT tracing model (.pt)
```

---

## 🗂️ Folder Structure

```
research/
├── train_adversarial.ipynb  # Minimax adversarial model trainer
├── train_ffnn.ipynb         # Feed-forward neural network options hedger trainer
└── train_lstm.ipynb         # LSTM recurrent neural network options hedger trainer
```

---

## 💾 Model Configuration & Data Specification

* **Input Feature Map**: Model inputs are tensors of shape `(batch_size, sequence_length, 5)` consisting of:
  1. Underlying spot price.
  2. Normalized strike distance: $(S_t / K) - 1.0$.
  3. Time-to-maturity (DTE) scaled in years.
  4. Implied Volatility (approximate or raw).
  5. Delta from previous tick to control transaction costs.
* **Loss Metric**: Unlike standard mean-squared error, training minimizes the Conditional Value-at-Risk (CVaR) of the hedging portfolio:
  $$\text{CVaR}_\alpha(X) = \mathbb{E}[-X \mid X \le q_\alpha]$$
  where $X$ is the path hedging P&L including a transaction cost penalty rate.
