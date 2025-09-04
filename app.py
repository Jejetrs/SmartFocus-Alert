from flask import Flask, render_template, request, Response, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename
import mediapipe as mp
import numpy as np
from scipy.spatial import distance as dis
import cv2 as cv
import os
import time
import uuid
from datetime import datetime, timedelta
import json
import threading
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as ReportLabImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
import base64
import tempfile
import shutil
import traceback
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

application = Flask(__name__)

# Konfigurasi
application.config['UPLOAD_FOLDER'] = '/tmp/uploads'
application.config['DETECTED_FOLDER'] = '/tmp/detected'
application.config['REPORTS_FOLDER'] = '/tmp/reports'
application.config['RECORDINGS_FOLDER'] = '/tmp/recordings'
application.config['MAX_CONTENT_PATH'] = 10000000

for folder in [application.config['UPLOAD_FOLDER'], application.config['DETECTED_FOLDER'], 
               application.config['REPORTS_FOLDER'], application.config['RECORDINGS_FOLDER']]:
    try:
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
            os.chmod(folder, 0o755)
        print(f"Directory ready: {folder}")
    except Exception as e:
        print(f"Error creating directory {folder}: {str(e)}")

# Global variables
monitoring_lock = threading.RLock()
live_monitoring_active = False

# Data Sesi
session_data = {
    'start_time': None,
    'end_time': None,
    'detections': [],
    'alerts': [],
    'focus_statistics': {
        'total_focused_time': 0,
        'total_unfocused_time': 0,
        'total_yawning_time': 0,
        'total_sleeping_time': 0,
        'total_no_person_time': 0,
        'total_persons': 0,
        'total_detections': 0
    },
    'recording_path': None,
    'recording_frames': [],
    'session_id': None,
    'client_alerts': [],
    'frame_counter': 0,
    'frame_timestamps': [],
    'total_frames_processed': 0
}

# Variabel video recording
video_writer = None
recording_active = False

current_person_state = None
person_state_start_time = None
last_alert_times = {}
session_start_time = None
no_person_state = {
    'active': False,
    'start_time': None,
    'last_alert_time': 0,
    'total_duration': 0 
}

# Konfigurasi Alert
DISTRACTION_THRESHOLDS = {
    'SLEEPING': 8,      # 8 detik
    'YAWNING': 3.5,     # 3.5 detik
    'NOT FOCUSED': 8,   # 8 detik
    'NO PERSON': 10     # 10 detik
}

ALERT_COOLDOWN = 5.0

# Rekaman Frame
FRAME_STORAGE_INTERVAL = 2
MAX_STORED_FRAMES = 3000
RECORDING_FPS = 5

# MediaPipe
face_detection = None
face_mesh = None

def init_mediapipe():
    """Initialize MediaPipe"""
    global face_detection, face_mesh
    try:
        face_detection = mp.solutions.face_detection.FaceDetection(
            model_selection=1,
            min_detection_confidence=0.5
        )
        face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=8,  # Allow multiple faces for upload mode
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        logger.info("MediaPipe initialized successfully")
        return True
    except Exception as e:
        logger.error(f"MediaPipe initialization failed: {str(e)}")
        return False

def draw_landmarks(image, landmarks, land_mark, color):
    """Draw landmarks on the image."""
    height, width = image.shape[:2]
    for face in land_mark:
        point = landmarks.landmark[face]
        point_scale = (int(point.x * width), int(point.y * height))     
        cv.circle(image, point_scale, 1, color, 1)

def calculate_ear(eye_points):
    """ Calculate Eye Aspect Ratio (EAR), Using: (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)"""
    A = dis.euclidean(eye_points[1], eye_points[5])  # p2 - p6
    B = dis.euclidean(eye_points[2], eye_points[4])  # p3 - p5
    C = dis.euclidean(eye_points[0], eye_points[3])  # p1 - p4

    if C == 0:
        return 0.0
    ear = (A + B) / (2.0 * C)
    return ear

def calculate_midpoint(points):
    """Calculate the midpoint of a set of points."""
    x_coords = [p[0] for p in points]
    y_coords = [p[1] for p in points]
    return (sum(x_coords) // len(x_coords), sum(y_coords) // len(y_coords))

def check_iris_in_middle(left_eye_points, left_iris_points, right_eye_points, right_iris_points):
    """Check if the iris is approximately centered in both eyes."""
    left_eye_mid = calculate_midpoint(left_eye_points)
    right_eye_mid = calculate_midpoint(right_eye_points)
    left_iris_mid = calculate_midpoint(left_iris_points)
    right_iris_mid = calculate_midpoint(right_iris_points)
    threshold = 2.5
    
    return (
        abs(left_iris_mid[0] - left_eye_mid[0]) <= threshold and 
        abs(right_iris_mid[0] - right_eye_mid[0]) <= threshold
    )

def model_detect(frame, landmarks):
    """Detect user attention state based on EAR, MAR, and iris location."""
    COLOR_RED = (0, 0, 255)
    COLOR_BLUE = (255, 0, 0)
    COLOR_GREEN = (0, 255, 0)
    COLOR_MAGENTA = (255, 0, 255)

    # Landmark
    LEFT_EYE = [362, 385, 387, 263, 373, 380]   # p1–p6
    RIGHT_EYE = [33, 160, 158, 133, 153, 144]   # p1–p6

    LEFT_IRIS = [474, 475, 476, 477]
    RIGHT_IRIS = [469, 470, 471, 472]

    UPPER_LOWER_LIPS = [13, 14]
    LEFT_RIGHT_LIPS = [78, 308]

    FACE = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400,
            377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]

    try:
        # Desain facial landmarks
        draw_landmarks(frame, landmarks, FACE, COLOR_GREEN)
        draw_landmarks(frame, landmarks, LEFT_EYE, COLOR_RED)
        draw_landmarks(frame, landmarks, RIGHT_EYE, COLOR_RED)
        draw_landmarks(frame, landmarks, UPPER_LOWER_LIPS, COLOR_BLUE)
        draw_landmarks(frame, landmarks, LEFT_RIGHT_LIPS, COLOR_BLUE)

        img_h, img_w = frame.shape[:2]
        mesh_points = [(int(p.x * img_w), int(p.y * img_h)) for p in landmarks.landmark]
        mesh_points = np.array(mesh_points)

        # Extract landmarks
        left_eye_pts = mesh_points[LEFT_EYE]
        right_eye_pts = mesh_points[RIGHT_EYE]
        left_iris_pts = mesh_points[LEFT_IRIS]
        right_iris_pts = mesh_points[RIGHT_IRIS]

        # EAR
        left_ear = calculate_ear(left_eye_pts)
        right_ear = calculate_ear(right_eye_pts)
        avg_ear = (left_ear + right_ear) / 2.0

        # MAR (mouth aspect ratio)
        A = dis.euclidean(mesh_points[UPPER_LOWER_LIPS[0]], mesh_points[UPPER_LOWER_LIPS[1]])
        B = dis.euclidean(mesh_points[LEFT_RIGHT_LIPS[0]], mesh_points[LEFT_RIGHT_LIPS[1]])
        mar = A / B if B != 0 else 0.0

        # Iris
        focused = check_iris_in_middle(left_eye_pts, left_iris_pts, right_eye_pts, right_iris_pts)

        # Visualisasi lingkaran iris
        try:
            (lx, ly), lr = cv.minEnclosingCircle(left_iris_pts)
            (rx, ry), rr = cv.minEnclosingCircle(right_iris_pts)
            cv.circle(frame, (int(lx), int(ly)), int(lr), COLOR_MAGENTA, 1)
            cv.circle(frame, (int(rx), int(ry)), int(rr), COLOR_MAGENTA, 1)
        except:
            pass

        # Logika Kondisi
        eyes_closed = avg_ear < 0.15
        is_yawning = mar > 0.5
        not_focused = not focused

        if eyes_closed:
            state = "SLEEPING"
        elif is_yawning:
            state = "YAWNING"
        elif not_focused:
            state = "NOT FOCUSED"
        else:
            state = "FOCUSED"

        status = {
            "eyes_closed": eyes_closed,
            "yawning": is_yawning,
            "not_focused": not_focused,
            "focused": focused,
            "state": state,
            "EAR": round(avg_ear, 3),
            "MAR": round(mar, 3)
        }

        return status, state

    except Exception as e:
        print(f"Detection error: {str(e)}")
        return {"state": "FOCUSED"}, "FOCUSED"

