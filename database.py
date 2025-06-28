import sqlite3
from config import DATABASE_URL  # Импорт DATABASE_URL из config.py

def get_db_connection():
    """Возвращает подключение к базе данных SQLite."""
    return sqlite3.connect(DATABASE_URL)

def load_data(game_state):
    """Загружает данные из базы в game_state."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vip_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bonus_users (
                user_id INTEGER PRIMARY KEY,
                bonus_count INTEGER
            )
        """)
        cur.execute("SELECT user_id, username FROM vip_users")
        game_state["vip_users"] = []
        rows = cur.fetchall()
        for row in rows:
            game_state["vip_users"].append({"user_id": row[0], "username": row[1]})
        cur.execute("SELECT user_id, bonus_count FROM bonus_users")
        game_state["bonus_users"] = {}
        rows = cur.fetchall()
        for row in rows:
            game_state["bonus_users"][row[0]] = row[1]
        conn.commit()
    except Exception as e:
        print(f"Ошибка загрузки данных: {e}")
    finally:
        cur.close()
        conn.close()

def save_data(game_state):
    """Сохраняет данные из game_state в базу."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM vip_users")
        for vip in game_state["vip_users"]:
            cur.execute("INSERT OR REPLACE INTO vip_users (user_id, username) VALUES (?, ?)",
                       (vip["user_id"], vip["username"]))
        cur.execute("DELETE FROM bonus_users")
        for user_id, count in game_state["bonus_users"].items():
            cur.execute("INSERT OR REPLACE INTO bonus_users (user_id, bonus_count) VALUES (?, ?)",
                       (user_id, count))
        conn.commit()
    except Exception as e:
        print(f"Ошибка сохранения данных: {e}")
    finally:
        cur.close()
        conn.close()