import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Transactions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_code TEXT UNIQUE,
            category TEXT,
            amount REAL,
            currency TEXT,
            name TEXT,
            comment TEXT,
            file_path TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME
        )
    ''')

    # Existing installations may have been created before expires_at was added.
    c.execute('PRAGMA table_info(transactions)')
    transaction_columns = {row['name'] for row in c.fetchall()}
    if 'expires_at' not in transaction_columns:
        c.execute('ALTER TABLE transactions ADD COLUMN expires_at DATETIME')
    
    # Old settings table (kept for migration)
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            region_code TEXT PRIMARY KEY,
            req_title TEXT,
            req_value TEXT
        )
    ''')
    
    # New banks table
    c.execute('''
        CREATE TABLE IF NOT EXISTS banks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region_code TEXT,
            name TEXT,
            value TEXT
        )
    ''')
    
    # Admins table
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            chat_id TEXT PRIMARY KEY,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Project settings
    c.execute('''
        CREATE TABLE IF NOT EXISTS project_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            media_url TEXT,
            min_amount REAL
        )
    ''')
    c.execute('PRAGMA table_info(projects)')
    project_columns = {row['name'] for row in c.fetchall()}
    for column, column_type in (
        ('description', 'TEXT'),
        ('media_url', 'TEXT'),
        ('min_amount', 'REAL'),
    ):
        if column not in project_columns:
            c.execute(f'ALTER TABLE projects ADD COLUMN {column} {column_type}')
    
    # Migrate old data if banks table is empty
    c.execute('SELECT COUNT(*) FROM banks')
    if c.fetchone()[0] == 0:
        c.execute('SELECT * FROM settings')
        old_settings = c.fetchall()
        if old_settings:
            for s in old_settings:
                c.execute('INSERT INTO banks (region_code, name, value) VALUES (?, ?, ?)', 
                          (s['region_code'], s['req_title'], s['req_value']))
        else:
            # Default init if both are empty
            default_banks = [
                ('PL', 'BLIK / Bank Millennium', 'PL89 1020 5558 1111 2222 3333 4444'),
                ('LT', 'Revolut Bank (Rimas Cicenas)', 'LT85 3250 0478 6473 6227'),
                ('KZ', 'Kaspi Bank', 'Данные уточняются...'),
                ('AZ', 'M10 / Золотая Корона', 'Данные уточняются...')
            ]
            c.executemany('INSERT INTO banks (region_code, name, value) VALUES (?, ?, ?)', default_banks)

    # Ensure the root admin from .env is in the DB
    admin_env = os.getenv("TELEGRAM_ADMIN_ID", "DUMMY_ID")
    for aid in admin_env.split(','):
        aid = aid.strip()
        if aid and aid != "DUMMY_ID":
            c.execute('INSERT OR IGNORE INTO admins (chat_id) VALUES (?)', (aid,))

    conn.commit()
    conn.close()

