import serial
import time
import serial.tools.list_ports
import platform
from datetime import datetime
import math
import requests
import sqlite3
import db_utils # Utility for database operations

HOURLY_RATE = 500
BACKEND_API_URL = "http://localhost:3001/api"

db_utils.init_db() # Initialize database using utility

def detect_arduino_port(): # (Identical to car_entry.py)
    ports = list(serial.tools.list_ports.comports())
    system = platform.system()
    for p in ports:
        if "arduino" in p.description.lower() or "COM13" in p.device: return p.device
    for p in ports:
        if system == "Windows" and "COM" in p.device: return p.device
    return None

def parse_arduino_data(line):
    try:
        parts = line.strip().split(',');
        if len(parts) != 2: return None, None
        plate = parts[0].strip()
        balance_str = ''.join(c for c in parts[1] if c.isdigit())
        return (plate, int(balance_str)) if balance_str else (None, None)
    except ValueError: return None, None

def send_alert_to_backend(plate, msg, alert_type):
    try:
        payload = {"plate_number": plate, "message": msg, "type": alert_type}
        resp = requests.post(f"{BACKEND_API_URL}/events/alert", json=payload, timeout=5)
        print(f"[BACKEND_ALERT] Sent '{alert_type}' for {plate if plate else 'Sys'}. Status: {resp.status_code}")
    except requests.exceptions.RequestException as e: print(f"[BACKEND_ALERT_ERROR] {e}")

def process_payment(plate, balance, ser):
    conn = db_utils.get_db_connection()
    cursor = conn.cursor()
    record = None
    try:
        cursor.execute("SELECT id, entry_time FROM parking_log WHERE car_plate = ? AND payment_status = 0 ORDER BY entry_time DESC LIMIT 1", (plate,))
        record = cursor.fetchone()
    except sqlite3.Error as e_sql:
        print(f"[DB_ERROR] Fetching unpaid for {plate}: {e_sql}")
        if conn: conn.close()
        return

    if not record:
        print(f"[PAYMENT] Plate {plate} not found/paid in DB.")
        send_alert_to_backend(plate, f"No active entry for {plate}.", "PLATE_NOT_FOUND_DB")
        if conn: conn.close()
        return

    entry_id, entry_time_str = record["id"], record["entry_time"]
    try:
        entry_dt = datetime.strptime(entry_time_str, '%Y-%m-%d %H:%M:%S')
        exit_dt = datetime.now(); exit_str = exit_dt.strftime('%Y-%m-%d %H:%M:%S')
        hours = max(1, math.ceil((exit_dt - entry_dt).total_seconds() / 3600.0))
        due = int(hours * HOURLY_RATE)

        if balance < due:
            print(f"[PAYMENT] Insufficient balance {plate}. Req: {due}, Has: {balance}")
            ser.write(b'I\n'); send_alert_to_backend(plate, f"Insufficient RFID balance {plate}. Req: {due}", "INSUFFICIENT_BALANCE_RFID")
            return
        
        new_bal = balance - due
        print("[WAIT] Arduino READY..."); start_t = time.time(); ready_ok = False
        while time.time() - start_t < 5:
            if ser.in_waiting and ser.readline().decode().strip() == "READY": ready_ok = True; break
            time.sleep(0.01)
        if not ready_ok: print("[ERROR] Arduino READY timeout"); return

        ser.write(f"{new_bal}\r\n".encode()); print(f"[PAYMENT] Sent new balance {new_bal}")
        print("[WAIT] Arduino confirm..."); start_t = time.time(); confirm_ok = False
        while time.time() - start_t < 10:
            if ser.in_waiting and "DONE" in ser.readline().decode().strip(): confirm_ok = True; break
            time.sleep(0.1)
        
        if not confirm_ok:
            print("[ERROR] Arduino confirm timeout."); send_alert_to_backend(plate, f"Timeout 'DONE' for {plate}.", "ARDUINO_TIMEOUT_CONFIRM"); return

        cursor.execute("UPDATE parking_log SET exit_time = ?, due_payment = ?, payment_status = 1 WHERE id = ?", (exit_str, due, entry_id))
        conn.commit()
        print(f"[DB_UPDATE] Payment success for {plate}.")
        payload = {"car_plate": plate, "payment_status": "PAID"}
        try:
            resp = requests.post(f"{BACKEND_API_URL}/events/exit", json=payload, timeout=5)
            print(f"[BACKEND_EVENT] PAID exit {plate}. Status: {resp.status_code}")
        except requests.exceptions.RequestException as e_req: print(f"[BACKEND_ERROR] PAID event: {e_req}")
    except ValueError as ve: print(f"[ERROR] Date parse {plate}: {ve}"); send_alert_to_backend(plate, f"Date error {plate}: {ve}", "PAYMENT_DATE_ERROR")
    except sqlite3.Error as e_sql: print(f"[ERROR] SQLite payment {plate}: {e_sql}"); send_alert_to_backend(plate, f"DB error payment {plate}: {e_sql}", "PAYMENT_DB_ERROR")
    except Exception as e: print(f"[ERROR] Payment failed {plate}: {e}"); send_alert_to_backend(plate, f"Payment error {plate}: {e}", "PAYMENT_PROCESSING_ERROR")
    finally:
        if conn: conn.close()

def main():
    port = detect_arduino_port()
    if not port: print("[ERROR] Arduino not found"); send_alert_to_backend(None, "Payment Arduino not detected.", "ARDUINO_NOT_DETECTED_PAYMENT"); return
    ser = None
    try:
        ser = serial.Serial(port, 9600, timeout=1); time.sleep(2); ser.reset_input_buffer()
        print(f"[CONNECTED] Listening on {port} --- Payment Terminal Ready ---")
        while True:
            if ser.in_waiting:
                try:
                    line = ser.readline().decode('utf-8').strip()
                    if line:
                        print(f"\n[SERIAL] Received: {line}")
                        plate, balance = parse_arduino_data(line)
                        if plate and balance is not None: process_payment(plate, balance, ser); print("--- Ready for next scan ---")
                except UnicodeDecodeError: print(f"[ERROR] UnicodeDecodeError.")
                except Exception as e_read: print(f"[ERROR] Serial read/parse: {e_read}")
            time.sleep(0.01)
    except KeyboardInterrupt: print("[EXIT] Program terminated")
    except serial.SerialException as e_s: print(f"[ERROR] Serial issue: {e_s}"); send_alert_to_backend(None, f"Serial error Payment Arduino {port}: {e_s}", "ARDUINO_SERIAL_ERROR")
    except Exception as e: print(f"[ERROR] Main error: {e}"); send_alert_to_backend(None, f"Critical payment script error: {e}", "PAYMENT_SCRIPT_CRITICAL_ERROR")
    finally:
        if ser and ser.is_open: print("[INFO] Closing serial."); ser.close()

if __name__ == "__main__":
    main()