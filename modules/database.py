import sqlite3

def get_db():
    return sqlite3.connect("database.db", check_same_thread=False)

def get_all_users():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT username FROM users")
    users = cur.fetchall()

    conn.close()
    return users

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        failed_attempts INTEGER DEFAULT 0,
        is_blocked INTEGER DEFAULT 0
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        event_type TEXT,
        description TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    

    conn.commit()
    conn.close()