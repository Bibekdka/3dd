import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import streamlit as st
import json
import os
from collections import Counter

# SETUP SCOPE
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_connection():
    """
    Connects to Google Sheets using Streamlit Secrets (Local) OR Env Vars (Render).
    """
    try:
        creds_dict = None
        
        # 1. Try Streamlit Secrets (Local Testing)
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            
        # 2. Try Environment Variables (Render / Cloud Deployment)
        elif "gcp_service_account" in os.environ:
            try:
                creds_dict = json.loads(os.environ["gcp_service_account"])
            except json.JSONDecodeError as e:
                print(f"❌ JSON Error in Env Var: {e}")
                return None

        if not creds_dict:
            print("❌ No credentials found in secrets.toml or Environment Variables.")
            return None

        # Authorize
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        
        # Open the sheet
        sheet = client.open("printer_brain").sheet1
        return sheet

    except Exception as e:
        print(f"❌ Connection Error: {e}")
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
            if not sheet.row_values(1):
                headers = ["id", "timestamp", "type", "name", "details", "cost_inr", "print_status", "ai_summary", "tags", "full_json"]
                sheet.append_row(headers)
        except: pass

def add_entry(entry_type, name, details, cost=0.0, ai_summary="", tags="", full_json=""):
    sheet = get_connection()
    if not sheet: return False
    
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_id = len(sheet.get_all_values()) 
        row = [new_id, timestamp, entry_type, name, details, cost, "Pending", ai_summary, tags, str(full_json)]
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
            df = df.sort_values(by="id", ascending=False)
        return df
    except: return pd.DataFrame()

def update_print_status(row_id, status):
    sheet = get_connection()
    if not sheet: return False
    try:
        cell = sheet.find(str(row_id))
        sheet.update_cell(cell.row, 7, status) # Column 7 is print_status
        return True
    except: return False

def get_learning_context():
    df = load_history()
    if df.empty: return "No recorded failures yet."
    failures = df[(df['print_status'] == 'Do Not Print') | (df['details'].str.contains('fail', case=False, na=False))].head(5)
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
    
    all_tags = " ".join(df['tags'].astype(str)).replace("#", "").split()
    top_tags = Counter(all_tags).most_common(5)
    
    return {"total": total, "success_rate": rate, "top_tags": top_tags}
