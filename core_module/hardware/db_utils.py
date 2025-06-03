import sqlite3
import os

DATABASE_NAME = 'parking_system.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_name=None):
    current_db_name = db_name if db_name else DATABASE_NAME
    db_dir = os.path.dirname(current_db_name)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        print(f"[DB_UTILS] Created directory for database: {db_dir}")

    conn = sqlite3.connect(current_db_name)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS parking_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_time TEXT NOT NULL,
                exit_time TEXT,
                car_plate TEXT NOT NULL,
                due_payment INTEGER,
                payment_status INTEGER NOT NULL DEFAULT 0,
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_car_plate_status ON parking_log (car_plate, payment_status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entry_time ON parking_log (entry_time)')
        conn.commit()
        print(f"[DB_UTILS] Database '{current_db_name}' initialized/verified successfully.")
    except sqlite3.Error as e:
        print(f"[DB_UTILS][ERROR] Error initializing database '{current_db_name}': {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("Initializing default database via db_utils.py...")
    init_db()
    print("Default database initialization check complete.")