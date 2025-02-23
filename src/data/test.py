import pandas as pd
from statsmodels.tsa.stattools import adfuller
import matplotlib.pyplot as plt
import numpy as np

pd.set_option('display.max_rows', 1000)
pd.set_option('display.max_columns', 1000)

# Load your CSV file
df = pd.read_csv("live_data.csv")
print(len(df.index))

# Select only the price columns
price_columns = [col for col in df.columns if col.endswith("_Price")]
price_df = df[price_columns]

# Compute the correlation matrix
correlation_matrix = price_df.corr()

# Display the correlation matrix
print(correlation_matrix)

# Define the two stock price series
stock_a = df["StockB_Price"]
stock_b = df["StockE_Price"]

# Shift Stock A forward by 346 timesteps
df["stockA_future"] = stock_a.shift(50)

# Compute signals: Only trade if Stock A moves by more than ±2%
threshold = 0.3  # 2% threshold

price_change = (df["stockA_future"] - stock_a) / stock_a  # Percentage change in Stock A
df["signal"] = np.where(price_change > threshold, 1,
                np.where(price_change < -threshold, -1, 0))  # 1 = Buy Stock B, -1 = Short Stock B, 0 = No trade

# Simulate trading: Buy at t, sell at t+346
df["stockB_future"] = stock_b.shift(-346)
df["returns"] = df["signal"] * (df["stockB_future"] - stock_b) / stock_b

# Compute cumulative returns
df["cumulative_returns"] = df["returns"].cumsum()

# Plot results
plt.figure(figsize=(10, 5))
plt.plot(df["cumulative_returns"], label="Cumulative Returns", color="blue")
plt.axhline(0, color="black", linestyle="--")
plt.title("Lead-Lag Trading Strategy Performance")
plt.xlabel("Time")
plt.ylabel("Cumulative Returns")
plt.legend()
plt.grid()
plt.show()

# Print total returns
total_return = df["cumulative_returns"].iloc[-1]
print(f"Total Return: {total_return}%")

'''# Define the maximum number of shifts to test
max_lag = 1000  # You can increase this

# Compute correlations for different lags
lag_correlations = {}
for lag in range(-max_lag, max_lag + 1):
    lag_correlations[lag] = stock_a.corr(stock_b.shift(lag))

# Convert to a DataFrame for easier analysis
lag_df = pd.DataFrame.from_dict(lag_correlations, orient="index", columns=["correlation"])

# Find the lag with the highest absolute correlation
best_lag = lag_df["correlation"].abs().idxmax()
best_corr = lag_df.loc[best_lag, "correlation"]

print(f"Best Lag: {best_lag}, Correlation: {best_corr}")'''
