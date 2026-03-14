import os
import sqlite3
import time
import psycopg2
from psycopg2.extras import DictCursor
from config import DATABASE_URL

def get_db():
    if DATABASE_URL:
        # Use PostgreSQL (Neon)
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        # Fallback to SQLite
        db_path = os.path.join(os.path.dirname(__file__), "dashboard.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    if DATABASE_URL:
        # PostgreSQL syntax
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE,
                password_hash TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, 
                created_at DOUBLE PRECISION,
                tb_host TEXT, 
                device_id TEXT, 
                time_range TEXT
            );
            CREATE TABLE IF NOT EXISTS agent_logs (
                id SERIAL PRIMARY KEY,
                session_id TEXT, 
                agent_name TEXT,
                status TEXT, 
                message TEXT, 
                created_at DOUBLE PRECISION
            );
            CREATE TABLE IF NOT EXISTS dashboards (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                name TEXT,
                config TEXT,
                created_at DOUBLE PRECISION,
                share_token TEXT UNIQUE,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
        """)
    else:
        # SQLite syntax
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                password_hash TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, created_at REAL,
                tb_host TEXT, device_id TEXT, time_range TEXT
            );
            CREATE TABLE IF NOT EXISTS agent_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT, agent_name TEXT,
                status TEXT, message TEXT, created_at REAL
            );
            CREATE TABLE IF NOT EXISTS dashboards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                config TEXT,
                created_at REAL,
                share_token TEXT UNIQUE,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
        """)
    conn.commit()
    cur.close()
    conn.close()

def log_agent(sid, name, status, msg):
    conn = get_db()
    cur = conn.cursor()
    placeholder = "%s" if DATABASE_URL else "?"
    cur.execute(
        f"INSERT INTO agent_logs (session_id,agent_name,status,message,created_at) VALUES ({placeholder},{placeholder},{placeholder},{placeholder},{placeholder})",
        (sid, name, status, msg, time.time())
    )
    conn.commit()
    cur.close()
    conn.close()

def create_user(email, password_hash):
    conn = get_db()
    cur = conn.cursor()
    placeholder = "%s" if DATABASE_URL else "?"
    try:
        cur.execute(f"INSERT INTO users (email, password_hash) VALUES ({placeholder}, {placeholder})",
                  (email, password_hash))
        conn.commit()
        return True
    except (sqlite3.IntegrityError, psycopg2.IntegrityError):
        return False
    finally:
        cur.close()
        conn.close()

def get_user_by_email(email):
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor) if DATABASE_URL else conn.cursor()
    placeholder = "%s" if DATABASE_URL else "?"
    cur.execute(f"SELECT * FROM users WHERE email = {placeholder}", (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def get_user_by_id(user_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor) if DATABASE_URL else conn.cursor()
    placeholder = "%s" if DATABASE_URL else "?"
    cur.execute(f"SELECT * FROM users WHERE id = {placeholder}", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def save_session(sid, created_at, host, device_id, time_range):
    conn = get_db()
    cur = conn.cursor()
    if DATABASE_URL:
        # PostgreSQL: Use ON CONFLICT
        cur.execute("""
            INSERT INTO sessions (id, created_at, tb_host, device_id, time_range)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                created_at = EXCLUDED.created_at,
                tb_host = EXCLUDED.tb_host,
                device_id = EXCLUDED.device_id,
                time_range = EXCLUDED.time_range
        """, (sid, created_at, host, device_id, time_range))
    else:
        # SQLite: Use INSERT OR REPLACE
        cur.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?)",
                  (sid, created_at, host, device_id, time_range))
    conn.commit()
    cur.close()
    conn.close()

def get_session_logs(session_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor) if DATABASE_URL else conn.cursor()
    placeholder = "%s" if DATABASE_URL else "?"
    cur.execute(
        f"SELECT agent_name, status, message, created_at FROM agent_logs "
        f"WHERE session_id = {placeholder} ORDER BY created_at", (session_id,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

def save_dashboard(user_id, name, config, share_token):
    conn = get_db()
    cur = conn.cursor()
    placeholder = "%s" if DATABASE_URL else "?"
    
    # Check if dashboard with same name exists for this user
    cur.execute(f"SELECT id FROM dashboards WHERE user_id = {placeholder} AND name = {placeholder}", (user_id, name))
    existing = cur.fetchone()
    
    if existing:
        idx = existing[0] if isinstance(existing, tuple) else existing["id"]
        cur.execute(f"UPDATE dashboards SET config = {placeholder}, share_token = {placeholder} WHERE id = {placeholder}", 
                    (config, share_token, idx))
        dashboard_id = idx
    else:
        if DATABASE_URL:
            cur.execute("""
                INSERT INTO dashboards (user_id, name, config, created_at, share_token) 
                VALUES (%s, %s, %s, %s, %s) RETURNING id
            """, (user_id, name, config, time.time(), share_token))
            dashboard_id = cur.fetchone()[0]
        else:
            cur.execute("""
                INSERT INTO dashboards (user_id, name, config, created_at, share_token) 
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, name, config, time.time(), share_token))
            dashboard_id = cur.lastrowid
            
    conn.commit()
    cur.close()
    conn.close()
    return dashboard_id

def get_dashboards(user_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor) if DATABASE_URL else conn.cursor()
    placeholder = "%s" if DATABASE_URL else "?"
    cur.execute(
        f"SELECT id, name, created_at, share_token FROM dashboards "
        f"WHERE user_id = {placeholder} ORDER BY created_at DESC", (user_id,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

def get_dashboard(dashboard_id, user_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor) if DATABASE_URL else conn.cursor()
    placeholder = "%s" if DATABASE_URL else "?"
    cur.execute(
        f"SELECT * FROM dashboards WHERE id = {placeholder} AND user_id = {placeholder}", 
        (dashboard_id, user_id)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None

def get_dashboard_by_token(token):
    conn = get_db()
    cur = conn.cursor(cursor_factory=DictCursor) if DATABASE_URL else conn.cursor()
    placeholder = "%s" if DATABASE_URL else "?"
    cur.execute(
        f"SELECT d.*, u.email as owner_email FROM dashboards d "
        f"JOIN users u ON d.user_id = u.id "
        f"WHERE d.share_token = {placeholder}", 
        (token,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None

def delete_dashboard(dashboard_id, user_id):
    conn = get_db()
    cur = conn.cursor()
    placeholder = "%s" if DATABASE_URL else "?"
    cur.execute(
        f"DELETE FROM dashboards WHERE id = {placeholder} AND user_id = {placeholder}", 
        (dashboard_id, user_id)
    )
    conn.commit()
    cur.close()
    conn.close()
    return True
