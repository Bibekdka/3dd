import sqlite3
import pandas as pd
from datetime import datetime
from collections import Counter
import os

# If running on Render, save to /data. If local, save to current folder.
if os.path.exists("/data"):
    DB_FILE = "/data/printer_brain.db"
else:
    DB_FILE = "printer_brain.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            type TEXT,
            name TEXT,
            details TEXT,
            print_status TEXT, 
            ai_summary TEXT,
            tags TEXT,
            full_json TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_entry(entry_type, name, details, ai_summary="", tags="", full_json=""):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO history (timestamp, type, name, details, print_status, ai_summary, tags, full_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (timestamp, entry_type, name, details, "Pending", ai_summary, tags, str(full_json)))
    conn.commit()
    conn.close()

def update_print_status(row_id, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE history SET print_status = ? WHERE id = ?", (status, row_id))
    conn.commit()
    conn.close()

def get_learning_context():
    """Returns past failures to warn the AI."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    query = "SELECT name, ai_summary, tags FROM history WHERE print_status = 'Do Not Print' OR details LIKE '%fail%' ORDER BY id DESC LIMIT 5"
    try:
        df = pd.read_sql_query(query, conn)
        conn.close()
        if df.empty: return "No recorded failures yet."
        context = "USER'S PAST FAILURES (WARNINGS):\n"
        for _, row in df.iterrows():
            context += f"- Model: {row['name']} | Issues: {row['ai_summary']} | Tags: {row['tags']}\n"
        return context
    except: return ""

def get_db_stats():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM history", conn)
    conn.close()
    
    if df.empty: return {"total": 0, "success_rate": 0, "top_tags": []}
    
    success = len(df[df['print_status'] == 'Success'])
    total = len(df)
    rate = round((success/total)*100, 1) if total > 0 else 0
    
    # Extract tags
    all_tags = " ".join(df['tags'].dropna().astype(str)).replace("#", "").split()
    top_tags = Counter(all_tags).most_common(5)
    
    return {"total": total, "success_rate": rate, "top_tags": top_tags}

def load_history():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM history ORDER BY id DESC", conn)
    conn.close()
    return df
