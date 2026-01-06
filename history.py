import pandas as pd
import os
import time
from datetime import datetime

HISTORY_FILE = "history.csv"

def load_history():
    """Lengths history from CSV. Returns empty DF if new."""
    if os.path.exists(HISTORY_FILE):
        return pd.read_csv(HISTORY_FILE)
    else:
        return pd.DataFrame(columns=["Timestamp", "Type", "Name", "Details", "Cost_INR"])

def add_history_entry(entry_type, name, details, cost=0.0):
    """Adds a new entry to the history CSV."""
    try:
        time.sleep(0.1)  # crude but effective for MVP
        df = load_history()
        
        new_entry = {
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Type": entry_type,
            "Name": name,
            "Details": details,
            "Cost_INR": round(cost, 2)
        }
        
        # Concat and save
        df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
        df.to_csv(HISTORY_FILE, index=False)
        return True
    except Exception as e:
        print(f"Error saving history: {e}")
        return False
