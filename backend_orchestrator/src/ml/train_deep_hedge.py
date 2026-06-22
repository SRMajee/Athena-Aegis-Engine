import os
import glob
import re
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from datetime import datetime, timezone

# Set device
device = torch.device("cpu")

# 1. Differentiable CVaR Loss
def calculate_cvar_loss(pnl, alpha=0.05):
    sorted_pnl, _ = torch.sort(pnl)
    num_samples = sorted_pnl.size(0)
    cvar_index = int(np.floor(num_samples * alpha))
    if cvar_index < 1:
        cvar_index = 1
    worst_pnl = sorted_pnl[:cvar_index]
    cvar_loss = -torch.mean(worst_pnl)
    return cvar_loss

# 2. PyTorch Modules - Scale Invariant
class FFNNHedger(nn.Module):
    def __init__(self, input_dim=5):
        super(FFNNHedger, self).__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid() # call delta [0, 1]
        )
        
    def forward(self, x):
        # x[..., 0]: raw spot. x[..., 1]: strike_dist = spot/strike - 1
        x_norm = x.clone()
        x_norm[..., 0] = x[..., 1] + 1.0 # spot/K
        return self.net(x_norm)

class LSTMHedger(nn.Module):
    def __init__(self, input_dim=5, hidden_dim=32):
        super(LSTMHedger, self).__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True, num_layers=2, dropout=0.1)
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 1)
        )
        
    def forward(self, x):
        x_norm = x.clone()
        x_norm[..., 0] = x[..., 1] + 1.0
        out, _ = self.lstm(x_norm)
        return torch.sigmoid(self.fc(out[:, -1, :]))

class MarketGenerator(nn.Module):
    def __init__(self, input_dim=2):
        super(MarketGenerator, self).__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 2),
            nn.Tanh()
        )
    def forward(self, x):
        return self.net(x)

# Parse OCC symbols to get Expiry, Strike, and Option Type
def parse_occ_symbol(symbol):
    match = re.search(r"(\d{2})(\d{2})(\d{2})([CP])(\d{8})$", symbol)
    if not match:
        return None, None, None
    yy, mm, dd, cp, strike_raw = match.groups()
    year = 2000 + int(yy) if int(yy) < 80 else 1900 + int(yy)
    expiry = datetime(year, int(mm), int(dd), 16, 0, tzinfo=timezone.utc)
    strike = int(strike_raw) / 1000.0
    opt_type = 'CALL' if cp == 'C' else 'PUT'
    return expiry, strike, opt_type

def implied_volatility_approx(spot, strike, dte, price, is_call=True):
    # Simple Brenner-Subrahmanyam IV approximation as proxy
    if dte <= 0.0 or spot <= 0.0 or price <= 0.0:
        return 0.20
    try:
        val = (price / spot) * np.sqrt(2 * np.pi / dte)
        return float(np.clip(val, 0.05, 0.80))
    except:
        return 0.20