def handle_no_person_detection(current_time, mode="video"):
    """NO PERSON state detection and alerts"""
    global no_person_state, session_data, live_monitoring_active
    
    if mode != "video" or not live_monitoring_active:
        return 0
    
    # NO PERSON tracking
    if not no_person_state['active']:
        no_person_state['active'] = True
        no_person_state['start_time'] = current_time
        logger.info("Started NO PERSON tracking")
        return 0
    
    # Akumulasi durasi saat ini
    if no_person_state['start_time']:
        duration = current_time - no_person_state['start_time']
        threshold = DISTRACTION_THRESHOLDS['NO PERSON']
        
        # Check threshold
        if duration >= threshold:
            last_alert_time = no_person_state.get('last_alert_time', 0)
            
            if last_alert_time == 0:
                # Initial NO PERSON alert
                trigger_alert("System", "NO PERSON", duration, False)
                no_person_state['last_alert_time'] = current_time
                logger.info(f"First NO PERSON alert after {duration:.1f}s")
            elif current_time - last_alert_time >= ALERT_COOLDOWN:
                # Reminder NO PERSON alert
                trigger_alert("System", "NO PERSON", duration, True)
                no_person_state['last_alert_time'] = current_time
                logger.info(f"Reminder NO PERSON alert ({duration:.1f}s total)")
        
        return duration
    
    return 0

def reset_no_person_state():
    """Reset NO PERSON state when person is detected"""
    global no_person_state, session_data
    
    if no_person_state['active'] and no_person_state['start_time']:
        # Kalkulasi dan akumulasi durasi deteksi NO PERSON
        current_time = time.time()
        duration = current_time - no_person_state['start_time']
        
        # Tambahkan ke total durasi deteksi
        no_person_state['total_duration'] += duration
        
        # Update statistik sesi
        with monitoring_lock:
            if live_monitoring_active and session_data.get('start_time'):
                session_data['focus_statistics']['total_no_person_time'] += duration
        
        logger.info(f"Accumulated NO PERSON time: {duration:.1f}s (Total: {no_person_state['total_duration']:.1f}s)")
        
        # Reset status
        no_person_state['active'] = False
        no_person_state['start_time'] = None
        no_person_state['last_alert_time'] = 0

def update_person_state(current_state, current_time):
    """Update state tracking"""
    global current_person_state, person_state_start_time, session_data, last_alert_times
    
    # Initialize if first time
    if person_state_start_time is None:
        person_state_start_time = current_time
        last_alert_times = {}
    
    previous_state = current_person_state
    
    # State change detected
    if previous_state != current_state:
        logger.debug(f"Person state: {previous_state} -> {current_state}")
        
        if previous_state and previous_state in DISTRACTION_THRESHOLDS and person_state_start_time:
            session_duration = current_time - person_state_start_time
            logger.debug(f"Closed {previous_state} session: {session_duration:.2f}s")
        
        # Update status
        current_person_state = current_state
        person_state_start_time = current_time
        
        # Hapus pengingat waktu untuk status baru
        if current_state in last_alert_times:
            del last_alert_times[current_state]
    
    # Kalkulasi durasi terkini untuk pengecekan alert
    if current_state in DISTRACTION_THRESHOLDS and person_state_start_time:
        current_duration = current_time - person_state_start_time
        return current_duration
    
    return 0

def should_trigger_alert(current_state, current_duration):
    """Check if alert should be triggered for person"""
    global last_alert_times
    
    if current_state not in DISTRACTION_THRESHOLDS:
        return False, False
    
    threshold = DISTRACTION_THRESHOLDS[current_state]
    current_time = time.time()
    
    # Cek durasi threshold
    if current_duration < threshold:
        return False, False
    
    # Cek alert timing
    if current_state not in last_alert_times:
        # Initial alert untuk suatu status
        logger.info(f"First alert: {current_state} after {current_duration:.1f}s")
        return True, False
    else:
        # Cooldown reminder
        time_since_last = current_time - last_alert_times[current_state]
        if time_since_last >= ALERT_COOLDOWN:
            logger.info(f"Reminder alert: {current_state} ({current_duration:.1f}s total)")
            return True, True
    
    return False, False

def trigger_alert(person_label, alert_type, duration, is_reminder=False):
    """Alert triggering with proper NO PERSON support"""
    global session_data, last_alert_times
    
    alert_time = datetime.now().strftime("%H:%M:%S")
    current_time = time.time()
    
    # Menangani peringatan dengan tipe yang berbeda
    if alert_type == 'NO PERSON':
        display_message = 'No person detected - please return to your seat!'
    else:
        #  Pembaruan waktu peringatan terakhir dengan kondisi terkini
        if alert_type not in last_alert_times:
            last_alert_times[alert_type] = current_time
        else:
            last_alert_times[alert_type] = current_time
        
        # Pesan Peringatan
        if alert_type == 'SLEEPING':
            display_message = 'You are sleeping - please wake up!'
        elif alert_type == 'YAWNING':
            display_message = 'You are yawning - please take a rest!'
        elif alert_type == 'NOT FOCUSED':
            display_message = 'You are not focused - please focus on screen!'
        else:
            return
    
    # Simpan peringatan ke dalam session data
    with monitoring_lock:
        if live_monitoring_active and session_data and session_data.get('start_time'):
            alert_entry = {
                'timestamp': datetime.now().isoformat(),
                'person': person_label,
                'detection': alert_type,
                'message': display_message,
                'duration': int(duration),
                'alert_time': alert_time,
                'real_time_duration': duration,
                'is_reminder': is_reminder
            }
            session_data['alerts'].append(alert_entry)
            logger.info(f"Alert stored - {display_message} (Duration: {duration:.1f}s)")

def calculate_distraction_times():
    """Calculate distraction times"""
    global session_data, no_person_state
    
    totals = {
        'total_unfocused_time': 0,
        'total_yawning_time': 0,
        'total_sleeping_time': 0,
        'total_no_person_time': 0,
        'total_focused_time': 0
    }
    
    current_time = time.time()
    
    # Kalkulasi alert tersimpan
    if session_data and session_data.get('alerts'):
        for alert in session_data['alerts']:
            alert_type = alert.get('detection', '')
            duration = alert.get('real_time_duration', alert.get('duration', 0))
            
            if alert_type == 'NOT FOCUSED':
                totals['total_unfocused_time'] += duration
            elif alert_type == 'YAWNING':
                totals['total_yawning_time'] += duration
            elif alert_type == 'SLEEPING':
                totals['total_sleeping_time'] += duration
            elif alert_type == 'NO PERSON':
                totals['total_no_person_time'] += duration
    
    # Menambahkan waktu aktif "NO PERSON" saat ini
    if no_person_state['active'] and no_person_state['start_time']:
        current_no_person_duration = current_time - no_person_state['start_time']
        totals['total_no_person_time'] += current_no_person_duration
    
    # Menambahkan akumulasi waktu "NO PERSON"
    totals['total_no_person_time'] += no_person_state.get('total_duration', 0)
    
    # Menghitung waktu fokus
    if session_data and session_data.get('start_time'):
        if session_data.get('end_time'):
            total_session_time = (session_data['end_time'] - session_data['start_time']).total_seconds()
        else:
            total_session_time = current_time - time.mktime(session_data['start_time'].timetuple())
        
        total_distraction_time = (totals['total_unfocused_time'] + 
                                totals['total_yawning_time'] + 
                                totals['total_sleeping_time'] +
                                totals['total_no_person_time'])
        totals['total_focused_time'] = max(0, total_session_time - total_distraction_time)
    
    return totals

