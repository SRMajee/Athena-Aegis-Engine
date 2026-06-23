import os
import re
import math
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from datetime import datetime, timezone

device = torch.device("cpu")
print(f"Using device: {device}")

def calculate_cvar_loss(pnl, alpha=0.05):
    sorted_pnl, _ = torch.sort(pnl)
    num_samples = sorted_pnl.size(0)
    cvar_index = int(np.floor(num_samples * alpha))
    if cvar_index < 1:
        cvar_index = 1
    worst_pnl = sorted_pnl[:cvar_index]
    cvar_loss = -torch.mean(worst_pnl)
    return cvar_loss

def parse_occ_symbol(symbol):
    match = re.search(r"(\d{2})(\d{2})(\d{2})([CP])(\d{8})$", symbol)
    if not match:
        nifty_match = re.search(r"NIFTY(\d{2})([0-9A-Z]+)(\d{5})(CE|PE)$", symbol)
        if nifty_match:
            yy, date_part, strike_raw, cp = nifty_match.groups()
            expiry = datetime(2026, 2, 26, 16, 0, tzinfo=timezone.utc)
            strike = float(strike_raw)
            opt_type = 'CALL' if cp == 'CE' else 'PUT'
            return expiry, strike, opt_type
        return None, None, None
    yy, mm, dd, cp, strike_raw = match.groups()
    year = 2000 + int(yy) if int(yy) < 80 else 1900 + int(yy)
    expiry = datetime(year, int(mm), int(dd), 16, 0, tzinfo=timezone.utc)
    strike = int(strike_raw) / 1000.0
    opt_type = 'CALL' if cp == 'C' else 'PUT'
    return expiry, strike, opt_type

def implied_volatility_approx(spot, strike, dte, price, is_call=True):
    if dte <= 0.0 or spot <= 0.0 or price <= 0.0:
        return 0.20
    try:
        val = (price / spot) * np.sqrt(2 * np.pi / dte)
        return float(np.clip(val, 0.05, 0.80))
    except:
        return 0.20

def generate_synthetic_paths(num_paths=1500, path_len=30):
    print(f"Generating {num_paths} synthetic Heston + Merton Jump Diffusion paths...")
    paths_collected = []
    dt = 1.0 / 252.0
    
    kappa = 2.0
    theta = 0.09
    xi = 0.3
    rho = -0.7
    
    jump_lambda = 0.1
    mu_J = -0.05
    sigma_J = 0.1
    
    for _ in range(num_paths):
        S0 = np.random.uniform(50.0, 500.0)
        strike = S0 * np.random.uniform(0.9, 1.1)
        V0 = np.random.uniform(0.04, 0.16)
        dte0 = np.random.uniform(10.0, 60.0) / 365.25
        
        S_seq = [S0]
        V_seq = [V0]
        
        for t in range(path_len):
            Z1 = np.random.normal()
            Z2 = np.random.normal()
            W_S = Z1
            W_V = rho * Z1 + np.sqrt(1.0 - rho**2) * Z2
            
            V_prev = V_seq[-1]
            dV = kappa * (theta - V_prev) * dt + xi * np.sqrt(max(1e-5, V_prev)) * np.sqrt(dt) * W_V
            V_next = max(1e-4, V_prev + dV)
            V_seq.append(V_next)
            
            jump = 0.0
            if np.random.uniform() < (jump_lambda * dt):
                jump = np.random.normal(mu_J, sigma_J)
                
            S_prev = S_seq[-1]
            drift = 0.05 * dt
            diffusion = np.sqrt(V_prev) * np.sqrt(dt) * W_S
            S_next = S_prev + S_prev * (drift + diffusion)
            if jump != 0.0:
                S_next = S_next * math.exp(jump)
            S_seq.append(max(1.0, S_next))
            
        C_seq = []
        DTE_seq = []
        IV_seq = []
        for t in range(path_len + 1):
            dte_t = max(0.0001, dte0 - t * dt)
            DTE_seq.append(dte_t)
            curr_vol = math.sqrt(V_seq[t])
            
            d1 = (math.log(S_seq[t] / strike) + (0.05 + 0.5 * curr_vol**2) * dte_t) / (curr_vol * math.sqrt(dte_t))
            d2 = d1 - curr_vol * math.sqrt(dte_t)
            cdf_d1 = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
            cdf_d2 = 0.5 * (1.0 + math.erf(d2 / math.sqrt(2.0)))
            c_price = S_seq[t] * cdf_d1 - strike * math.exp(-0.05 * dte_t) * cdf_d2
            C_seq.append(max(0.01, c_price))
            IV_seq.append(curr_vol)
            
        paths_collected.append({
            'S': torch.tensor(S_seq, dtype=torch.float32),
            'C': torch.tensor(C_seq, dtype=torch.float32),
            'IV': torch.tensor(IV_seq, dtype=torch.float32),
            'DTE': torch.tensor(DTE_seq, dtype=torch.float32),
            'strike': strike
        })
    return paths_collected

