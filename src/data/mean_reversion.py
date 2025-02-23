import pandas as pd
from statsmodels.tsa.stattools import adfuller

# Load data
df = pd.read_csv("live_data.csv")

# Extract stock price series
stock_c = df["StockE_Price"]

# Run Augmented Dickey-Fuller test
adf_result = adfuller(stock_c)

# Print results
print(f"ADF Statistic: {adf_result[0]}")
print(f"p-value: {adf_result[1]}")
print("Critical Values:")
for key, value in adf_result[4].items():
    print(f"  {key}: {value}")

# Interpretation
if adf_result[1] < 0.05:
    print("StockC_Price is likely mean-reverting (stationary).")
else:
    print("StockC_Price is likely not mean-reverting (non-stationary).")