def detect_persons_with_attention(image, mode="image"):
    """Person detection with mode support for single vs multiple detection"""
    global live_monitoring_active, session_data, face_detection, face_mesh
    global current_person_state, person_state_start_time, no_person_state
    
    if face_detection is None or face_mesh is None:
        if not init_mediapipe():
            logger.error("MediaPipe not available")
            return image, []

    rgb_image = cv.cvtColor(image, cv.COLOR_BGR2RGB)
    
    try:
        detection_results = face_detection.process(rgb_image)
        mesh_results = face_mesh.process(rgb_image)
    except Exception as e:
        logger.error(f"MediaPipe processing error: {str(e)}")
        return image, []
    
    detections = []
    ih, iw, _ = image.shape
    current_time = time.time()
    
    with monitoring_lock:
        is_monitoring_active = live_monitoring_active
        current_session_data = session_data.copy() if session_data else None
    
    # Penanganan deteksi NO PERSON untuk mode video live
    if not detection_results.detections:
        if mode == "video" and is_monitoring_active:
            no_person_duration = handle_no_person_detection(current_time, mode)
            
            cv.putText(image, "NO PERSON DETECTED", (10, 60), 
                      cv.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
            
            if no_person_duration > 0:
                threshold = DISTRACTION_THRESHOLDS['NO PERSON']
                timer_text = f"No person: {no_person_duration:.1f}s/{threshold}s"
                cv.putText(image, timer_text, (10, 100), 
                          cv.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)
        
        cv.putText(image, "No person detected", 
                  (10, 30), cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        
        return image, detections
    
    # Reset status NO PERSON ketika sudah terdeteksi person
    if mode == "video" and is_monitoring_active:
        reset_no_person_state()
    
    # Tampilkan jumlah deteksi
    if mode == "video":
        # Live monitoring: hanya proses satu wajah pertama
        faces_to_process = detection_results.detections[:1]
        max_faces = 1
    else:
        # Upload mode: proses semua wajah yang terdeteksi
        faces_to_process = detection_results.detections
        max_faces = len(detection_results.detections)
    
    # Proses setiap wajah terdeteksi
    for face_idx, detection in enumerate(faces_to_process):
        bboxC = detection.location_data.relative_bounding_box
        x, y, w, h = int(bboxC.xmin * iw), int(bboxC.ymin * ih), \
                     int(bboxC.width * iw), int(bboxC.height * ih)
        
        # bounding box
        x = max(0, x)
        y = max(0, y)
        w = min(w, iw - x)
        h = min(h, ih - y)
        
        confidence_score = detection.score[0]
        
        # Status Perhatian
        attention_status = {
            "eyes_closed": False,
            "yawning": False,
            "not_focused": False,
            "state": "FOCUSED"
        }
        
        # Hubungkan face mesh dengan deteksi
        matched_face_idx = -1
        if mesh_results.multi_face_landmarks and face_idx < len(mesh_results.multi_face_landmarks):
            face_landmarks = mesh_results.multi_face_landmarks[face_idx]
            min_x, min_y = float('inf'), float('inf')
            max_x, max_y = 0, 0
            
            for landmark in face_landmarks.landmark:
                landmark_x, landmark_y = int(landmark.x * iw), int(landmark.y * ih)
                min_x = min(min_x, landmark_x)
                min_y = min(min_y, landmark_y)
                max_x = max(max_x, landmark_x)
                max_y = max(max_y, landmark_y)
            
            mesh_center_x = (min_x + max_x) // 2
            mesh_center_y = (min_y + max_y) // 2
            det_center_x = x + w // 2
            det_center_y = y + h // 2
            
            # Cek jika bounding box deteksi wajah dan mesh beririsan
            if (abs(mesh_center_x - det_center_x) < w // 2 and 
                abs(mesh_center_y - det_center_y) < h // 2):
                matched_face_idx = face_idx
        
        # Tampilkan detail deteksi
        if matched_face_idx != -1 and matched_face_idx < len(mesh_results.multi_face_landmarks):
            attention_status, state = model_detect(image, mesh_results.multi_face_landmarks[matched_face_idx])
        
        status_text = attention_status.get("state", "FOCUSED")
        
        # Pelacakan Sesi untuk live monitoring
        session_duration = 0
        if mode == "video" and is_monitoring_active and face_idx == 0:
            session_duration = update_person_state(status_text, current_time)
            
            # Cek jika alert harus dipicu
            should_trigger, is_reminder = should_trigger_alert(status_text, session_duration)
            if should_trigger:
                logger.info(f"Triggering alert - {status_text} - Duration: {session_duration:.1f}s")
                trigger_alert("You", status_text, session_duration, is_reminder)
        
        # Visualisasi distraksi
        if mode == "video" and is_monitoring_active:
            status_colors = {
                "FOCUSED": (0, 255, 0),
                "NOT FOCUSED": (0, 165, 255),
                "YAWNING": (0, 255, 255),
                "SLEEPING": (0, 0, 255)
            }
            
            main_color = status_colors.get(status_text, (0, 255, 0))
            
            # Primary person
            border_thickness = 3 if face_idx == 0 else 2
            cv.rectangle(image, (x, y), (x + w, y + h), main_color, border_thickness)
            
            # Display Timer
            if face_idx == 0 and status_text in DISTRACTION_THRESHOLDS:
                threshold = DISTRACTION_THRESHOLDS[status_text]
                timer_text = f"Status: {status_text} ({session_duration:.1f}s/{threshold}s)"
            else:
                timer_text = f"Person {face_idx + 1}: {status_text}"
            
            # Latar belakang teks
            font = cv.FONT_HERSHEY_SIMPLEX
            font_scale = 0.7
            thickness = 2
            (text_width, text_height), baseline = cv.getTextSize(timer_text, font, font_scale, thickness)
            
            text_y = y - 10 if face_idx == 0 else y + h + text_height + 10
            if text_y < text_height + 10:
                text_y = y + h + text_height + 10
            
            overlay = image.copy()
            cv.rectangle(overlay, (x, text_y - text_height - 5), (x + text_width + 10, text_y + 5), (0, 0, 0), -1)
            cv.addWeighted(overlay, 0.7, image, 0.3, 0, image)
            
            cv.putText(image, timer_text, (x + 5, text_y), font, font_scale, main_color, thickness)
        else:
            # Analisis statis untuk upload mode
            cv.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
            
            # Label Person
            person_label = f"Person {face_idx + 1}"
            # cv.putText(image, person_label, (x, y - 10), cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # Informasi box positioning
            info_y_start = y + h + 10
            box_padding = 10
            line_height = 20
            box_height = 4 * line_height
            
            # Penyesuaian posisi box informasi
            if info_y_start + box_height > ih:
                info_y_start = y - box_height - 10
            
            overlay = image.copy()
            cv.rectangle(overlay, 
                        (x - box_padding, info_y_start - box_padding), 
                        (x + w + box_padding, info_y_start + box_height), 
                        (0, 0, 0), -1)
            cv.addWeighted(overlay, 0.6, image, 0.4, 0, image)
            
            font = cv.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5
            font_color = (255, 255, 255)
            thickness = 1
            
            cv.putText(image, f"{person_label} Detected", (x, info_y_start), 
                    font, font_scale, (50, 205, 50), thickness+1)
            cv.putText(image, f"Confidence: {confidence_score*100:.2f}%", 
                    (x, info_y_start + line_height), font, font_scale, font_color, thickness)
           
            status_color = {
                "FOCUSED": (0, 255, 0),
                "NOT FOCUSED": (255, 165, 0),
                "YAWNING": (255, 255, 0),
                "SLEEPING": (0, 0, 255)
            }
            color = status_color.get(status_text, (0, 255, 0))
            
            cv.putText(image, f"Status: {status_text}", 
                    (x, info_y_start + 2*line_height), font, font_scale, color, thickness)

        # Simpan wajah yang terdeteksi
        face_img = image[y:y+h, x:x+w]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        face_filename = f"person_{face_idx + 1}_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
        face_path = os.path.join(application.config['DETECTED_FOLDER'], face_filename)
        
        if face_img.size > 0:
            try:
                cv.imwrite(face_path, face_img)
            except Exception as e:
                logger.error(f"Error saving face image: {str(e)}")
        
        # Buat Hasil Deteksi
        detections.append({
            "id": face_idx + 1, 
            "confidence": float(confidence_score),
            "bbox": [x, y, w, h],
            "image_path": f"/static/detected/{face_filename}",
            "status": status_text,
            "timestamp": datetime.now().isoformat(),
            "duration": session_duration if mode == "video" and face_idx == 0 else 0
        })
    
    # Display Perhitungan Deteksi
    if detections:
        if mode == "video":
            cv.putText(image, f"Person detected", 
                      (10, 30), cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            cv.putText(image, f"{len(detections)} person(s) detected", 
                      (10, 30), cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    else:
        cv.putText(image, "No person detected", 
                  (10, 30), cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    
    return image, detections

def update_session_statistics(detections):
    """Update session statistics"""
    global session_data
    
    if not detections:
        return
    
    with monitoring_lock:
        if session_data and session_data.get('start_time'):
            session_data['detections'].extend(detections)
            session_data['focus_statistics']['total_detections'] += len(detections)
            session_data['focus_statistics']['total_persons'] = 1 if detections else 0
            
            # Update statistics waktu
            totals = calculate_distraction_times()
            session_data['focus_statistics']['total_focused_time'] = totals['total_focused_time']
            session_data['focus_statistics']['total_unfocused_time'] = totals['total_unfocused_time']
            session_data['focus_statistics']['total_yawning_time'] = totals['total_yawning_time']
            session_data['focus_statistics']['total_sleeping_time'] = totals['total_sleeping_time']
            session_data['focus_statistics']['total_no_person_time'] = totals['total_no_person_time']

def create_session_recording_from_frames(recording_frames, output_path, session_start_time, session_end_time):
    """Create video recording from frames"""
    try:
        if not recording_frames:
            logger.warning("No frames available for video creation")
            return None

        actual_duration = session_end_time - session_start_time
        actual_duration_seconds = actual_duration.total_seconds()
        
        if actual_duration_seconds <= 0:
            logger.error("Invalid session duration")
            return None

        fps = RECORDING_FPS
        total_frames_needed = int(fps * actual_duration_seconds)
        if total_frames_needed <= 0:
            total_frames_needed = len(recording_frames) * 5
        
        frame_repeat_count = max(1, total_frames_needed // len(recording_frames))
        
        height, width = recording_frames[0].shape[:2]
        fourcc = cv.VideoWriter_fourcc(*'mp4v')
        out = cv.VideoWriter(output_path, fourcc, fps, (width, height))

        if not out.isOpened():
            logger.error(f"Could not open video writer: {output_path}")
            return None

        frames_written = 0
        for i, frame in enumerate(recording_frames):
            if frame is not None and frame.size > 0:
                for repeat in range(frame_repeat_count):
                    out.write(frame)
                    frames_written += 1

        out.release()
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            logger.info(f"Video recording created: {output_path} ({frames_written} frames)")
            return output_path
        else:
            logger.error("Failed to create valid video recording")
            return None

    except Exception as e:
        logger.error(f"Video recording creation error: {str(e)}")
        return None

def generate_live_pdf_report(session_data, output_path):
    """Laporan PDF untuk sesi live monitoring"""
    try:
        doc = SimpleDocTemplate(output_path, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=22,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#3B82F6')
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.HexColor('#1F2937')
        )
        
        story.append(Paragraph("Smart Focus Alert - Live Report", title_style))
        story.append(Spacer(1, 20))
        
        # Durasi Sesi 
        if session_data['start_time'] and session_data['end_time']:
            duration = session_data['end_time'] - session_data['start_time']
            total_session_seconds = duration.total_seconds()
            duration_str = str(duration).split('.')[0]
        else:
            total_session_seconds = 0
            duration_str = "N/A"
        
        # Alert counting
        unfocused_time = 0
        yawning_time = 0
        sleeping_time = 0
        no_person_time = 0
        
        alert_counts = {'SLEEPING': 0, 'YAWNING': 0, 'NOT FOCUSED': 0, 'NO PERSON': 0}
        initial_alerts = {'SLEEPING': 0, 'YAWNING': 0, 'NOT FOCUSED': 0, 'NO PERSON': 0}
        reminder_alerts = {'SLEEPING': 0, 'YAWNING': 0, 'NOT FOCUSED': 0, 'NO PERSON': 0}
        
        alert_durations_by_type = {}
        for alert in session_data.get('alerts', []):
            alert_type = alert.get('detection', '')
            duration = alert.get('real_time_duration', alert.get('duration', 0))
            is_reminder = alert.get('is_reminder', False)
            
            if alert_type in alert_counts:
                alert_counts[alert_type] += 1
                if is_reminder:
                    reminder_alerts[alert_type] += 1
                else:
                    initial_alerts[alert_type] += 1
            
            if alert_type not in alert_durations_by_type:
                alert_durations_by_type[alert_type] = []
            alert_durations_by_type[alert_type].append(duration)
        
        unfocused_time = sum(alert_durations_by_type.get('NOT FOCUSED', []))
        yawning_time = sum(alert_durations_by_type.get('YAWNING', []))
        sleeping_time = sum(alert_durations_by_type.get('SLEEPING', []))
        no_person_time = sum(alert_durations_by_type.get('NO PERSON', []))
        
        total_distraction_time = unfocused_time + yawning_time + sleeping_time + no_person_time
        focused_time = max(0, total_session_seconds - total_distraction_time)
        
        if total_session_seconds > 0:
            focus_accuracy = (focused_time / total_session_seconds) * 100
            distraction_percentage = (total_distraction_time / total_session_seconds) * 100
        else:
            focus_accuracy = 0
            distraction_percentage = 0
        
        # Focus rating
        if focus_accuracy >= 90:
            focus_rating = "Excellent"
            rating_color = colors.HexColor('#10B981')
        elif focus_accuracy >= 75:
            focus_rating = "Good"
            rating_color = colors.HexColor('#3B82F6')
        elif focus_accuracy >= 60:
            focus_rating = "Fair"
            rating_color = colors.HexColor('#F59E0B')
        elif focus_accuracy >= 40:
            focus_rating = "Poor"
            rating_color = colors.HexColor('#EF4444')
        else:
            focus_rating = "Very Poor"
            rating_color = colors.HexColor('#DC2626')
        
        def format_time(seconds):
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        
        # Info Sesi
        story.append(Paragraph("Session Information", heading_style))
        
        session_info = [
            ['Session Start Time', session_data.get('start_time', datetime.now()).strftime('%m/%d/%Y, %I:%M:%S %p')],
            ['Session Duration', duration_str],
            ['Total Detections', str(session_data['focus_statistics']['total_detections'])],
            ['Total Alerts', str(len(session_data['alerts']))],
            ['Frames Recorded', str(len(session_data.get('recording_frames', [])))]
        ]
        
        session_table = Table(session_info, colWidths=[2*inch, 4*inch])
        session_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F3F4F6')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        story.append(session_table)
        story.append(Spacer(1, 25))
        
        # Statistik Alert 
        story.append(Paragraph("Alert Statistics", heading_style))
        
        alert_stats = [
            ['Alert Type', 'Total Alerts', 'Initial Alerts', 'Reminder Alerts', 'Total Duration'],
            ['Sleeping', str(alert_counts['SLEEPING']), str(initial_alerts['SLEEPING']), str(reminder_alerts['SLEEPING']), format_time(sleeping_time)],
            ['Yawning', str(alert_counts['YAWNING']), str(initial_alerts['YAWNING']), str(reminder_alerts['YAWNING']), format_time(yawning_time)],
            ['Not Focused', str(alert_counts['NOT FOCUSED']), str(initial_alerts['NOT FOCUSED']), str(reminder_alerts['NOT FOCUSED']), format_time(unfocused_time)],
            ['No Person', str(alert_counts['NO PERSON']), str(initial_alerts['NO PERSON']), str(reminder_alerts['NO PERSON']), format_time(no_person_time)]
        ]
        
        alert_stats_table = Table(alert_stats, colWidths=[1.2*inch, 1.2*inch, 1.2*inch, 1.2*inch, 1.2*inch])
        alert_stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3B82F6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')])
        ]))
        
        story.append(alert_stats_table)
        story.append(Spacer(1, 25))
        
        # Akurasi Focus 
        story.append(Paragraph("Focus Accuracy Summary", heading_style))
        
        accuracy_text = f"<para align=center><font size=18 color='{rating_color.hexval()}'><b>{focus_accuracy:.1f}%</b></font></para>"
        story.append(Paragraph(accuracy_text, styles['Normal']))
        story.append(Spacer(1, 15))
        
        rating_text = f"<para align=center><font size=16 color='{rating_color.hexval()}'><b>Focus Quality: {focus_rating}</b></font></para>"
        story.append(Paragraph(rating_text, styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Time breakdown
        focus_breakdown = [
            ['Metric', 'Time', 'Percentage'],
            ['Total Focused Time', format_time(focused_time), f"{(focused_time/total_session_seconds*100):.1f}%" if total_session_seconds > 0 else "0%"],
            ['Total Distraction Time', format_time(total_distraction_time), f"{distraction_percentage:.1f}%"],
            ['- Unfocused Time', format_time(unfocused_time), f"{(unfocused_time/total_session_seconds*100):.1f}%" if total_session_seconds > 0 else "0%"],
            ['- Yawning Time', format_time(yawning_time), f"{(yawning_time/total_session_seconds*100):.1f}%" if total_session_seconds > 0 else "0%"],
            ['- Sleeping Time', format_time(sleeping_time), f"{(sleeping_time/total_session_seconds*100):.1f}%" if total_session_seconds > 0 else "0%"],
            ['- No Person Time', format_time(no_person_time), f"{(no_person_time/total_session_seconds*100):.1f}%" if total_session_seconds > 0 else "0%"]
        ]
        
        breakdown_table = Table(focus_breakdown, colWidths=[2*inch, 2*inch, 2*inch])
        breakdown_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3B82F6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')]),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#ECFDF5')),
            ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#065F46')),
            ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#FEF2F2')),
            ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor('#991B1B')),
        ]))
        
        story.append(breakdown_table)
        story.append(Spacer(1, 15))
        
        # History Alert 
        if session_data['alerts']:
            story.append(Paragraph("Alert History", heading_style))
            
            alert_headers = ['Time', 'Detection', 'Duration', 'Message']
            alert_data = [alert_headers]
            
            for alert in session_data['alerts'][-20:]:
                try:
                    alert_time = datetime.fromisoformat(alert['timestamp']).strftime('%I:%M:%S %p')
                except:
                    alert_time = alert.get('alert_time', 'N/A')
                
                duration = alert.get('real_time_duration', alert.get('duration', 0))
                duration_text = f"{duration:.0f}s" if duration > 0 else "N/A"
                
                alert_data.append([
                    alert_time,
                    alert['detection'],
                    duration_text,
                    alert['message']
                ])
            
            alert_table = Table(alert_data, colWidths=[0.8*inch, 1*inch, 0.6*inch, 3.6*inch])
            alert_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3B82F6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')])
            ]))
            
            story.append(alert_table)
        
        # Footer
        story.append(Spacer(1, 5))
        footer_text = f"Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br/>Smart Focus Alert"
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=10,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#6B7280')
        )
        story.append(Paragraph(footer_text, footer_style))
        
        doc.build(story)
        logger.info(f"PDF report generated: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"PDF generation error: {str(e)}")
        traceback.print_exc()
        return None

def process_video_file(video_path):
    """Process video file and collect all detections"""
    cap = cv.VideoCapture(video_path)
    fps = cap.get(cv.CAP_PROP_FPS)
    width = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"processed_{timestamp}_{uuid.uuid4().hex[:8]}.mp4"
    output_path = os.path.join(application.config['DETECTED_FOLDER'], output_filename)
    
    fourcc = cv.VideoWriter_fourcc(*'mp4v')
    out = cv.VideoWriter(output_path, fourcc, fps, (width, height))
    
    all_detections = []
    frame_count = 0
    process_every_n_frames = 5  # proses setiap 5 langkah video
    
    logger.info("Starting video processing...")
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        
        if frame_count % process_every_n_frames == 0:
            # Proses frame untuk deteksi distrak
            processed_frame, detections = detect_persons_with_attention(frame, mode="upload")
            
            # Add frame timestamp to each detection
            for detection in detections:
                detection['frame_number'] = frame_count
                detection['frame_time'] = frame_count / fps if fps > 0 else 0
            
            # Kumpulkan semua deteksi
            all_detections.extend(detections)
            
            if frame_count % 100 == 0:  # Log proses setiap 100 frame
                logger.info(f"Processed {frame_count} frames, found {len(detections)} detections in current frame")
        else:
            processed_frame = frame
            
        out.write(processed_frame)
    
    cap.release()
    out.release()
    
    logger.info(f"Video processing completed: {output_path}")
    logger.info(f"Total frames processed: {frame_count}")
    logger.info(f"Total detections collected: {len(all_detections)}")
    
    # Log ringkasan deteksi
    if all_detections:
        status_summary = {}
        person_summary = {}
        
        for detection in all_detections:
            status = detection.get('status', 'UNKNOWN')
            person_id = detection.get('id', 'UNKNOWN')
            
            status_summary[status] = status_summary.get(status, 0) + 1
            person_summary[person_id] = person_summary.get(person_id, 0) + 1
        
        logger.info(f"Detection status summary: {status_summary}")
        logger.info(f"Person detection summary: {person_summary}")
    
    return output_path, all_detections

def generate_upload_pdf_report(detections, file_info, output_path):
    """Analisis laporan PDF  untuk file upload uploaded """
    doc = SimpleDocTemplate(output_path, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=22,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#3B82F6')
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=12,
        spaceBefore=20,
        textColor=colors.HexColor('#1F2937')
    )
    
    story.append(Paragraph("Smart Focus Alert - File Analysis Report", title_style))
    story.append(Spacer(1, 20))
    
    # File info
    story.append(Paragraph("File Information", heading_style))
    
    # Akumulasi Unik Person dan Total Detections
    unique_persons = len(set(detection.get('id', 1) for detection in detections))
    total_detections = len(detections)
    
    file_info_data = [
        ['File Name', file_info.get('filename', 'Unknown')],
        ['File Type', file_info.get('type', 'Unknown')],
        ['Analysis Date', datetime.now().strftime('%m/%d/%Y, %I:%M:%S %p')],
        ['Unique Persons', str(unique_persons)],
        ['Total Detections', str(total_detections)]
    ]
    
    file_table = Table(file_info_data, colWidths=[2*inch, 4*inch])
    file_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F3F4F6')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(file_table)
    story.append(Spacer(1, 15))
    
    # Statistics
    story.append(Paragraph("Analysis Statistics", heading_style))
    
    status_counts = {'FOCUSED': 0, 'NOT FOCUSED': 0, 'YAWNING': 0, 'SLEEPING': 0}
    for detection in detections:
        status = detection.get('status', 'FOCUSED')
        if status in status_counts:
            status_counts[status] += 1
    
    focus_accuracy = 0
    if total_detections > 0:
        focus_accuracy = (status_counts['FOCUSED'] / total_detections) * 100
    
    analysis_stats = [
        ['Metric', 'Count', 'Percentage'],
        ['Focus Accuracy', f"{status_counts['FOCUSED']}/{total_detections}", f"{focus_accuracy:.1f}%"],
        ['Focused States', str(status_counts['FOCUSED']), f"{(status_counts['FOCUSED']/total_detections*100):.1f}%" if total_detections > 0 else "0%"],
        ['Unfocused States', str(status_counts['NOT FOCUSED']), f"{(status_counts['NOT FOCUSED']/total_detections*100):.1f}%" if total_detections > 0 else "0%"],
        ['Yawning States', str(status_counts['YAWNING']), f"{(status_counts['YAWNING']/total_detections*100):.1f}%" if total_detections > 0 else "0%"],
        ['Sleeping States', str(status_counts['SLEEPING']), f"{(status_counts['SLEEPING']/total_detections*100):.1f}%" if total_detections > 0 else "0%"]
    ]
    
    analysis_table = Table(analysis_stats, colWidths=[2*inch, 2*inch, 2*inch])
    analysis_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3B82F6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')])
    ]))
    
    story.append(analysis_table)
    story.append(Spacer(1, 15))
    
    # Menampilkan Semua Deteksi
    if detections:
        story.append(Paragraph("Detection Results", heading_style))
        
        detection_headers = ['Person ID', 'Status', 'Confidence', 'Position (X,Y)', 'Size (W,H)']
        detection_data = [detection_headers]
        
        for detection in detections:
            bbox = detection.get('bbox', [0, 0, 0, 0])
            person_id = detection.get('id', 1)
            
            detection_data.append([
                f"Person {person_id}",
                detection.get('status', 'Unknown'),
                f"{detection.get('confidence', 0)*100:.1f}%",
                f"({bbox[0]}, {bbox[1]})",
                f"({bbox[2]}, {bbox[3]})"
            ])
        
        # Batasi jumlah deteksi yang ditampilkan
        max_detections_to_show = 50
        if len(detection_data) > max_detections_to_show + 1:  # +1 for header
            detection_data = detection_data[:max_detections_to_show + 1]
            
            # Tambahkan note tentang jumlah deteksi yang ditampilkan
            story.append(Paragraph(f"<i>Note: Showing first {max_detections_to_show} detections out of {len(detections)} total detections</i>", styles['Normal']))
            story.append(Spacer(1, 10))
        
        detection_table = Table(detection_data, colWidths=[1*inch, 1*inch, 1*inch, 1.5*inch, 1.5*inch])
        detection_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3B82F6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')])
        ]))
        
        story.append(detection_table)
        story.append(Spacer(1, 20))
        
       
    # Footer
    story.append(Spacer(1, 30))
    footer_text = f"Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br/>Smart Focus Alert"
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#6B7280')
    )
    story.append(Paragraph(footer_text, footer_style))
    
    doc.build(story)
    logger.info(f"Upload analysis PDF generated: {output_path}")
    return output_path

