import pandas as pd
import os
import time
from datetime import datetime
import shutil

HISTORY_FILE = "history.csv"

def load_history():
    """Loads history from CSV. Returns empty DF if new."""
    if os.path.exists(HISTORY_FILE):
        try:
            df = pd.read_csv(HISTORY_FILE)
            # Ensure columns exist
            expected_cols = ["Timestamp", "Type", "Name", "Details", "Cost_INR", "PrintStatus", "AISummary", "FullDetails"]
            for col in expected_cols:
                if col not in df.columns:
                    df[col] = ""
            return df
        except Exception:
            # If CSV is corrupted, return empty
            return pd.DataFrame(columns=["Timestamp", "Type", "Name", "Details", "Cost_INR", "PrintStatus", "AISummary", "FullDetails"])
    else:
        return pd.DataFrame(columns=["Timestamp", "Type", "Name", "Details", "Cost_INR", "PrintStatus", "AISummary", "FullDetails"])

def add_history_entry(entry_type, name, details, cost=0.0, ai_summary="", full_details=""):
    """Adds a new entry to the history CSV using atomic write to prevent corruption."""
    try:
        # Load existing history
        df = load_history()
        
        # Create new entry
        new_entry = {
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Type": entry_type,
            "Name": name,
            "Details": details,
            "Cost_INR": round(cost, 2),
            "PrintStatus": "Pending",
            "AISummary": ai_summary,
            "FullDetails": full_details
        }
        
        # Append new entry
        df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
        
        # Atomic Write Strategy: Write to .tmp then rename
        tmp_file = HISTORY_FILE + ".tmp"
        df.to_csv(tmp_file, index=False)
        
        # Windows-safe atomic replace
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
        os.rename(tmp_file, HISTORY_FILE)
            
        return True
    except Exception as e:
        print(f"Error saving history: {e}")
        return False

def update_print_status(index, status):
    """Updates the print status of a history entry by index."""
    try:
        df = load_history()
        if 0 <= index < len(df):
            df.at[index, "PrintStatus"] = status
            
            # Atomic Write Strategy
            tmp_file = HISTORY_FILE + ".tmp"
            df.to_csv(tmp_file, index=False)
            
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)
            os.rename(tmp_file, HISTORY_FILE)
            
            return True
        return False
    except Exception as e:
        print(f"Error updating print status: {e}")
        return False
