import sqlite3
import pandas as pd
from datetime import datetime
import os
from collections import Counter

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
            cost_inr REAL,
            print_status TEXT,
            ai_summary TEXT,
            tags TEXT,
            full_json TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_entry(entry_type, name, details, cost=0.0, ai_summary="", tags="", full_json=""):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT INTO history (timestamp, type, name, details, cost_inr, print_status, ai_summary, tags, full_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (timestamp, entry_type, name, details, cost, "Pending", ai_summary, tags, str(full_json)))
    conn.commit()
    conn.close()
    return True

def load_history():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM history ORDER BY id DESC", conn)
    conn.close()
    return df

def update_print_status(row_id, status):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE history SET print_status = ? WHERE id = ?", (status, row_id))
    conn.commit()
    conn.close()

def get_learning_context():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    # Fetch failures to warn the user
    query = "SELECT name, ai_summary, tags FROM history WHERE print_status = 'Do Not Print' OR details LIKE '%fail%' ORDER BY id DESC LIMIT 5"
    try:
        df = pd.read_sql_query(query, conn)
        conn.close()
        if df.empty: return "No recorded failures yet."
        context = "USER'S PAST FAILURES (LEARN FROM THESE):\n"
        for _, row in df.iterrows():
            context += f"- Model: {row['name']} | Issues: {row['ai_summary']} | Tags: {row['tags']}\n"
        return context
    except: return ""

def get_db_stats():
    """
    New: Generates statistics for the Dashboard.
    """
    init_db()
    conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql_query("SELECT * FROM history", conn)
        conn.close()
        
        if df.empty:
            return {"total": 0, "success_rate": 0, "top_tags": [], "recent_failures": []}
        
        # Calculate Stats
        total = len(df)
        success_count = len(df[df['print_status'] == 'Success'])
        failure_count = len(df[df['print_status'] == 'Do Not Print'])
        rate = round((success_count / total) * 100, 1) if total > 0 else 0
        
        # Analyze Tags
        all_tags = " ".join(df['tags'].dropna().astype(str)).replace("#", "").replace(",", " ").split()
        top_tags = Counter(all_tags).most_common(5)
        
        # Recent Failures
        failures = df[df['print_status'] == 'Do Not Print'].head(5)[['name', 'tags']].to_dict('records')
        
        return {
            "total": total,
            "success": success_count,
            "failed": failure_count,
            "success_rate": rate,
            "top_tags": top_tags,
            "recent_failures": failures
        }
    except:
        conn.close()
        return {"total": 0, "success_rate": 0, "top_tags": [], "recent_failures": []}
