import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Load data
df = pd.read_csv("live_data.csv")

# Extract stock price
stock_c = df["StockE_Price"]

# Define momentum window (e.g., 50-period moving average)
lookback = 10

# Compute rolling moving average
df["rolling_mean"] = stock_c.rolling(window=lookback).mean()

# Define trading signals
df["signal"] = np.where(stock_c > df["rolling_mean"], -1, 1)  # 1 = Buy, -1 = Sell

# Simulate trading: Calculate returns
df["stockC_future"] = stock_c.shift(-1)  # Future price
df["returns"] = df["signal"] * (df["stockC_future"] - stock_c) / stock_c  # Strategy returns

# Compute cumulative returns
df["cumulative_returns"] = df["returns"].cumsum()

# Plot strategy performance
plt.figure(figsize=(10, 5))
plt.plot(df["cumulative_returns"], label="Momentum Strategy", color="blue")
plt.axhline(0, color="black", linestyle="--")
plt.title(f"Momentum Strategy Backtest (Lookback={lookback})")
plt.xlabel("Time")
plt.ylabel("Cumulative Returns")
plt.legend()
plt.grid()
plt.show()

# Print total returns
total_return = df["cumulative_returns"].iloc[-1]
print(f"Total Return: {total_return * 100:.2f}%")

# Check Sharpe Ratio (risk-adjusted return)
sharpe_ratio = df["returns"].mean() / df["returns"].std()
print(f"Sharpe Ratio: {sharpe_ratio:.2f}")