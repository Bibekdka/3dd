
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import streamlit as st
import json
from collections import Counter

# SETUP SCOPE
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_connection():
    """
    Connects to Google Sheets using Streamlit Secrets.
    """
    try:
        # Load credentials from secrets.toml (Local) or Environment Variables (Render)
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
            client = gspread.authorize(creds)
            # Make sure your Google Sheet is named EXACTLY 'printer_brain'
            sheet = client.open("printer_brain").sheet1
            return sheet
        else:
            return None
    except Exception as e:
        print(f"Connection Error: {e}")
        return None

def check_connection():
    """Simple function to test if the Brain is online."""
    sheet = get_connection()
    return sheet is not None

def init_db():
    """Ensures headers exist in the sheet."""
    sheet = get_connection()
    if sheet:
        try:
            # Check if row 1 is empty
            if not sheet.row_values(1):
                headers = ["id", "timestamp", "type", "name", "details", "cost_inr", "print_status", "ai_summary", "tags", "full_json"]
                sheet.append_row(headers)
        except: pass

def add_entry(entry_type, name, details, cost=0.0, ai_summary="", tags="", full_json=""):
    sheet = get_connection()
    if not sheet: return False
    
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Generate simple ID based on existing rows
        new_id = len(sheet.get_all_values()) 
        
        row = [
            new_id, timestamp, entry_type, name, details, 
            cost, "Pending", ai_summary, tags, str(full_json)
        ]
        sheet.append_row(row)
        return True
    except: return False

def load_history():
    sheet = get_connection()
    if not sheet: return pd.DataFrame()
    
    try:
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if not df.empty:
            # Sort by ID descending so newest is first
            df = df.sort_values(by="id", ascending=False)
        return df
    except: return pd.DataFrame()

def update_print_status(row_id, status):
    sheet = get_connection()
    if not sheet: return False
    
    try:
        # Find the cell with the matching ID
        cell = sheet.find(str(row_id))
        # Update column G (Print Status is usually 7th column)
        sheet.update_cell(cell.row, 7, status)
        return True
    except: return False

def get_learning_context():
    """Fetches past failures from the Sheet."""
    df = load_history()
    if df.empty: return "No recorded failures yet."
    
    # Filter for failures
    failures = df[
        (df['print_status'] == 'Do Not Print') | 
        (df['details'].str.contains('fail', case=False, na=False))
    ].head(5)
    
    if failures.empty: return "No recent failures."
    
    context = "USER'S PAST FAILURES (WARNINGS):\n"
    for _, row in failures.iterrows():
        context += f"- Model: {row['name']} | Issues: {row['ai_summary']} | Tags: {row['tags']}\n"
    return context

def get_db_stats():
    df = load_history()
    if df.empty: return {"total": 0, "success_rate": 0, "top_tags": []}
    
    success = len(df[df['print_status'] == 'Success'])
    total = len(df)
    rate = round((success/total)*100, 1) if total > 0 else 0
    
    # Simple tag counting
    all_tags = " ".join(df['tags'].astype(str)).replace("#", "").split()
    top_tags = Counter(all_tags).most_common(5)
    
    return {"total": total, "success_rate": rate, "top_tags": top_tags}
