import sqlite3, time, os
from datetime import datetime
import psycopg2

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))  # go up 3 levels
INSTANCE_DIR = os.path.join(PROJECT_ROOT, "instance")
DB_PATH = os.path.join(INSTANCE_DIR, "database.db")

# DATABASE_URL = postgresql://database_i96q_user:ur6ds5cAen7bQUpeWXynfS1f4yw1dCNN@dpg-d8hf7smrnols73chl19g-a/database_i96q


# def get_db():
#     print("[DEBUG] Using DB path:", DB_PATH)  # helpful check
#     return sqlite3.connect(DB_PATH, check_same_thread=False)

# def get_db():
#     return sqlite3.connect("database.db", check_same_thread=False)
def get_db():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # Render → PostgreSQL
        print("[DEBUG] Using PostgreSQL:", database_url)
        return psycopg2.connect(database_url)
    else:
        # Local dev → SQLite
        print("[DEBUG] Using SQLite:", DB_PATH)
        return sqlite3.connect(DB_PATH, check_same_thread=False)

def get_all_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT username FROM users")
    users = cur.fetchall()
    conn.close()
    return users

# --- Save text message ---
def save_message(sender, receiver, ciphertext, nonce):
    for attempt in range(5):
        try:
            conn = get_db()
            cur = conn.cursor()

            # Use ? placeholders for sqlite3
            if os.environ.get("DATABASE_URL"):
                cur.execute(
                    "INSERT INTO messages (sender, receiver, ciphertext, nonce, msg_type, timestamp) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (sender, receiver, ciphertext, nonce, "text", datetime.utcnow())
                )
            else:
                cur.execute(
                    "INSERT INTO messages (sender, receiver, ciphertext, nonce, msg_type, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (sender, receiver, ciphertext, nonce, "text", datetime.utcnow())
                )

            conn.commit()
            cur.close()
            conn.close()
            return
        except Exception as e:
            print("[DEBUG] Error saving message:", e)
            time.sleep(0.1)

# --- Save file/image message ---
def save_file_message(sender, receiver, file_name, msg_type):
    for attempt in range(5):
        try:
            conn = get_db()
            cur = conn.cursor()

            if os.environ.get("DATABASE_URL"):
                cur.execute(
                    "INSERT INTO messages (sender, receiver, file_name, msg_type, timestamp) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (sender, receiver, file_name, msg_type, datetime.utcnow())
                )
            else:
                cur.execute(
                    "INSERT INTO messages (sender, receiver, file_name, msg_type, timestamp) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (sender, receiver, file_name, msg_type, datetime.utcnow())
                )

            conn.commit()
            cur.close()
            conn.close()
            return
        except Exception as e:
            print("[DEBUG] Error saving file message:", e)
            time.sleep(0.1)

# --- Save call log message ---
def save_call_message(sender, receiver, status, duration=None):
    for attempt in range(5):
        try:
            conn = get_db()
            cur = conn.cursor()

            if os.environ.get("DATABASE_URL"):
                cur.execute(
                    "INSERT INTO messages (sender, receiver, msg_type, status, duration, timestamp) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (sender, receiver, "call", status, duration, datetime.utcnow())
                )
            else:
                cur.execute(
                    "INSERT INTO messages (sender, receiver, msg_type, status, duration, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (sender, receiver, "call", status, duration, datetime.utcnow())
                )

            conn.commit()
            cur.close()
            conn.close()
            return
        except Exception as e:
            print("[DEBUG] Error saving call message:", e)
            time.sleep(0.1)

# --- Retrieve chat history ---
def get_chat_history(user1, user2):
    conn = get_db()
    cur = conn.cursor()

    if os.environ.get("DATABASE_URL"):
        cur.execute(
            "SELECT sender, receiver, ciphertext, nonce, file_name, msg_type, timestamp, status, duration "
            "FROM messages "
            "WHERE (sender=%s AND receiver=%s) OR (sender=%s AND receiver=%s) "
            "ORDER BY timestamp",
            (user1, user2, user2, user1)
        )
    else:
        cur.execute(
            "SELECT sender, receiver, ciphertext, nonce, file_name, msg_type, timestamp, status, duration "
            "FROM messages "
            "WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?) "
            "ORDER BY timestamp",
            (user1, user2, user2, user1)
        )

    history = cur.fetchall()
    conn.close()
    return history


# --- Initialize DB schema ---

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    if os.environ.get("DATABASE_URL"):
        # PostgreSQL syntax
        cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            failed_attempts INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0
        )
        ''')

        cur.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            username TEXT,
            event_type TEXT,
            description TEXT,
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        cur.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            sender TEXT NOT NULL,
            receiver TEXT NOT NULL,
            ciphertext TEXT,
            nonce TEXT,
            file_name TEXT,
            msg_type TEXT,   -- "text", "file", "image", "audio", "call"
            status TEXT,     -- for calls: "ended", "missed", "declined"
            duration INTEGER, -- call duration in seconds
            timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        ''')
    else:        
        # users table
        cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            failed_attempts INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0
        )
        ''')

        # logs table
        cur.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            event_type TEXT,
            description TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # messages table
        cur.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            receiver TEXT NOT NULL,
            ciphertext TEXT,
            nonce TEXT,
            file_name TEXT,
            msg_type TEXT,   -- "text", "file", "image", "audio", "call"
            status TEXT,     -- for calls: "ended", "missed", "declined"
            duration INTEGER, -- call duration in seconds
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')

    conn.commit()
    conn.close()
