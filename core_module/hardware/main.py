import platform
import cv2
import numpy as np
from ultralytics import YOLO
import pytesseract
import os
import time
import serial
import serial.tools.list_ports
import sqlite3
import logging
from collections import Counter
from datetime import datetime
import re
import argparse
import threading
import db_utils # Utility for database operations

class PlateRecognitionSystem:
    def __init__(self, config):
        self.config = config
        self.setup_logging()
        self.logger.info("Initializing Plate Recognition System")
        os.makedirs(config['save_dir'], exist_ok=True)
        db_utils.init_db() # Use utility to init DB
        self.load_model(); self.connect_arduino(); self.init_camera()
        self.plate_buffer = []; self.last_saved_plate = None
        self.last_entry_time = 0; self.running = False
        self.logger.info("System initialization complete")

    def setup_logging(self):
        log_dir = os.path.dirname(self.config['log_file'])
        os.makedirs(log_dir, exist_ok=True)
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                            handlers=[logging.FileHandler(self.config['log_file']), logging.StreamHandler()])
        self.logger = logging.getLogger('PlateRecognition')

    def load_model(self):
        try: self.model = YOLO(self.config['model_path']); self.logger.info("Model loaded")
        except Exception as e: self.logger.error(f"Load model error: {e}"); raise

    def detect_arduino_port(self): # (Identical to car_entry.py)
        ports = list(serial.tools.list_ports.comports())
        system = platform.system()
        for p in ports:
            if "arduino" in p.description.lower() or (p.vid == 0x2341) or (p.vid == 0x2A03) or (p.vid == 0x1A86 and p.pid == 0x7523): return p.device
        for p in ports: # Fallback
            dev = p.device
            if system=='Linux' and ('ttyACM' in dev or 'ttyUSB' in dev): return dev
            if system=='Darwin' and ('usbmodem' in dev or 'usbserial' in dev): return dev
            if system=='Windows' and 'COM' in dev: return dev
        return None
        
    def connect_arduino(self):
        self.arduino = None
        if not self.config['use_arduino']: self.logger.info("Arduino disabled"); return
        try:
            port = self.detect_arduino_port()
            if port: self.arduino = serial.Serial(port, 9600, timeout=1); time.sleep(2); self.logger.info(f"Arduino on {port}")
            else: self.logger.warning("Arduino not detected, simulation mode")
        except serial.SerialException as e: self.logger.error(f"Arduino connect error: {e}")

    def init_camera(self):
        try:
            self.cap = cv2.VideoCapture(self.config['camera_device'])
            if not self.cap.isOpened(): raise IOError("Could not open camera")
            if self.config['camera_width'] and self.config['camera_height']:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config['camera_width'])
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config['camera_height'])
            self.logger.info("Camera initialized")
        except Exception as e: self.logger.error(f"Camera init error: {e}"); raise

    def read_distance(self):
        if self.arduino and self.arduino.is_open and self.arduino.in_waiting > 0:
            try: return float(self.arduino.readline().decode('utf-8').strip())
            except: pass
        return self.mock_ultrasonic_distance()

    def mock_ultrasonic_distance(self): import random; return random.randint(10, 150)

    def control_gate(self, open_gate=True):
        if not self.arduino or not self.arduino.is_open: self.logger.info(f"Gate {'open' if open_gate else 'close'} (SIM)"); return
        try:
            cmd = b'1' if open_gate else b'0'; self.arduino.write(cmd)
            self.logger.info(f"Gate {'opened' if open_gate else 'closed'} (sent '{cmd.decode()}')")
            if open_gate: threading.Timer(self.config['gate_open_duration'], self.control_gate, [False]).start()
        except serial.SerialException as e: self.logger.error(f"Gate control error: {e}")

    def process_plate_image(self, plate_img):
        if plate_img.size == 0: return None
        gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
        kernel = np.ones((1, 1), np.uint8); thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        return cv2.medianBlur(thresh, 3)

    def extract_plate_text(self, processed_img):
        if processed_img is None: return None
        try: return pytesseract.image_to_string(processed_img, config=self.config['tesseract_config']).strip().replace(" ", "")
        except Exception as e: self.logger.error(f"OCR error: {e}"); return None

    def validate_plate(self, plate_text):
        if not plate_text: return None
        matches = re.findall(self.config['plate_regex'], plate_text)
        return matches[0] if matches else None

    def has_unpaid_record_db(self, plate_number):
        conn = db_utils.get_db_connection()
        cursor = conn.cursor()
        record = None
        try:
            cursor.execute("SELECT 1 FROM parking_log WHERE car_plate = ? AND payment_status = 0 LIMIT 1", (plate_number,))
            record = cursor.fetchone()
        except sqlite3.Error as e: self.logger.error(f"[DB_ERROR] Checking unpaid in main: {e}")
        finally:
            if conn: conn.close()
        return record is not None

    def save_plate_entry(self, plate_number):
        conn = db_utils.get_db_connection()
        cursor = conn.cursor()
        try:
            current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("INSERT INTO parking_log (entry_time, car_plate, payment_status) VALUES (?, ?, 0)", (current_time_str, plate_number))
            conn.commit()
            self.logger.info(f"DB entry for {plate_number}")
            if self.config['save_plate_images'] and hasattr(self, 'current_plate_img'):
                fname = f"{plate_number}_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
                cv2.imwrite(os.path.join(self.config['save_dir'], fname), self.current_plate_img)
            return True
        except sqlite3.Error as e: self.logger.error(f"DB save error: {e}"); return False
        finally:
            if conn: conn.close()

    def process_frame(self, frame):
        if frame is None or frame.size == 0: return frame
        try:
            distance = self.read_distance()
            if distance <= self.config['detection_distance']:
                results = self.model(frame)
                for result in results:
                    for box in result.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0]); plate_img = frame[y1:y2, x1:x2]
                        self.current_plate_img = plate_img.copy()
                        processed_img = self.process_plate_image(plate_img)
                        if not processed_img: continue
                        plate_text = self.extract_plate_text(processed_img)
                        if not plate_text: continue
                        valid_plate = self.validate_plate(plate_text)
                        if valid_plate:
                            self.handle_valid_plate(valid_plate)
                            if self.config['debug_mode']: cv2.imshow("Plate", plate_img); cv2.imshow("Processed", processed_img)
                return results[0].plot()
            return frame
        except Exception as e: self.logger.error(f"Frame process error: {e}"); return frame

    def handle_valid_plate(self, plate_number):
        self.plate_buffer.append(plate_number)
        if len(self.plate_buffer) >= self.config['min_plate_detections']:
            counts = Counter(self.plate_buffer); common_plate = counts.most_common(1)[0][0]
            consensus = counts.most_common(1)[0][1] / len(self.plate_buffer)
            if consensus >= self.config['min_consensus_ratio']:
                current_time_ts = time.time()
                if not self.has_unpaid_record_db(common_plate):
                    if (common_plate != self.last_saved_plate or (current_time_ts - self.last_entry_time) > self.config['entry_cooldown']):
                        if self.save_plate_entry(common_plate):
                            self.control_gate(open_gate=True)
                            self.last_saved_plate = common_plate; self.last_entry_time = current_time_ts
                    else: self.logger.info(f"Skipped {common_plate} cooldown/duplicate.")
                else: self.logger.info(f"Skipped {common_plate}, unpaid DB record.")
            else: self.logger.warning(f"Weak consensus for {common_plate}.")
            self.plate_buffer.clear()

    def run(self):
        self.logger.info("Starting system"); self.running = True
        try:
            while self.running:
                ret, frame = self.cap.read()
                if not ret: self.logger.warning("Frame capture fail"); time.sleep(0.1); continue
                processed_frame = self.process_frame(frame)
                cv2.imshow('Plate Recognition System', processed_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): self.logger.info("Exit by user"); break
        except KeyboardInterrupt: self.logger.info("Interrupted by user")
        except Exception as e: self.logger.error(f"Runtime error: {e}")
        finally: self.cleanup()

    def cleanup(self):
        self.logger.info("Cleaning up")
        if self.cap and self.cap.isOpened(): self.cap.release()
        if self.arduino and self.arduino.is_open:
            try: self.arduino.write(b'0'); time.sleep(0.5); self.arduino.close()
            except serial.SerialException: pass
        cv2.destroyAllWindows(); self.logger.info("Shutdown complete")

def parse_arguments():
    parser = argparse.ArgumentParser(description='License Plate Recognition System')
    parser.add_argument('--model', type=str, default='../model_dev/runs/detect/train/weights/best.pt')
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--arduino', action='store_true', default=True)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--save-images', action='store_true')
    return parser.parse_args()

def main():
    args = parse_arguments()
    config = {
        'model_path': args.model, 'camera_device': args.camera, 'camera_width': 1280, 'camera_height': 720,
        'use_arduino': args.arduino, 'debug_mode': args.debug, 'save_plate_images': args.save_images,
        'save_dir': 'plates', 'log_file': 'logs/plate_recognition.log',
        'detection_distance': 50, 'entry_cooldown': 300, 'gate_open_duration': 15,
        'min_plate_detections': 3, 'min_consensus_ratio': 0.7,
        'plate_regex': r'(RA[A-Z]\d{3}[A-Z])',
        'tesseract_config': '--psm 8 --oem 3 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    }
    system = PlateRecognitionSystem(config)
    system.run()

if __name__ == "__main__":
    main()