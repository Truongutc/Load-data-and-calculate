import pandas as pd
import numpy as np
import sys
import os

sys.path.append('e:/projects/Codeinvest/Codeinvest')
from tinvest.advanced_entry import classify_entry

# Create dummy data
np.random.seed(42)
dates = pd.date_range('2023-01-01', periods=250)
data = {
    'Date': dates,
    'Open': np.random.uniform(10, 20, 250),
    'High': np.random.uniform(15, 25, 250),
    'Low': np.random.uniform(5, 15, 250),
    'Close': np.random.uniform(10, 20, 250),
    'Volume': np.random.uniform(1000, 5000, 250)
}
df = pd.DataFrame(data)

# Test the classification
try:
    res = classify_entry(df)
    print("Classification Result:", res)
    print("Test Passed: No exceptions thrown.")
except Exception as e:
    print(f"Test Failed: {e}")
    import traceback
    traceback.print_exc()
