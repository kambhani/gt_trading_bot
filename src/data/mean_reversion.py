import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import adfuller
import statsmodels.api as sm

# Load data
df = pd.read_csv("live_data.csv")

# Extract stock price series
stock_c = df["StockB_Price"]

# Run Augmented Dickey-Fuller test
adf_result = adfuller(stock_c)

# Print ADF test results
print("Augmented Dickey-Fuller Test Results:")
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

# -----------------------------------
# Calculate Half-Life of Mean Reversion
# -----------------------------------
def half_life(series):
    """Estimate half-life using an Ornstein-Uhlenbeck process regression."""
    series_lag = series.shift(1).dropna()
    delta_series = series.diff().dropna()

    model = sm.OLS(delta_series, sm.add_constant(series_lag)).fit()
    lambda_value = model.params[1]  # Speed of mean reversion

    half_life_value = -np.log(2) / lambda_value
    return half_life_value

hl = half_life(stock_c)

print(f"Estimated Half-Life of Mean Reversion: {hl:.2f} time steps")

# Interpretation
if hl > 0 and hl < len(stock_c) / 2:
    print("StockC_Price exhibits mean-reverting behavior with a reasonable half-life.")
else:
    print("StockC_Price does not exhibit strong mean-reversion.")