import platform
import cv2
from ultralytics import YOLO
import pytesseract
import os
import time
import serial
import serial.tools.list_ports
from collections import Counter
from datetime import datetime, timedelta
import requests
import sqlite3
import db_utils # Utility for database operations

pytesseract.pytesseract.tesseract_cmd = r"C:\Users\fadhi\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

YOLO_MODEL_PATH = '../model_dev/runs/detect/train/weights/best.pt'
MAX_DISTANCE = 50
MIN_DISTANCE = 0
CAPTURE_THRESHOLD = 3
GATE_OPEN_TIME = 15
EXIT_GRACE_PERIOD_MINUTES = 1
BACKEND_API_URL = "http://localhost:3001/api"
PLATE_PROCESS_COOLDOWN = 10
ALERT_MESSAGE_DURATION = 3

db_utils.init_db() # Initialize database using utility

try:
    model = YOLO(YOLO_MODEL_PATH)
except Exception as e:
    print(f"[ERROR] Could not load YOLO model: {e}"); exit(1)

def detect_arduino_port(): # (Identical to car_entry.py)
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if "arduino" in p.description.lower() or (p.vid == 0x2341) or (p.vid == 0x2A03) or (p.vid == 0x1A86 and p.pid == 0x7523): return p.device
    for p in ports: # Fallback
        dev = p.device
        if platform.system()=='Linux' and ('ttyACM' in dev or 'ttyUSB' in dev): return dev
        if platform.system()=='Darwin' and ('usbmodem' in dev or 'usbserial' in dev): return dev
        if platform.system()=='Windows' and 'COM' in dev: return dev
    return None

def read_distance(arduino_serial): # (Identical to car_entry.py)
    if not arduino_serial or not arduino_serial.is_open or arduino_serial.in_waiting == 0: return None
    try: return float(arduino_serial.readline().decode('utf-8').strip())
    except: return None

arduino_port = detect_arduino_port()
arduino = None
if arduino_port:
    try:
        arduino = serial.Serial(arduino_port, 9600, timeout=1); time.sleep(2)
        print(f"[CONNECTED] Arduino on {arduino_port}")
    except serial.SerialException as e: print(f"[ERROR] Arduino connect: {e}")
else: print("[WARNING] Arduino not detected.")

def handle_exit_local_db(plate_number):
    conn = db_utils.get_db_connection()
    cursor = conn.cursor()
    record_data = None
    try:
        cursor.execute("SELECT exit_time FROM parking_log WHERE car_plate = ? AND payment_status = 1 AND exit_time IS NOT NULL ORDER BY exit_time DESC LIMIT 1", (plate_number,))
        record_data = cursor.fetchone()
    except sqlite3.Error as e: print(f"[DB_ERROR] Checking paid exit: {e}")
    finally:
        if conn: conn.close()

    if record_data and record_data["exit_time"]: # Access by column name
        try:
            payment_time_dt = datetime.strptime(record_data["exit_time"], '%Y-%m-%d %H:%M:%S')
            if timedelta(minutes=0) <= (datetime.now() - payment_time_dt) <= timedelta(minutes=EXIT_GRACE_PERIOD_MINUTES):
                print(f"[DB_CHECK][ACCESS GRANTED] Plate {plate_number}: Valid paid record."); return True
        except ValueError: print(f"[DB_CHECK][ERROR] Invalid date for {plate_number}")
    print(f"[DB_CHECK][ACCESS DENIED] Plate {plate_number}: No recent paid record."); return False

cap = cv2.VideoCapture(0)
if not cap.isOpened(): print("[ERROR] Cannot open camera."); exit(1)
cv2.namedWindow('Exit Webcam Feed', cv2.WINDOW_NORMAL); cv2.namedWindow('Plate Exit', cv2.WINDOW_NORMAL)
cv2.namedWindow('Processed Exit', cv2.WINDOW_NORMAL); cv2.resizeWindow('Exit Webcam Feed', 800, 600)

plate_buffer = []; last_processed_plate_time = 0; last_processed_plate_value = None
is_alert_message_active = False; alert_message_start_time = 0; current_alert_message_text = ""
print("[SYSTEM] Car Exit System Ready. Press 'q' to quit.")

