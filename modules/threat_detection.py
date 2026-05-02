from modules.database import get_db

def log_event(username, event_type, description):
    username = str(username)[:50]
    event_type = str(event_type)[:30]
    description = str(description)[:200]

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(
            "INSERT INTO logs (username, event_type, description) VALUES (?, ?, ?)",
            (username, event_type, description)
        )
        conn.commit()
        print("LOG SUCCESS:", username, event_type)

    except Exception as e:
        conn.rollback()
        print("Logging failed:", e)

    finally:
        conn.close()