# Flask Routes
@application.route('/')
def index():
    return render_template('index.html')

@application.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('upload.html', error='No file part')
        
        file = request.files['file']
        
        if file.filename == '':
            return render_template('upload.html', error='No selected file')
        
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(application.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
            
            result = {
                "filename": filename,
                "file_path": f"/static/uploads/{filename}",
                "detections": []
            }
            
            if file_ext in ['jpg', 'jpeg', 'png', 'bmp']:
                image = cv.imread(file_path)
                processed_image, detections = detect_persons_with_attention(image, mode="upload")
                
                output_filename = f"processed_{filename}"
                output_path = os.path.join(application.config['DETECTED_FOLDER'], output_filename)
                cv.imwrite(output_path, processed_image)
                
                result["processed_image"] = f"/static/detected/{output_filename}"
                result["detections"] = detections
                result["type"] = "image"
                
                pdf_filename = f"report_{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                pdf_path = os.path.join(application.config['REPORTS_FOLDER'], pdf_filename)
                
                file_info = {'filename': filename, 'type': file_ext.upper()}
                generate_upload_pdf_report(detections, file_info, pdf_path)
                result["pdf_report"] = f"/static/reports/{pdf_filename}"
                
            elif file_ext in ['mp4', 'avi', 'mov', 'mkv']:
                output_path, detections = process_video_file(file_path)
                
                result["processed_video"] = f"/static/detected/{os.path.basename(output_path)}"
                result["detections"] = detections
                result["type"] = "video"
                
                pdf_filename = f"report_{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                pdf_path = os.path.join(application.config['REPORTS_FOLDER'], pdf_filename)
                
                file_info = {'filename': filename, 'type': file_ext.upper()}
                generate_upload_pdf_report(detections, file_info, pdf_path)
                result["pdf_report"] = f"/static/reports/{pdf_filename}"
            
            return render_template('result.html', result=result)
    
    return render_template('upload.html')

@application.route('/live')
def live():
    return render_template('live.html')

@application.route('/start_monitoring', methods=['POST'])
def start_monitoring():
    """Memulai Sesi live monitoring"""
    global live_monitoring_active, session_data, recording_active
    global current_person_state, person_state_start_time, last_alert_times, session_start_time, no_person_state
    
    try:
        request_data = request.get_json() or {}
        client_session_id = request_data.get('sessionId')
        
        with monitoring_lock:
            if live_monitoring_active:
                return jsonify({"status": "error", "message": "Monitoring already active"})
            
            # Reset semua variable 
            session_data = {
                'start_time': datetime.now(),
                'end_time': None,
                'detections': [],
                'alerts': [],
                'focus_statistics': {
                    'total_focused_time': 0,
                    'total_unfocused_time': 0,
                    'total_yawning_time': 0,
                    'total_sleeping_time': 0,
                    'total_no_person_time': 0,
                    'total_persons': 0,
                    'total_detections': 0
                },
                'recording_path': None,
                'recording_frames': [],
                'session_id': client_session_id,
                'client_alerts': [],
                'frame_counter': 0,
                'frame_timestamps': [],
                'total_frames_processed': 0
            }
            
            current_person_state = None
            person_state_start_time = None
            last_alert_times = {}
            session_start_time = time.time()
            
            # Reset status NO PERSON 
            no_person_state = {
                'active': False,
                'start_time': None,
                'last_alert_time': 0,
                'total_duration': 0
            }
            
            live_monitoring_active = True
            recording_active = True
            
            logger.info(f"Monitoring session started: {session_data['start_time']} (ID: {client_session_id})")
            
            return jsonify({
                "status": "success", 
                "message": "Session started", 
                "session_id": client_session_id,
                "thresholds": DISTRACTION_THRESHOLDS,
                "alert_cooldown": ALERT_COOLDOWN
            })
        
    except Exception as e:
        logger.error(f"Start monitoring error: {str(e)}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Failed to start monitoring: {str(e)}"})

