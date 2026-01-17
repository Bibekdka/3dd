import sqlite3
import pandas as pd
from datetime import datetime
import os

DB_FILE = "printer_brain.db"

def init_db():
    """Initialize the database with a robust schema."""
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
    """Adds a new entry with AI-generated tags."""
    init_db() # Ensure DB exists
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
    """Loads history into a Pandas DataFrame for the UI."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM history ORDER BY id DESC", conn)
    conn.close()
    return df

def update_print_status(row_id, status):
    """Updates status (e.g., 'Printed', 'Failed')."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE history SET print_status = ? WHERE id = ?", (status, row_id))
    conn.commit()
    conn.close()

def get_learning_context():
    """
    THE BRAIN: Searches past history for 'Failures' or 'Warnings' 
    to teach the AI about your specific printer struggles.
    """
    init_db()
    conn = sqlite3.connect(DB_FILE)
    # Look for items marked 'Do Not Print' or containing 'Failed' in details
    query = """
        SELECT name, ai_summary, tags FROM history 
        WHERE print_status = 'Do Not Print' 
        OR details LIKE '%fail%' 
        ORDER BY id DESC LIMIT 5
    """
    try:
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            return "No recorded failures yet."
            
        context = "USER'S PAST FAILURES (LEARN FROM THESE):\n"
        for _, row in df.iterrows():
            context += f"- Model: {row['name']} | Issues: {row['ai_summary']} | Tags: {row['tags']}\n"
        return context
    except:
        return ""
