import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "dashboard.db")

def get_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = get_db()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, created_at REAL,
            tb_host TEXT, device_id TEXT, time_range TEXT
        );
        CREATE TABLE IF NOT EXISTS agent_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT, agent_name TEXT,
            status TEXT, message TEXT, created_at REAL
        );
    """)
    c.commit()
    c.close()

def log_agent(sid, name, status, msg):
    c = get_db()
    c.execute(
        "INSERT INTO agent_logs (session_id,agent_name,status,message,created_at) VALUES (?,?,?,?,?)",
        (sid, name, status, msg, time.time())
    )
    c.commit()
    c.close()