def load_real_paths():
    print("Loading option parquet and CSV data...")
    paths_collected = []
    data_root = "c:\\Users\\User\\Desktop\\Affinity-Core\\data"
    if os.path.exists(data_root):
        ticker_dirs = [os.path.join(data_root, d) for d in os.listdir(data_root) if os.path.isdir(os.path.join(data_root, d)) and d != "temp"]
        for t_dir in ticker_dirs:
            parquet_files = []
            for root, _, files in os.walk(t_dir):
                for f in files:
                    if f.endswith(".parquet"):
                        parquet_files.append(os.path.join(root, f))
            parquet_files = sorted(parquet_files)[:10]  # speed up training load
            for f_path in parquet_files:
                try:
                    df = pd.read_parquet(f_path)
                    unique_syms = df['symbol'].unique()
                    for sym_raw in unique_syms[:50]:
                        sym = str(sym_raw)
                        expiry, strike, opt_type = parse_occ_symbol(sym)
                        if not expiry or strike is None:
                            continue
                        contract_df = df[df['symbol'] == sym_raw].sort_values('ts_recv')
                        if len(contract_df) < 31:
                            continue
                        spots = ((contract_df['underlying_bid_px'] + contract_df['underlying_ask_px']) / 2.0).values
                        opt_prices = ((contract_df['bid_px'] + contract_df['ask_px']) / 2.0).values
                        ts_recvs = contract_df['ts_recv'].values
                        
                        path_len = 30
                        for offset in range(0, len(spots) - path_len - 1, 10):
                            S_seq = spots[offset : offset + path_len + 1]
                            C_seq = opt_prices[offset : offset + path_len + 1]
                            t_seq = ts_recvs[offset : offset + path_len + 1]
                            
                            if np.any(S_seq <= 0.0) or np.any(C_seq <= 0.0):
                                continue
                                
                            IV_seq = []
                            DTE_seq = []
                            for t_idx in range(path_len + 1):
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
                except Exception as e:
                    print(f"Error loading parquet {f_path}: {e}")
                    
    root_dir = "c:\\Users\\User\\Desktop\\Affinity-Core"
    csv_files = [os.path.join(root_dir, f) for f in os.listdir(root_dir) if f.endswith(".csv") and "option_minute_prices" in f]
    for csv_path in csv_files:
        try:
            print(f"Loading options CSV {csv_path}...")
            df = pd.read_csv(csv_path)
            fut_sym = [s for s in df['symbol'].unique() if "FUT" in str(s)]
            if not fut_sym:
                continue
            fut_df = df[df['symbol'] == fut_sym[0]].sort_values('minute_end')
            spots_map = dict(zip(fut_df['minute_end'], fut_df['last_trade_price']))
            
            opt_symbols = [s for s in df['symbol'].unique() if "FUT" not in str(s)]
            for sym in opt_symbols[:50]:
                expiry, strike, opt_type = parse_occ_symbol(str(sym))
                if not expiry or strike is None:
                    continue
                contract_df = df[df['symbol'] == sym].sort_values('minute_end')
                if len(contract_df) < 31:
                    continue
                spots = []
                opt_prices = []
                for _, row in contract_df.iterrows():
                    m = row['minute_end']
                    if m in spots_map:
                        spots.append(spots_map[m])
                        opt_prices.append(row['last_trade_price'])
                if len(spots) < 31:
                    continue
                
                path_len = 30
                for offset in range(0, len(spots) - path_len - 1, 10):
                    S_seq = spots[offset : offset + path_len + 1]
                    C_seq = opt_prices[offset : offset + path_len + 1]
                    
                    IV_seq = []
                    DTE_seq = []
                    for t_idx in range(path_len + 1):
                        curr_dte = max(0.0001, (22.0 - t_idx) / 365.25)
                        DTE_seq.append(curr_dte)
                        IV_seq.append(implied_volatility_approx(S_seq[t_idx], strike, curr_dte, C_seq[t_idx]))
                        
                    paths_collected.append({
                        'S': torch.tensor(S_seq, dtype=torch.float32),
                        'C': torch.tensor(C_seq, dtype=torch.float32),
                        'IV': torch.tensor(IV_seq, dtype=torch.float32),
                        'DTE': torch.tensor(DTE_seq, dtype=torch.float32),
                        'strike': strike
                    })
        except Exception as e:
            print(f"Error loading CSV {csv_path}: {e}")
            
    print(f"Successfully constructed {len(paths_collected)} real option paths!")
    return paths_collected

