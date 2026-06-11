from modules.database import get_db
import os

def log_event(username, event_type, description):
    username = str(username)[:50]
    event_type = str(event_type)[:30]
    description = str(description)[:200]

    conn = get_db()
    cur = conn.cursor()
    ph = "%s" if os.environ.get("DATABASE_URL") else "?"

    try:
        cur.execute(
            f"INSERT INTO logs (username, event_type, description) VALUES ({ph}, {ph}, {ph})",
            (username, event_type, description)
        )
        conn.commit()
        print("LOG SUCCESS:", username, event_type)

    except Exception as e:
        conn.rollback()
        print("Logging failed:", e)

    finally:
        conn.close()