def load_real_paths():
    print("Loading actual options parquet data for SPY, AAPL, and MSFT to build a generalized cross-asset model...")
    paths_collected = []
    
    # Define datasets to load
    # SPY: Jan-Mar 2010. AAPL: Jun-Jul 2025. MSFT: Jan-Mar 2024.
    targets = [
        {"dir": r"c:\Users\User\Desktop\Affinity-Core\data\SPY\2010", "months": ["01", "02", "03"]},
        {"dir": r"c:\Users\User\Desktop\Affinity-Core\data\AAPL\2025", "months": ["06", "07"]},
        {"dir": r"c:\Users\User\Desktop\Affinity-Core\data\MSFT\2024", "months": ["01", "02", "03"]}
    ]
    
    for target in targets:
        data_dir = target["dir"]
        if not os.path.exists(data_dir):
            continue
        files = []
        for m in target["months"]:
            files.extend(glob.glob(os.path.join(data_dir, m, "*.parquet")))
        files = sorted(files)
        if not files:
            continue
            
        # Read and concatenate parquets for this asset
        dfs = []
        for f in files:
            try:
                dfs.append(pd.read_parquet(f))
            except Exception as e:
                print(f"Error reading {f}: {e}")
        if not dfs:
            continue
            
        df = pd.concat(dfs, ignore_index=True)
        unique_syms = df['symbol'].unique()
        
        print(f"  Processing options series for {len(unique_syms)} symbols in {os.path.basename(os.path.dirname(data_dir))}...")
        # Sample up to 250 symbols per asset to ensure balanced training paths
        for sym_raw in unique_syms[:250]:
            sym = str(sym_raw)
            expiry, strike, opt_type = parse_occ_symbol(sym)
            if not expiry or opt_type != 'CALL' or strike is None:
                continue
                
            contract_df = df[df['symbol'] == sym_raw].sort_values('ts_recv')
            if len(contract_df) < 31: # We need at least 31 days to get a 30-step path
                continue
                
            spots = ((contract_df['underlying_bid_px'] + contract_df['underlying_ask_px']) / 2.0).values
            opt_prices = ((contract_df['bid_px'] + contract_df['ask_px']) / 2.0).values
            ts_recvs = contract_df['ts_recv'].values
            
            path_len = 30
            for offset in range(0, len(spots) - path_len - 1, 5):
                S_seq = spots[offset : offset + path_len + 1]
                C_seq = opt_prices[offset : offset + path_len + 1]
                t_seq = ts_recvs[offset : offset + path_len + 1]
                
                if np.any(S_seq <= 0.0) or np.any(C_seq <= 0.0):
                    continue
                    
                IV_seq = []
                DTE_seq = []
                for t_idx in range(path_len + 1):
                    # Calculate DTE relative to expiry
                    curr_dt = pd.to_datetime(t_seq[t_idx])
                    if curr_dt.tzinfo is None:
                        curr_dt = curr_dt.tz_localize(timezone.utc)
                    else:
                        curr_dt = curr_dt.tz_convert(timezone.utc)
                    time_diff = expiry - curr_dt
                    curr_dte = max(0.0001, time_diff.total_seconds() / (365.25 * 24 * 3600))
                    DTE_seq.append(curr_dte)
                    IV_seq.append(implied_volatility_approx(S_seq[t_idx], strike, curr_dte, C_seq[t_idx]))
                    
                paths_collected.append({
                    'S': torch.tensor(S_seq, dtype=torch.float32),
                    'C': torch.tensor(C_seq, dtype=torch.float32),
                    'IV': torch.tensor(IV_seq, dtype=torch.float32),
                    'DTE': torch.tensor(DTE_seq, dtype=torch.float32),
                    'strike': strike
                })
                
    print(f"Successfully constructed {len(paths_collected)} cross-asset option paths!")
    return paths_collected