class ResidualBlock(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.fc = nn.Linear(dim, dim)
        self.relu = nn.ReLU()
    def forward(self, x):
        return x + self.relu(self.fc(x))

class FFNNHedgerV2(nn.Module):
    def __init__(self, input_dim=5):
        super(FFNNHedgerV2, self).__init__()
        self.in_proj = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU()
        )
        self.res1 = ResidualBlock(64)
        self.res2 = ResidualBlock(64)
        self.out_proj = nn.Sequential(
            nn.Linear(64, 1),
            nn.Sigmoid()
        )
        
    def forward(self, x):
        x_norm = x.clone()
        x_norm[..., 0] = x[..., 1] + 1.0
        h = self.in_proj(x_norm)
        h = self.res1(h)
        h = self.res2(h)
        return self.out_proj(h)

class LSTMHedgerV2(nn.Module):
    def __init__(self, input_dim=5, hidden_dim=32):
        super(LSTMHedgerV2, self).__init__()
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

def main():
    paths = load_real_paths()
    synthetic_paths = generate_synthetic_paths(num_paths=1500)
    paths.extend(synthetic_paths)
    
    S_tensor = torch.stack([p['S'] for p in paths])
    C_tensor = torch.stack([p['C'] for p in paths])
    IV_tensor = torch.stack([p['IV'] for p in paths])
    DTE_tensor = torch.stack([p['DTE'] for p in paths])
    K_tensor = torch.tensor([p['strike'] for p in paths], dtype=torch.float32).unsqueeze(1)
    
    epochs = 15  # 15 epochs for fast training verification
    cost_rate = 0.0005
    num_steps = 30
    batch_size = 512
    num_samples = len(paths)
    
    # 1. Train FFNN V2
    print("--- Training FFNN V2 ---")
    ffnn = FFNNHedgerV2(input_dim=5)
    optimizer = optim.Adam(ffnn.parameters(), lr=0.01)
    for epoch in range(epochs):
        ffnn.train()
        indices = torch.randperm(num_samples)
        epoch_loss = 0.0
        for idx in range(0, num_samples, batch_size):
            batch_idx = indices[idx : idx + batch_size]
            b_S = S_tensor[batch_idx]
            b_C = C_tensor[batch_idx]
            b_IV = IV_tensor[batch_idx]
            b_DTE = DTE_tensor[batch_idx]
            b_K = K_tensor[batch_idx]
            
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
            
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * b_size
        print(f"Epoch {epoch+1}/{epochs}, Loss: {epoch_loss / num_samples:.4f}")
        
    os.makedirs("models", exist_ok=True)
    traced_ffnn = torch.jit.trace(ffnn, torch.randn(2, 5))
    traced_ffnn.save("models/deep_hedge_ffnn_v2.pt")
    print("Saved models/deep_hedge_ffnn_v2.pt")
    
    # 2. Train LSTM V2
    print("--- Training LSTM V2 ---")
    lstm_model = LSTMHedgerV2(input_dim=5)
    optimizer = optim.Adam(lstm_model.parameters(), lr=0.01)
    for epoch in range(epochs):
        lstm_model.train()
        indices = torch.randperm(num_samples)
        epoch_loss = 0.0
        for idx in range(0, num_samples, batch_size):
            batch_idx = indices[idx : idx + batch_size]
            b_S = S_tensor[batch_idx]
            b_C = C_tensor[batch_idx]
            b_IV = IV_tensor[batch_idx]
            b_DTE = DTE_tensor[batch_idx]
            b_K = K_tensor[batch_idx]
            
            b_size = len(batch_idx)
            deltas = torch.zeros(b_size, num_steps + 1)
            delta_prev = torch.zeros(b_size, 1)
            for t in range(num_steps):
                S_t = b_S[:, t:t+1]
                strike_dist = (S_t / b_K) - 1.0
                dte_t = b_DTE[:, t:t+1]
                iv_t = b_IV[:, t:t+1]
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
            
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * b_size
        print(f"Epoch {epoch+1}/{epochs}, Loss: {epoch_loss / num_samples:.4f}")
        
    traced_lstm = torch.jit.trace(lstm_model, torch.randn(2, 1, 5))
    traced_lstm.save("models/deep_hedge_lstm_v2.pt")
    print("Saved models/deep_hedge_lstm_v2.pt")
    
    # 3. Train Adversarial V2
    print("--- Training Adversarial V2 ---")
    adv_hedger = FFNNHedgerV2(input_dim=5)
    adversary = MarketGenerator(input_dim=2)
    opt_hedger = optim.Adam(adv_hedger.parameters(), lr=0.01)
    opt_adversary = optim.Adam(adversary.parameters(), lr=0.003)
    for epoch in range(epochs):
        adv_hedger.train()
        adversary.train()
        indices = torch.randperm(num_samples)
        epoch_loss = 0.0
        for idx in range(0, num_samples, batch_size):
            batch_idx = indices[idx : idx + batch_size]
            b_S = S_tensor[batch_idx].clone()
            b_C = C_tensor[batch_idx].clone()
            b_IV = IV_tensor[batch_idx].clone()
            b_DTE = DTE_tensor[batch_idx]
            b_K = K_tensor[batch_idx]
            
            b_size = len(batch_idx)
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
                
            batch_S = torch.stack(S_list, dim=1)
            batch_IV = torch.stack(IV_list, dim=1)
            
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
            
            opt_hedger.zero_grad()
            opt_adversary.zero_grad()
            loss.backward()
            opt_hedger.step()
            for param in adversary.parameters():
                if param.grad is not None:
                    param.grad.data.mul_(-1.0)
            opt_adversary.step()
            epoch_loss += loss.item() * b_size
        print(f"Epoch {epoch+1}/{epochs}, Loss: {epoch_loss / num_samples:.4f}")
        
    traced_adv = torch.jit.trace(adv_hedger, torch.randn(2, 5))
    traced_adv.save("models/deep_hedge_adversarial_v2.pt")
    print("Saved models/deep_hedge_adversarial_v2.pt")
    print("--- ALL V2 MODELS TRAINED AND EXPORTED SUCCESSFULLY ---")

if __name__ == "__main__":
    main()