@application.route('/stop_monitoring', methods=['POST'])
def stop_monitoring():
    """Stop monitoring session"""
    global live_monitoring_active, session_data, recording_active
    global current_person_state, person_state_start_time, no_person_state
    
    try:
        request_data = request.get_json() or {}
        client_alerts = request_data.get('alerts', [])
        client_session_id = request_data.get('sessionId')
        
        with monitoring_lock:
            if not live_monitoring_active and (not session_data or not session_data.get('start_time')):
                return jsonify({"status": "error", "message": "Monitoring not active"})
            
            # Finalisasi Sesi yang akan datang
            current_time = time.time()
            if current_person_state and current_person_state in DISTRACTION_THRESHOLDS and person_state_start_time:
                session_duration = current_time - person_state_start_time
                logger.debug(f"Finalized {current_person_state} session: {session_duration:.2f}s")
            
            # Finalisasi status NO PERSON jika aktif
            if no_person_state['active'] and no_person_state['start_time']:
                no_person_duration = current_time - no_person_state['start_time']
                no_person_state['total_duration'] += no_person_duration
                session_data['focus_statistics']['total_no_person_time'] += no_person_duration
                logger.debug(f"Finalized NO PERSON session: {no_person_duration:.2f}s")
            
            if client_alerts:
                session_data['client_alerts'] = client_alerts
                logger.info(f"Merged {len(client_alerts)} client alerts")
            
            live_monitoring_active = False
            recording_active = False
            session_data['end_time'] = datetime.now()
            
            logger.info(f"Monitoring session stopped: {session_data['end_time']} (ID: {client_session_id})")
            
            response_data = {
                "status": "success", 
                "message": "Session stopped",
                "alerts_processed": len(session_data['alerts']),
                "frames_captured": len(session_data.get('recording_frames', [])),
            }
            
            # Generate PDF
            try:
                pdf_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.pdf"
                pdf_path = os.path.join(application.config['REPORTS_FOLDER'], pdf_filename)
                
                pdf_result = generate_live_pdf_report(session_data, pdf_path)
                
                if pdf_result and os.path.exists(pdf_path):
                    response_data["pdf_report"] = f"/static/reports/{pdf_filename}"
                    logger.info(f"PDF report generated: {pdf_filename}")
                else:
                    logger.warning("PDF generation failed")
                    
            except Exception as pdf_error:
                logger.error(f"PDF generation error: {str(pdf_error)}")
                traceback.print_exc()
            
            # Generate video
            try:
                recording_filename = f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.mp4"
                recording_path = os.path.join(application.config['RECORDINGS_FOLDER'], recording_filename)
                
                if len(session_data.get('recording_frames', [])) > 0:
                    video_result = create_session_recording_from_frames(
                        session_data['recording_frames'],
                        recording_path,
                        session_data.get('start_time', datetime.now() - timedelta(seconds=10)),
                        session_data.get('end_time', datetime.now())
                    )
                    
                    if video_result and os.path.exists(recording_path):
                        response_data["video_file"] = f"/static/recordings/{os.path.basename(recording_path)}"
                        session_data['recording_path'] = recording_path
                        logger.info(f"Video recording generated: {os.path.basename(recording_path)}")
                    else:
                        logger.warning("Video generation failed")
                else:
                    logger.warning("No frames available for video generation")
                    
            except Exception as video_error:
                logger.error(f"Video generation error: {str(video_error)}")
                traceback.print_exc()
            
            return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Stop monitoring error: {str(e)}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Failed to stop monitoring: {str(e)}"})

