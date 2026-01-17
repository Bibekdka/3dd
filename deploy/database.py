import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import streamlit as st
import json

# SCOPE for Google API
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_connection():
    """Authenticates with Google Sheets using Env Vars (Render) or Secrets (Local)."""
    
    # 1. Try loading from Render Environment Variable (JSON String)
    import os
    if "gcp_service_account" in os.environ:
        # We need to parse the JSON string back into a dictionary
        creds_dict = json.loads(os.environ["gcp_service_account"])
        
    # 2. Try loading from local .streamlit/secrets.toml
    elif "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        
    else:
        raise ValueError("❌ GCP Credentials not found! Check Render Environment Variables.")

    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open("printer_brain").sheet1
    return sheet

def init_db():
    """Checks if headers exist, if not adds them."""
    try:
        sheet = get_connection()
        if not sheet: return
        headers = sheet.row_values(1)
        if not headers:
            sheet.append_row([
                "id", "timestamp", "type", "name", "details", 
                "cost_inr", "print_status", "ai_summary", "tags", "full_json"
            ])
    except Exception as e:
        print(f"DB Error: {e}")

def add_entry(entry_type, name, details, cost=0.0, ai_summary="", tags="", full_json=""):
    try:
        sheet = get_connection()
        if not sheet: return False
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Generate a simple ID based on number of rows
        all_vals = sheet.get_all_values()
        next_id = len(all_vals)
        
        row = [
            next_id, timestamp, entry_type, name, details, 
            cost, "Pending", ai_summary, tags, str(full_json)
        ]
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"Failed to save to Cloud: {e}")
        return False

def load_history():
    """Loads data from Sheet into DataFrame."""
    try:
        sheet = get_connection()
        if not sheet: return pd.DataFrame(columns=["id", "timestamp", "type", "name", "details", "print_status", "ai_summary", "tags"])
        
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        # Sort by ID descending (newest first)
        if not df.empty and "id" in df.columns:
            df = df.sort_values(by="id", ascending=False)
        return df
    except Exception:
        return pd.DataFrame(columns=["id", "timestamp", "type", "name", "details", "print_status", "ai_summary", "tags"])

def update_print_status(row_id, status):
    """Finds the row with matching ID and updates status."""
    try:
        sheet = get_connection()
        if not sheet: return False
        # Find cell with the ID
        cell = sheet.find(str(row_id))
        # Update the 'print_status' column (Column G, which is index 7)
        sheet.update_cell(cell.row, 7, status)
        return True
    except Exception as e:
        print(f"Update Error: {e}")
        return False

def get_learning_context():
    """Fetches past failures from the Sheet."""
    df = load_history()
    if df.empty: return "No recorded failures yet."
    
    # Filter for failures
    if 'print_status' in df.columns and 'details' in df.columns:
        failures = df[
            (df['print_status'] == 'Do Not Print') | 
            (df['details'].str.contains('fail', case=False, na=False))
        ].head(5)
        
        if failures.empty: return "No recent failures."
        
        context = "USER'S PAST FAILURES (WARNINGS):\n"
        for _, row in failures.iterrows():
            context += f"- Model: {row['name']} | Issues: {row.get('ai_summary', '')} | Tags: {row.get('tags', '')}\n"
        return context
    return "No history available."

def get_db_stats():
    df = load_history()
    if df.empty: return {"total": 0, "success_rate": 0, "top_tags": []}
    
    if 'print_status' not in df.columns or 'tags' not in df.columns:
        return {"total": len(df), "success_rate": 0, "top_tags": []}

    success = len(df[df['print_status'] == 'Success'])
    total = len(df)
    rate = round((success/total)*100, 1) if total > 0 else 0
    
    # Simple tag counting
    all_tags = " ".join(df['tags'].astype(str)).replace("#", "").split()
    from collections import Counter
    top_tags = Counter(all_tags).most_common(5)
    
    return {"total": total, "success_rate": rate, "top_tags": top_tags}
