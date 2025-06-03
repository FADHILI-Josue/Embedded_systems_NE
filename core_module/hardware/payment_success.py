import sqlite3
from datetime import datetime
import db_utils # Utility for database operations

db_utils.init_db() # Ensure table exists if script is run standalone

def mark_payment_success_db(plate_number, amount_paid=None):
    conn = db_utils.get_db_connection()
    cursor = conn.cursor()
    record = None
    try:
        cursor.execute("SELECT id FROM parking_log WHERE car_plate = ? AND payment_status = 0 ORDER BY entry_time DESC LIMIT 1", (plate_number,))
        record = cursor.fetchone()
    except sqlite3.Error as e:
        print(f"[DB_ERROR] Fetching unpaid for manual payment: {e}")
        if conn: conn.close()
        return

    if record:
        entry_id = record["id"]
        current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            if amount_paid is not None:
                cursor.execute("UPDATE parking_log SET payment_status = 1, exit_time = ?, due_payment = ? WHERE id = ?",
                               (current_time_str, amount_paid, entry_id))
            else:
                cursor.execute("UPDATE parking_log SET payment_status = 1, exit_time = ? WHERE id = ?",
                               (current_time_str, entry_id))
            conn.commit()
            print(f"[DB_UPDATED] Payment status set to 1 for plate {plate_number} (ID: {entry_id}) at {current_time_str}.")
        except sqlite3.Error as e_sql:
            print(f"[DB_ERROR] Updating manual payment: {e_sql}")
    else:
        print(f"[INFO] No unpaid record found for {plate_number} in the database.")
    
    if conn: conn.close()

if __name__ == "__main__":
    plate = input("Enter plate number to mark as paid: ").strip().upper()
    amount_str = input("Enter amount paid (optional, press Enter to skip): ").strip()
    amount = None
    if amount_str:
        try: amount = int(amount_str)
        except ValueError: print("Invalid amount. Proceeding without.")
    mark_payment_success_db(plate, amount)