@application.route('/process_frame', methods=['POST'])
def process_frame():
    """Process frame"""
    global session_data
    
    try:
        data = request.get_json()
        if not data or 'frame' not in data:
            return jsonify({"error": "No frame data"}), 400
            
        frame_data = data['frame'].split(',')[1]
        frame_bytes = base64.b64decode(frame_data)
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv.imdecode(nparr, cv.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({"error": "Invalid frame"}), 400
        
        processed_frame, detections = detect_persons_with_attention(frame, mode="video")
        
        # Store frame
        with monitoring_lock:
            if live_monitoring_active and recording_active and session_data:
                session_data['frame_counter'] = session_data.get('frame_counter', 0) + 1
                session_data['total_frames_processed'] = session_data.get('total_frames_processed', 0) + 1
                current_timestamp = time.time()
                
                should_store_frame = (
                    session_data['frame_counter'] % FRAME_STORAGE_INTERVAL == 0 or
                    len(detections) > 0 or
                    len(session_data.get('recording_frames', [])) < 10
                )
                
                if should_store_frame:
                    frame_copy = processed_frame.copy()
                    session_data['recording_frames'].append(frame_copy)
                    session_data['frame_timestamps'].append(current_timestamp)
                    
                    if len(session_data['recording_frames']) > MAX_STORED_FRAMES:
                        frames_to_remove = len(session_data['recording_frames']) - MAX_STORED_FRAMES
                        session_data['recording_frames'] = session_data['recording_frames'][frames_to_remove:]
                        session_data['frame_timestamps'] = session_data['frame_timestamps'][frames_to_remove:]
        
        if live_monitoring_active and detections:
            update_session_statistics(detections)
        
        # Encode frame
        _, buffer = cv.imencode('.jpg', processed_frame, [cv.IMWRITE_JPEG_QUALITY, 85])
        processed_frame_b64 = base64.b64encode(buffer).decode('utf-8')
        
        return jsonify({
            "success": True,
            "processed_frame": f"data:image/jpeg;base64,{processed_frame_b64}",
            "detections": detections,
            "frame_count": len(session_data.get('recording_frames', [])) if session_data else 0,
            "total_processed": session_data.get('total_frames_processed', 0) if session_data else 0,
            "frame_number": session_data.get('frame_counter', 0) if session_data else 0
        })
        
    except Exception as e:
        logger.error(f"Frame processing error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": f"Frame processing failed: {str(e)}"}), 500