def train_and_export():
    paths = load_real_paths()
    if not paths:
        print("No real paths loaded. Falling back to synthetic paths.")
        return
        
    epochs = 40
    lr = 0.01
    cost_rate = 0.0005 # 5 bps transaction cost friction
    num_steps = 30

    # 1. Train FFNN
    print("Training FFNN Hedger on real cross-asset options (batch size 512)...")
    ffnn = FFNNHedger(input_dim=5)
    optimizer_ffnn = optim.Adam(ffnn.parameters(), lr=lr)
    scheduler_ffnn = optim.lr_scheduler.CosineAnnealingLR(optimizer_ffnn, T_max=epochs)
    
    # Stack paths into unified tensors for fast batched training
    S_tensor = torch.stack([p['S'] for p in paths])  # (N, num_steps + 1)
    C_tensor = torch.stack([p['C'] for p in paths])  # (N, num_steps + 1)
    IV_tensor = torch.stack([p['IV'] for p in paths])  # (N, num_steps + 1)
    DTE_tensor = torch.stack([p['DTE'] for p in paths])  # (N, num_steps + 1)
    K_tensor = torch.tensor([p['strike'] for p in paths], dtype=torch.float32).unsqueeze(1)  # (N, 1)
    
    num_samples = len(paths)
    batch_size = 512
    
    for epoch in range(epochs):
        ffnn.train()
        epoch_loss = 0.0
        indices = torch.randperm(num_samples)
        
        for idx in range(0, num_samples, batch_size):
            batch_idx = indices[idx : idx + batch_size]
            b_S = S_tensor[batch_idx]       # (B, 31)
            b_C = C_tensor[batch_idx]       # (B, 31)
            b_IV = IV_tensor[batch_idx]     # (B, 31)
            b_DTE = DTE_tensor[batch_idx]   # (B, 31)
            b_K = K_tensor[batch_idx]       # (B, 1)
            
            b_size = len(batch_idx)
            deltas = torch.zeros(b_size, num_steps + 1)
            delta_prev = torch.zeros(b_size, 1)
            
            for t in range(num_steps):
                S_t = b_S[:, t:t+1]
                strike_dist = (S_t / b_K) - 1.0
                dte_t = b_DTE[:, t:t+1]
                iv_t = b_IV[:, t:t+1]
                
                features = torch.cat([S_t, strike_dist, dte_t, iv_t, delta_prev], dim=1)
                delta_t = ffnn(features)
                deltas[:, t] = delta_t.squeeze(1)
                delta_prev = delta_t.detach()
                
            opt_payout = b_C[:, -1] - b_C[:, 0]
            price_changes = b_S[:, 1:] - b_S[:, :-1]
            trading_pnl = torch.sum(deltas[:, :-1] * price_changes, dim=1)
            
            trade_turnover = torch.abs(deltas[:, 1:] - deltas[:, :-1])
            transaction_costs = torch.sum(trade_turnover * b_S[:, :-1] * cost_rate, dim=1)
            
            pnl = -opt_payout + trading_pnl - transaction_costs
            loss = calculate_cvar_loss(pnl)
            
            optimizer_ffnn.zero_grad()
            loss.backward()
            optimizer_ffnn.step()
            epoch_loss += loss.item() * b_size
            
        scheduler_ffnn.step()
        print(f"  FFNN Epoch {epoch+1}/{epochs}, Loss: {epoch_loss / num_samples:.4f}")

    # 2. Train LSTM
    print("Training LSTM Hedger on real cross-asset options (batch size 512)...")
    lstm_model = LSTMHedger(input_dim=5)
    optimizer_lstm = optim.Adam(lstm_model.parameters(), lr=lr)
    scheduler_lstm = optim.lr_scheduler.CosineAnnealingLR(optimizer_lstm, T_max=epochs)
    
    for epoch in range(epochs):
        lstm_model.train()
        epoch_loss = 0.0
        indices = torch.randperm(num_samples)
        
        for idx in range(0, num_samples, batch_size):
            batch_idx = indices[idx : idx + batch_size]
            b_S = S_tensor[batch_idx]       # (B, 31)
            b_C = C_tensor[batch_idx]       # (B, 31)
            b_IV = IV_tensor[batch_idx]     # (B, 31)
            b_DTE = DTE_tensor[batch_idx]   # (B, 31)
            b_K = K_tensor[batch_idx]       # (B, 1)
            
            b_size = len(batch_idx)
            deltas = torch.zeros(b_size, num_steps + 1)
            delta_prev = torch.zeros(b_size, 1)
            
            for t in range(num_steps):
                S_t = b_S[:, t:t+1]
                strike_dist = (S_t / b_K) - 1.0
                dte_t = b_DTE[:, t:t+1]
                iv_t = b_IV[:, t:t+1]
                
                # Input shape for LSTM: (batch_size, sequence_length, features) -> (B, 1, 5)
                features_t = torch.cat([S_t, strike_dist, dte_t, iv_t, delta_prev], dim=1).unsqueeze(1)
                delta_t = lstm_model(features_t)
                deltas[:, t] = delta_t.squeeze(1)
                delta_prev = delta_t.detach()
                
            opt_payout = b_C[:, -1] - b_C[:, 0]
            price_changes = b_S[:, 1:] - b_S[:, :-1]
            trading_pnl = torch.sum(deltas[:, :-1] * price_changes, dim=1)
            
            trade_turnover = torch.abs(deltas[:, 1:] - deltas[:, :-1])
            transaction_costs = torch.sum(trade_turnover * b_S[:, :-1] * cost_rate, dim=1)
            
            pnl = -opt_payout + trading_pnl - transaction_costs
            loss = calculate_cvar_loss(pnl)
            
            optimizer_lstm.zero_grad()
            loss.backward()
            optimizer_lstm.step()
            epoch_loss += loss.item() * b_size
            
        scheduler_lstm.step()
        print(f"  LSTM Epoch {epoch+1}/{epochs}, Loss: {epoch_loss / num_samples:.4f}")

    # 3. Train Adversarial Hedger (Minimax)
    print("Training Adversarial Hedger on real cross-asset options (batch size 512)...")
    adv_hedger = FFNNHedger(input_dim=5)
    adversary = MarketGenerator(input_dim=2)
    optimizer_adv_hedger = optim.Adam(adv_hedger.parameters(), lr=lr)
    optimizer_adversary = optim.Adam(adversary.parameters(), lr=0.003)
    scheduler_adv = optim.lr_scheduler.CosineAnnealingLR(optimizer_adv_hedger, T_max=epochs)
    
    for epoch in range(epochs):
        adv_hedger.train()
        adversary.train()
        epoch_loss = 0.0
        indices = torch.randperm(num_samples)
        
        for idx in range(0, num_samples, batch_size):
            batch_idx = indices[idx : idx + batch_size]
            b_S = S_tensor[batch_idx].clone()       # (B, 31)
            b_C = C_tensor[batch_idx].clone()       # (B, 31)
            b_IV = IV_tensor[batch_idx].clone()     # (B, 31)
            b_DTE = DTE_tensor[batch_idx]           # (B, 31)
            b_K = K_tensor[batch_idx]               # (B, 1)
            
            b_size = len(batch_idx)
            
            # Simulated adversarial path generation
            S_list = [b_S[:, 0]]
            IV_list = [b_IV[:, 0]]
            for t in range(num_steps):
                S_t = S_list[-1]
                IV_t = IV_list[-1]
                adv_input = torch.cat([S_t.unsqueeze(1) / b_K, IV_t.unsqueeze(1)], dim=1)
                shocks = adversary(adv_input)
                
                S_next = b_S[:, t+1] + shocks[:, 0] * 0.015 * S_t
                IV_next = torch.clamp(b_IV[:, t+1] + shocks[:, 1] * 0.015, 0.05, 0.80)
                S_list.append(S_next)
                IV_list.append(IV_next)
                
            batch_S = torch.stack(S_list, dim=1)    # (B, 31)
            batch_IV = torch.stack(IV_list, dim=1)  # (B, 31)
            
            deltas = torch.zeros(b_size, num_steps + 1)
            delta_prev = torch.zeros(b_size, 1)
            
            for t in range(num_steps):
                S_t = batch_S[:, t:t+1]
                strike_dist = (S_t / b_K) - 1.0
                dte_t = b_DTE[:, t:t+1]
                iv_t = batch_IV[:, t:t+1]
                
                features = torch.cat([S_t, strike_dist, dte_t, iv_t, delta_prev], dim=1)
                delta_t = adv_hedger(features)
                deltas[:, t] = delta_t.squeeze(1)
                delta_prev = delta_t.detach()
                
            opt_payout = b_C[:, -1] - b_C[:, 0]
            price_changes = batch_S[:, 1:] - batch_S[:, :-1]
            trading_pnl = torch.sum(deltas[:, :-1] * price_changes, dim=1)
            
            trade_turnover = torch.abs(deltas[:, 1:] - deltas[:, :-1])
            transaction_costs = torch.sum(trade_turnover * batch_S[:, :-1] * cost_rate, dim=1)
            
            pnl = -opt_payout + trading_pnl - transaction_costs
            loss = calculate_cvar_loss(pnl)
            
            optimizer_adv_hedger.zero_grad()
            optimizer_adversary.zero_grad()
            
            loss.backward()
            
            optimizer_adv_hedger.step()
            # Flip gradient to maximize loss for adversary
            for param in adversary.parameters():
                if param.grad is not None:
                    param.grad.data.mul_(-1.0)
            optimizer_adversary.step()
            
            epoch_loss += loss.item() * b_size
            
        scheduler_adv.step()
        print(f"  Adversarial Epoch {epoch+1}/{epochs}, Loss: {epoch_loss / num_samples:.4f}")

    # Export TorchScript JIT modules to the project root models directory
    print("Exporting TorchScript models...")
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    models_dir = os.path.join(project_root, "models")
    os.makedirs(models_dir, exist_ok=True)
    
    example_input = torch.randn(2, 5)
    
    ffnn.eval()
    traced_ffnn = torch.jit.trace(ffnn, example_input)
    traced_ffnn.save(os.path.join(models_dir, "deep_hedge_ffnn.pt"))
    
    lstm_model.eval()
    traced_lstm = torch.jit.trace(lstm_model, torch.randn(2, 1, 5))
    traced_lstm.save(os.path.join(models_dir, "deep_hedge_lstm.pt"))
    
    adv_hedger.eval()
    traced_adv = torch.jit.trace(adv_hedger, example_input)
    traced_adv.save(os.path.join(models_dir, "deep_hedge_adversarial.pt"))
    print(f"All models exported successfully to {models_dir}")

if __name__ == "__main__":
    train_and_export()