try:
    while True:
        ret, frame = cap.read()
        if not ret: print("[ERROR] Frame capture failed."); time.sleep(0.1); continue

        current_time = time.time()
        distance = read_distance(arduino)
        effective_distance = distance if distance is not None else (MAX_DISTANCE + 1)
        annotated_frame = frame.copy(); yolo_results_plot = None

        if MIN_DISTANCE <= effective_distance <= MAX_DISTANCE:
            results = model(frame, verbose=False)
            if results and results[0].boxes:
                yolo_results_plot = results[0].plot()
                for box in results[0].boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    plate_img = frame[y1:y2, x1:x2]
                    if plate_img.size == 0: continue

                    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY); blur = cv2.GaussianBlur(gray, (5, 5), 0)
                    thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
                    custom_config = r'--oem 3 --psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                    text = pytesseract.image_to_string(thresh, config=custom_config).strip().replace(" ", "")

                    if len(text) == 7 and text.startswith('RA') and text[2].isalpha() and text[3:6].isdigit() and text[6].isalpha():
                        plate_buffer.append(text)

                    if len(plate_buffer) >= CAPTURE_THRESHOLD:
                        most_common_plate = Counter(plate_buffer).most_common(1)[0][0]
                        plate_buffer.clear()
                        if not (most_common_plate == last_processed_plate_value and (current_time - last_processed_plate_time) < PLATE_PROCESS_COOLDOWN):
                            print(f"\n[CONFIRMED_EXIT_PLATE] Plate: {most_common_plate}")
                            allow_physical_exit = handle_exit_local_db(most_common_plate)
                            if allow_physical_exit:
                                print(f"[GATE_ACTION] GRANTED for {most_common_plate}.")
                                if arduino and arduino.is_open:
                                    try: arduino.write(b'1'); time.sleep(GATE_OPEN_TIME); arduino.write(b'0'); print("[GATE_HW] Operated.")
                                    except serial.SerialException as e: print(f"[ERROR] Arduino gate: {e}")
                                else: print("[GATE_SIM] Simulated."); time.sleep(GATE_OPEN_TIME)
                            else:
                                print(f"[GATE_ACTION] DENIED for {most_common_plate}.")
                                unpaid_payload = {"car_plate": most_common_plate, "payment_status": "UNPAID_ATTEMPT"}
                                try:
                                    resp = requests.post(f"{BACKEND_API_URL}/events/exit", json=unpaid_payload, timeout=5)
                                    print(f"[BACKEND_EVENT] UNPAID {most_common_plate}. Status: {resp.status_code}")
                                except requests.exceptions.RequestException as e_req: print(f"[BACKEND_ERROR] UNPAID: {e_req}")
                                is_alert_message_active = True; alert_message_start_time = current_time
                                current_alert_message_text = f"ALERT: Unpaid Exit - {most_common_plate}"
                                if arduino and arduino.is_open:
                                    try: arduino.write(b'2'); print(f"[ALERT_HW] Buzzer/LED on.")
                                    except serial.SerialException as e: print(f"[ERROR] Arduino alert: {e}")
                                else: print("[ALERT_HW_SIM] Simulated.")
                                print(f"[ALERT_VISUAL] On-screen: {current_alert_message_text}")
                            last_processed_plate_value = most_common_plate; last_processed_plate_time = current_time
                    cv2.imshow("Plate Exit", plate_img); cv2.imshow("Processed Exit", thresh)
                    break
        frame_to_display_on = yolo_results_plot if yolo_results_plot is not None else annotated_frame
        if is_alert_message_active:
            if (current_time - alert_message_start_time) < ALERT_MESSAGE_DURATION:
                if frame_to_display_on is not None:
                    cv2.putText(frame_to_display_on, current_alert_message_text, (10, frame_to_display_on.shape[0]-30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,0,255),3,cv2.LINE_AA)
            else: is_alert_message_active = False; current_alert_message_text = ""
        cv2.imshow("Exit Webcam Feed", frame_to_display_on)
        if cv2.waitKey(1) & 0xFF == ord('q'): print("[SYSTEM] 'q' pressed, exiting."); break
finally:
    print("[SYSTEM] Cleaning up...")
    if cap: cap.release()
    if arduino and arduino.is_open:
        try: arduino.write(b'0'); arduino.close(); print("[SYSTEM] Arduino closed.")
        except serial.SerialException as e: print(f"[ERROR] Arduino close: {e}")
    cv2.destroyAllWindows(); print("[SYSTEM] Exited.")