@application.route('/sync_alerts', methods=['POST'])
def sync_alerts():
    """Sync client alerts with server"""
    try:
        request_data = request.get_json() or {}
        client_alerts = request_data.get('alerts', [])
        session_id = request_data.get('sessionId')
        
        with monitoring_lock:
            if session_data and session_data.get('session_id') == session_id:
                session_data['client_alerts'] = client_alerts
                logger.info(f"Synced {len(client_alerts)} client alerts session {session_id}")
                return jsonify({"status": "success", "synced_count": len(client_alerts)})
            else:
                return jsonify({"status": "error", "message": "Session mismatch"})
                
    except Exception as e:
        logger.error(f"Alert sync error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

@application.route('/get_monitoring_data')
def get_monitoring_data():
    """Get monitoring data"""
    global session_data
    
    try:
        with monitoring_lock:
            if not live_monitoring_active:
                return jsonify({"error": "Monitoring not active"})
            
            current_alerts = session_data.get('alerts', []) if session_data else []
            recent_alerts = current_alerts[-5:] if current_alerts else []
            
            formatted_alerts = []
            for alert in recent_alerts:
                try:
                    alert_time = datetime.fromisoformat(alert['timestamp']).strftime('%H:%M:%S')
                except:
                    alert_time = alert.get('alert_time', 'N/A')
                
                duration = alert.get('real_time_duration', alert.get('duration', 0))
                is_reminder = alert.get('is_reminder', False)
                duration_text = f" ({duration:.1f}s)" if duration > 0 else ""
                
                formatted_alerts.append({
                    'time': alert_time,
                    'message': alert['message'] + duration_text,
                    'type': 'warning' if alert['detection'] in ['YAWNING', 'NOT FOCUSED'] else 'error',
                    'duration': duration,
                    'is_reminder': is_reminder
                })
            
            current_detections = session_data.get('detections', []) if session_data else []
            recent_detections = current_detections[-10:] if current_detections else []
            current_status = 'READY'
            focused_count = 0
            total_persons = 0
            
            if recent_detections:
                latest_detection = recent_detections[-1]
                current_status = latest_detection['status']
                total_persons = 1
                focused_count = 1 if current_status == 'FOCUSED' else 0
            elif no_person_state.get('active', False):
                current_status = 'NO PERSON'
            
            return jsonify({
                'total_persons': total_persons,
                'focused_count': focused_count,
                'alert_count': len(current_alerts),
                'current_status': current_status,
                'latest_alerts': formatted_alerts,
                'frame_count': len(session_data.get('recording_frames', [])) if session_data else 0,
                'total_processed': session_data.get('total_frames_processed', 0) if session_data else 0
            })
        
    except Exception as e:
        logger.error(f"Get monitoring data error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": f"Failed to get monitoring data: {str(e)}"})

