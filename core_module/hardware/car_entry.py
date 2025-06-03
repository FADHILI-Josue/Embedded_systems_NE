import platform
import cv2
from ultralytics import YOLO
import pytesseract
import os
import time
import serial
import serial.tools.list_ports
from collections import Counter
import requests
import sqlite3
from datetime import datetime
import db_utils # Utility for database operations

# Tesseract OCR Path
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\fadhi\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

# Configurations
YOLO_MODEL_PATH = '../model_dev/runs/detect/train/weights/best.pt'
ENTRY_COOLDOWN = 300
MAX_DISTANCE = 50
MIN_DISTANCE = 0
CAPTURE_THRESHOLD = 3
GATE_OPEN_TIME = 15
BACKEND_API_URL = "http://localhost:3001/api"
SAVE_DIR = 'plates' # For saving plate images

os.makedirs(SAVE_DIR, exist_ok=True)
db_utils.init_db() # Initialize database using utility

try:
    model = YOLO(YOLO_MODEL_PATH)
except Exception as e:
    print(f"[ERROR] Could not load YOLO model: {e}"); exit(1)

def detect_arduino_port():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if "arduino" in p.description.lower() or (p.vid == 0x2341) or (p.vid == 0x2A03) or (p.vid == 0x1A86 and p.pid == 0x7523): return p.device
    for p in ports: # Fallback
        dev = p.device
        if platform.system()=='Linux' and ('ttyACM' in dev or 'ttyUSB' in dev): return dev
        if platform.system()=='Darwin' and ('usbmodem' in dev or 'usbserial' in dev): return dev
        if platform.system()=='Windows' and 'COM' in dev: return dev
    return None

def read_distance(arduino_serial):
    if not arduino_serial or not arduino_serial.is_open or arduino_serial.in_waiting == 0: return None
    try: return float(arduino_serial.readline().decode('utf-8').strip())
    except: return None

def has_unpaid_record_local(plate):
    conn = db_utils.get_db_connection()
    cursor = conn.cursor()
    record = None
    try:
        cursor.execute("SELECT 1 FROM parking_log WHERE car_plate = ? AND payment_status = 0 LIMIT 1", (plate,))
        record = cursor.fetchone()
    except sqlite3.Error as e: print(f"[DB_ERROR] Checking unpaid: {e}")
    finally:
        if conn: conn.close()
    return record is not None

arduino_port = detect_arduino_port()
arduino = None
if arduino_port:
    try:
        arduino = serial.Serial(arduino_port, 9600, timeout=1); time.sleep(2)
        print(f"[CONNECTED] Arduino on {arduino_port}")
    except serial.SerialException as e: print(f"[ERROR] Arduino connect: {e}")
else: print("[WARNING] Arduino not detected.")

cap = cv2.VideoCapture(0)
if not cap.isOpened(): print("[ERROR] Cannot open camera."); exit(1)
cv2.namedWindow('Webcam Feed', cv2.WINDOW_NORMAL); cv2.namedWindow('Plate', cv2.WINDOW_NORMAL)
cv2.namedWindow('Processed', cv2.WINDOW_NORMAL); cv2.resizeWindow('Webcam Feed', 800, 600)

plate_buffer = []
last_saved_plate = None
last_entry_time = 0
print("[SYSTEM] Car Entry System Ready. Press 'q' to exit.")

try:
    while True:
        ret, frame = cap.read()
        if not ret: print("[ERROR] Frame capture failed."); time.sleep(0.1); continue

        current_time_ts = time.time()
        current_datetime_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        distance = read_distance(arduino)
        effective_distance = distance if distance is not None else (MAX_DISTANCE + 1)
        annotated_frame = frame.copy()

        if MIN_DISTANCE <= effective_distance <= MAX_DISTANCE:
            results = model(frame, verbose=False)[0]
            if results.boxes:
                annotated_frame = results.plot()
                for box in results.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    plate_img = frame[y1:y2, x1:x2]
                    if plate_img.size == 0: continue

                    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
                    blur = cv2.GaussianBlur(gray, (5,5), 0)
                    thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
                    custom_config = r'--oem 3 --psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                    text = pytesseract.image_to_string(thresh, config=custom_config).strip().replace(' ', '')

                    if len(text) == 7 and text.startswith('RA') and \
                       text[2].isalpha() and text[3:6].isdigit() and text[6].isalpha():
                        plate_buffer.append(text)

                    if len(plate_buffer) >= CAPTURE_THRESHOLD:
                        common_plate = Counter(plate_buffer).most_common(1)[0][0]
                        if not has_unpaid_record_local(common_plate):
                            if common_plate != last_saved_plate or (current_time_ts - last_entry_time) > ENTRY_COOLDOWN:
                                conn_log = db_utils.get_db_connection()
                                cursor_log = conn_log.cursor()
                                try:
                                    cursor_log.execute("INSERT INTO parking_log (entry_time, car_plate, payment_status) VALUES (?, ?, 0)",
                                        (current_datetime_str, common_plate))
                                    conn_log.commit()
                                    print(f"[DB_LOG] Logged entry for {common_plate}")
                                except sqlite3.Error as e_sql: print(f"[ERROR] DB write: {e_sql}")
                                finally:
                                    if conn_log: conn_log.close()

                                try:
                                    payload = {"car_plate": common_plate}
                                    response = requests.post(f"{BACKEND_API_URL}/events/entry", json=payload, timeout=5)
                                    print(f"[BACKEND] Entry {common_plate} Status: {response.status_code}")
                                except requests.exceptions.RequestException as e_req: print(f"[BACKEND_ERROR] Entry: {e_req}")

                                if arduino and arduino.is_open:
                                    try: arduino.write(b'1'); time.sleep(GATE_OPEN_TIME); arduino.write(b'0'); print("[GATE] Operated.")
                                    except serial.SerialException as e_s: print(f"[ERROR] Arduino gate: {e_s}")
                                else: print("[GATE_SIM] Simulated.")
                                last_saved_plate = common_plate
                                last_entry_time = current_time_ts
                            else: print(f"[SKIPPED] Cooldown/Same plate {common_plate}.")
                        else: print(f"[SKIPPED] DB: Unpaid record for {common_plate}.")
                        plate_buffer.clear()
                    cv2.imshow('Plate', plate_img); cv2.imshow('Processed', thresh)
                    break
        cv2.imshow('Webcam Feed', annotated_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): print("[SYSTEM] 'q' pressed, exiting."); break
finally:
    print("[SYSTEM] Cleaning up...")
    if cap: cap.release()
    if arduino and arduino.is_open:
        try: arduino.write(b'0'); arduino.close(); print("[SYSTEM] Arduino closed.")
        except serial.SerialException as e_s: print(f"[ERROR] Arduino close: {e_s}")
    cv2.destroyAllWindows(); print("[SYSTEM] Exited.")