def create_transaction(tx_code, category, amount, currency, name, comment, file_path, expires_at=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO transactions (tx_code, category, amount, currency, name, comment, file_path, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (tx_code, category, amount, currency, name, comment, file_path, expires_at))
    tx_id = c.lastrowid
    conn.commit()
    conn.close()
    return tx_id

def get_transaction(tx_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM transactions WHERE id = ?', (tx_id,))
    tx = c.fetchone()
    conn.close()
    return tx

def get_transaction_by_code(tx_code):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM transactions WHERE tx_code = ?', (tx_code,))
    tx = c.fetchone()
    conn.close()
    return tx

def update_transaction_status(tx_id, status):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE transactions SET status = ? WHERE id = ?', (status, tx_id))
    conn.commit()
    conn.close()

def get_statistics():
    conn = get_connection()
    c = conn.cursor()
    # Today stats
    c.execute("SELECT COUNT(*), SUM(amount) FROM transactions WHERE date(created_at) = date('now') AND status = 'approved'")
    today_approved_count, today_approved_sum = c.fetchone()
    
    c.execute("SELECT COUNT(*) FROM transactions WHERE status = 'pending'")
    pending_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM transactions WHERE date(created_at) = date('now')")
    today_total_count = c.fetchone()[0]
    
    conn.close()
    return {
        "today_approved_count": today_approved_count or 0,
        "today_approved_sum": today_approved_sum or 0,
        "pending_count": pending_count or 0,
        "today_total_count": today_total_count or 0
    }

def get_extended_statistics(period='today'):
    conn = get_connection()
    c = conn.cursor()
    
    if period == 'today':
        date_cond = "date(created_at) = date('now')"
    elif period == 'week':
        date_cond = "date(created_at) >= date('now', '-7 days')"
    elif period == 'month':
        date_cond = "date(created_at) >= date('now', '-30 days')"
    else: # all time
        date_cond = "1=1"
        
    c.execute(f"SELECT COUNT(*), SUM(amount) FROM transactions WHERE {date_cond} AND status = 'approved'")
    appr_cnt, appr_sum = c.fetchone()
    
    c.execute(f"SELECT COUNT(*) FROM transactions WHERE {date_cond} AND status = 'rejected'")
    rej_cnt = c.fetchone()[0]
    
    c.execute(f"SELECT COUNT(*) FROM transactions WHERE {date_cond}")
    total_cnt = c.fetchone()[0]
    
    conn.close()
    return {
        "approved_count": appr_cnt or 0,
        "approved_sum": appr_sum or 0,
        "rejected_count": rej_cnt or 0,
        "total_count": total_cnt or 0,
        "period": period
    }

def get_all_banks():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM banks ORDER BY region_code')
    banks = c.fetchall()
    conn.close()
    return [dict(b) for b in banks]

def get_banks_by_region(region_code):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM banks WHERE region_code = ?', (region_code,))
    banks = c.fetchall()
    conn.close()
    return [dict(b) for b in banks]

def add_bank(region_code, name, value):
    conn = get_connection()
    c = conn.cursor()
    c.execute('INSERT INTO banks (region_code, name, value) VALUES (?, ?, ?)', (region_code, name, value))
    conn.commit()
    conn.close()

def update_bank_value(bank_id, new_value):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE banks SET value = ? WHERE id = ?', (new_value, bank_id))
    conn.commit()
    conn.close()

def delete_bank(bank_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM banks WHERE id = ?', (bank_id,))
    conn.commit()
    conn.close()

def get_pending_transactions(offset=0, limit=20):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM transactions WHERE status = 'pending' ORDER BY id ASC LIMIT ? OFFSET ?", (limit, offset))
    rows = c.fetchall()
    
    c.execute("SELECT COUNT(*) FROM transactions WHERE status = 'pending'")
    total = c.fetchone()[0]
    conn.close()
    return [dict(r) for r in rows], total

def get_all_transactions():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM transactions ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_projects():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, description, media_url, min_amount FROM projects ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def add_project(name: str, min_amount=None, description: str = "", media_url: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO projects (name, min_amount, description, media_url) VALUES (?, ?, ?, ?)",
        (name, min_amount, description, media_url),
    )
    conn.commit()
    project_id = cursor.lastrowid
    conn.close()
    return project_id

def get_project(project_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, description, media_url, min_amount FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_project(project_id: int, name: str, min_amount=None, description: str = "", media_url: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE projects SET name = ?, min_amount = ?, description = ?, media_url = ? WHERE id = ?",
        (name, min_amount, description, media_url, project_id),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated

def delete_project(project_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

# Setting Management
def is_admin(chat_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT 1 FROM admins WHERE chat_id=?", (str(chat_id),))
    row = c.fetchone()
    conn.close()
    return row is not None

# --- Project Settings ---
def get_setting(key, default=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM project_settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO project_settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def add_admin(chat_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO admins (chat_id) VALUES (?)', (str(chat_id),))
    conn.commit()
    conn.close()

def remove_admin(chat_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM admins WHERE chat_id = ?', (str(chat_id),))
    conn.commit()
    conn.close()

def get_all_admins():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM admins ORDER BY added_at DESC')
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Инициализируем при импорте
init_db()