@application.route('/monitoring_status')
def monitoring_status():
    """Get monitoring status"""
    try:
        with monitoring_lock:
            return jsonify({
                "is_active": live_monitoring_active,
                "session_id": session_data.get('session_id') if session_data else None,
                "alerts_count": len(session_data.get('alerts', [])) if session_data else 0,
                "frames_stored": len(session_data.get('recording_frames', [])) if session_data else 0,
                "frames_processed": session_data.get('total_frames_processed', 0) if session_data else 0,
                "no_person_active": no_person_state.get('active', False),
                "alert_cooldown": ALERT_COOLDOWN,
                "thresholds": DISTRACTION_THRESHOLDS,
            })
    except Exception as e:
        logger.error(f"Monitoring status error: {str(e)}")
        return jsonify({"is_active": False})

@application.route('/check_camera')
def check_camera():
    """Check camera availability"""
    try:
        return jsonify({"camera_available": False})
    except Exception as e:
        logger.error(f"Camera check error: {str(e)}")
        return jsonify({"camera_available": False})

@application.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        with monitoring_lock:
            return jsonify({
                "status": "healthy", 
                "timestamp": datetime.now().isoformat(),
                "directories": {
                    "uploads": os.path.exists(application.config['UPLOAD_FOLDER']),
                    "detected": os.path.exists(application.config['DETECTED_FOLDER']),
                    "reports": os.path.exists(application.config['REPORTS_FOLDER']),
                    "recordings": os.path.exists(application.config['RECORDINGS_FOLDER'])
                },
                "monitoring_active": live_monitoring_active,
                "session_alerts": len(session_data.get('alerts', [])) if session_data else 0,
                "recording_frames": len(session_data.get('recording_frames', [])) if session_data else 0,
                "total_frames_processed": session_data.get('total_frames_processed', 0) if session_data else 0,
                "frame_storage_ratio": len(session_data.get('recording_frames', [])) / max(1, session_data.get('total_frames_processed', 1)) * 100 if session_data else 0,
                "mediapipe_status": "initialized" if face_detection and face_mesh else "error",
                "no_person_state": no_person_state,
                "alert_cooldown": ALERT_COOLDOWN,
                "thresholds": DISTRACTION_THRESHOLDS,
                "audio_system": {
                    "enabled": True,
                    "speech_synthesis": True,
                    "beep_alerts": True,
                    "status": "ready"
                }
            })
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@application.route('/api/detect', methods=['POST'])
def api_detect():
    """API endpoint"""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    filename = secure_filename(file.filename)
    file_path = os.path.join(application.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)
    
    file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    if file_ext in ['jpg', 'jpeg', 'png', 'bmp']:
        image = cv.imread(file_path)
        processed_image, detections = detect_persons_with_attention(image, mode="upload")
        
        output_filename = f"processed_{filename}"
        output_path = os.path.join(application.config['DETECTED_FOLDER'], output_filename)
        cv.imwrite(output_path, processed_image)
        
        return jsonify({
            "type": "image",
            "processed_image": f"/static/detected/{output_filename}",
            "detections": detections
        })
        
    elif file_ext in ['mp4', 'avi', 'mov', 'mkv']:
        output_path, detections = process_video_file(file_path)
        
        return jsonify({
            "type": "video",
            "processed_video": f"/static/detected/{os.path.basename(output_path)}",
            "detections": detections
        })
    
    return jsonify({"error": "Unsupported file format"}), 400

# Static file
@application.route('/static/reports/<filename>')
def report_file(filename):
    """Serve PDF files"""
    try:
        file_path = os.path.join(application.config['REPORTS_FOLDER'], filename)
        if os.path.exists(file_path):
            return send_from_directory(
                application.config['REPORTS_FOLDER'], 
                filename,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=filename
            )
        else:
            logger.warning(f"Report file not found: {filename}")
            return jsonify({"error": "Report not found"}), 404
    except Exception as e:
        logger.error(f"Report serve error: {str(e)}")
        return jsonify({"error": "Error accessing report"}), 500

@application.route('/static/recordings/<filename>')
def recording_file(filename):
    """Serve video files"""
    try:
        file_path = os.path.join(application.config['RECORDINGS_FOLDER'], filename)
        if os.path.exists(file_path):
            return send_from_directory(
                application.config['RECORDINGS_FOLDER'], 
                filename,
                mimetype='video/mp4',
                as_attachment=True,
                download_name=filename
            )
        else:
            logger.warning(f"Recording file not found: {filename}")
            return jsonify({"error": "Recording not found"}), 404
    except Exception as e:
        logger.error(f"Recording serve error: {str(e)}")
        return jsonify({"error": "Error accessing recording"}), 500

@application.route('/static/detected/<filename>')
def detected_file(filename):
    """Serve detected files"""
    try:
        return send_from_directory(application.config['DETECTED_FOLDER'], filename)
    except Exception as e:
        logger.error(f"Detected file error: {str(e)}")
        return jsonify({"error": "Error accessing file"}), 500

@application.route('/static/uploads/<filename>')
def upload_file(filename):
    """Serve uploaded files"""
    try:
        return send_from_directory(application.config['UPLOAD_FOLDER'], filename)
    except Exception as e:
        logger.error(f"Upload file error: {str(e)}")
        return jsonify({"error": "Error accessing file"}), 500

if __name__ == "__main__":
    try:
        if not init_mediapipe():
            logger.warning("MediaPipe initialization failed - some features may not work")
        
        port = int(os.environ.get('PORT', 5000))
        logger.info(f"Starting Smart Focus Alert on port {port}")
        logger.info(f"Alert cooldown: {ALERT_COOLDOWN} seconds")
        logger.info(f"Thresholds: {DISTRACTION_THRESHOLDS}")
        logger.info(f"Frame storage: every {FRAME_STORAGE_INTERVAL} frames, max {MAX_STORED_FRAMES}")
        logger.info(f"Recording FPS: {RECORDING_FPS}")
        
        for name, path in [
            ("UPLOAD", application.config['UPLOAD_FOLDER']),
            ("DETECTED", application.config['DETECTED_FOLDER']),
            ("REPORTS", application.config['REPORTS_FOLDER']),
            ("RECORDINGS", application.config['RECORDINGS_FOLDER'])
        ]:
            logger.info(f"{name}: {path} (exists: {os.path.exists(path)})")
        
        application.run(host='0.0.0.0', port=port, debug=False)
    except Exception as e:
        logger.error(f"Application startup error: {str(e)}")
        traceback.print_exc()
