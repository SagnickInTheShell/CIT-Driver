"""
main.py - SafeDrive AI
Stable Release: Prioritizes Zero Crashes, Hardware Serial, and ESP32-CAM Stream.
"""
import cv2
import time
import random
import traceback

# Core Vision and Health
from vision import FaceMeshDetector, LEFT_EYE_INDICES, RIGHT_EYE_INDICES
from drowsiness import DrowsinessDetector
from health_monitor import HealthMonitor

# New Hackathon Features
from attention import AttentionDetector
from yawn import YawnDetector
from fatigue import FatigueScoring
from voice_alert import VoiceAlertSystem
from event_logger import EventLogger
from accident import AccidentDetector
from report_generator import ReportGenerator

# --- CONFIGURATION ---
ESP32_CAM_IP = "192.168.1.100"  # Change this to your ESP32-CAM IP
USE_IP_CAMERA = True            # Set to False to force webcam fallback

def get_camera_stream():
    """Attempt to connect to ESP32-CAM stream, fallback to webcam."""
    if USE_IP_CAMERA:
        stream_url = f"http://{ESP32_CAM_IP}:81/stream"
        print(f"Connecting to ESP32-CAM stream at {stream_url}...")
        cap = cv2.VideoCapture(stream_url)
        if cap.isOpened():
            print("Successfully connected to ESP32-CAM.")
            return cap
        else:
            print(f"Failed to connect to IP camera at {stream_url}. Falling back to webcam (0).")
    
    print("Connecting to default webcam (0)...")
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return cap

def main():
    print("SafeDrive AI: Initialising with Stable Features...")
    cap = get_camera_stream()

    # Instantiate modules safely
    try:
        detector        = FaceMeshDetector()
        drowsiness_chk  = DrowsinessDetector(ear_threshold=0.22, consecutive_frames=15)
        health_monitor  = HealthMonitor()
        attention_chk   = AttentionDetector(fps=30, distracted_time_threshold=3.0)
        yawn_chk        = YawnDetector(mar_threshold=0.6, fps=30, yawn_time_threshold=1.0)
        fatigue_sys     = FatigueScoring()
        voice           = VoiceAlertSystem()
    except Exception as e:
        print(f"CRITICAL: Error initializing modules: {e}")
        return

    prev_time = time.time()
    print("System Active – press 'q' to quit.")

    while True:
        try:
            if cap is None or not cap.isOpened():
                print("Camera stream lost. Attempting to reconnect in 2 seconds...")
                if cap:
                    cap.release()
                time.sleep(2)
                cap = get_camera_stream()
                if not cap.isOpened():
                    continue

            ok, frame = cap.read()
            if not ok or frame is None:
                print("Empty frame received. Retrying...")
                time.sleep(0.1)
                continue

            frame = cv2.flip(frame, 1)
            h, w  = frame.shape[:2]

            # ── 1. Update Health Sensors ────────────────────────────────
            try:
                hdata = health_monitor.update_sensors()
            except Exception as e:
                print(f"Error updating sensors: {e}")
                hdata = {"heart_rate": 0, "spo2": 0, "ecg_status": "Error", "emergency": False, "mode": "error", "lat": 0, "lng": 0}

            # ── 2. Vision Processing ────────────────────────────────────
            face_detected = False
            is_drowsy      = False
            avg_ear        = 0.0
            is_yawning     = False
            mar            = 0.0
            head_direction = "FORWARD"
            is_distracted  = False
            f_score = 0
            f_level = "AWAKE"

            try:
                landmarks = detector.find_face_landmarks(frame)
                face_detected = landmarks is not None
                
                if face_detected:
                    # Drowsiness (EAR)
                    left_pts  = detector.get_eye_coords(landmarks, LEFT_EYE_INDICES, w, h)
                    right_pts = detector.get_eye_coords(landmarks, RIGHT_EYE_INDICES, w, h)
                    
                    if len(left_pts) > 0 and len(right_pts) > 0:
                        left_ear  = drowsiness_chk.calculate_ear(left_pts)
                        right_ear = drowsiness_chk.calculate_ear(right_pts)
                        is_drowsy, avg_ear = drowsiness_chk.check_drowsiness(left_ear, right_ear)
                    
                    # Yawning (MAR)
                    mar = yawn_chk.calculate_mar(landmarks, w, h)
                    is_yawning, yawn_count = yawn_chk.check_yawn(mar)
                    
                    # Head Pose Attention
                    head_direction = attention_chk.get_head_pose(landmarks, w, h)
                    is_distracted = attention_chk.check_attention(head_direction)
                    
                    # Draw facial dots for feedback
                    for (x, y) in left_pts: cv2.circle(frame, (x, y), 2, (0, 255, 0), -1)
                    for (x, y) in right_pts: cv2.circle(frame, (x, y), 2, (0, 255, 0), -1)
            except Exception as e:
                pass # Fail silently on vision errors to avoid log spam/crashes

            # ── 3. Fatigue Scoring & Alerts ──────────────────────────────
            try:
                f_score, f_level = fatigue_sys.update_score(is_drowsy, is_yawning, is_distracted)
                
                # We omit excessive voice/logging to keep the UI stable and demo-safe
                if f_level == "CRITICAL FATIGUE" and int(time.time()) % 15 == 0:
                    voice.play_alert("drowsy") 
            except Exception as e:
                pass

            # ── 4. UI Rendering ────────────────────────────────────────
            try:
                F = cv2.FONT_HERSHEY_DUPLEX
                WHITE, RED, GREEN, YELLOW = (255,255,255), (0,0,255), (0,220,0), (0,255,255)
                ORANGE, GREY = (0,165,255), (150,150,150)
                
                # Background panels (Clean UI)
                overlay = frame.copy()
                cv2.rectangle(overlay, (10, 10), (350, 280), (0, 0, 0), -1)
                cv2.rectangle(overlay, (w-350, 10), (w-10, 280), (0, 0, 0), -1)
                frame = cv2.addWeighted(overlay, 0.6, frame, 0.4, 0)
                
                # --- LEFT PANEL: Driver State ---
                cv2.putText(frame, "DRIVER STATE", (20, 40), F, 0.7, ORANGE, 2)
                cv2.line(frame, (20, 50), (330, 50), WHITE, 1)
                
                cv2.putText(frame, f"Face: {'Detected' if face_detected else 'Missing'}", (20, 80), F, 0.6, GREEN if face_detected else RED, 1)
                cv2.putText(frame, f"Pose: {head_direction}", (20, 110), F, 0.6, YELLOW if is_distracted else WHITE, 1)
                cv2.putText(frame, f"EAR : {avg_ear:.3f} | MAR: {mar:.2f}", (20, 140), F, 0.6, WHITE, 1)
                
                # Fatigue Bar
                cv2.putText(frame, "FATIGUE SCORE:", (20, 180), F, 0.6, WHITE, 1)
                bar_w = 250
                cv2.rectangle(frame, (20, 195), (20 + bar_w, 215), GREY, 1)
                fill_w = int((f_score / 100.0) * bar_w)
                score_color = GREEN if f_score < 30 else (YELLOW if f_score < 70 else RED)
                if fill_w > 0:
                    cv2.rectangle(frame, (21, 196), (20 + fill_w - 1, 214), score_color, -1)
                cv2.putText(frame, f"{f_score}/100", (20 + bar_w + 10, 210), F, 0.6, score_color, 1)
                cv2.putText(frame, f"Level: {f_level}", (20, 250), F, 0.65, score_color, 2)

                # --- RIGHT PANEL: Health & Safety ---
                cv2.putText(frame, "HEALTH VITALS", (w-330, 40), F, 0.7, ORANGE, 2)
                cv2.line(frame, (w-330, 50), (w-20, 50), WHITE, 1)
                
                hr_col = RED if hdata.get('emergency', False) and (hdata.get('heart_rate', 0)>120 or hdata.get('heart_rate', 0)<50) else WHITE
                sp_col = RED if hdata.get('emergency', False) and hdata.get('spo2', 100)<90 else WHITE
                
                cv2.putText(frame, f"Heart Rate:  {hdata.get('heart_rate', '--')} bpm", (w-330, 80), F, 0.6, hr_col, 1)
                cv2.putText(frame, f"SpO2 Level:  {hdata.get('spo2', '--')} %", (w-330, 110), F, 0.6, sp_col, 1)
                cv2.putText(frame, f"Mode: {hdata.get('mode', 'simulation').upper()}", (w-330, 140), F, 0.6, YELLOW, 1)
                
                # Overall Status
                cv2.putText(frame, "SYSTEM STATUS:", (w-330, 190), F, 0.6, ORANGE, 1)
                if hdata.get('emergency', False):
                    sys_stat, sys_col = "MEDICAL EMERGENCY", RED
                elif f_level == "CRITICAL FATIGUE" or is_drowsy:
                    sys_stat, sys_col = "DRIVER DROWSY", RED
                elif is_distracted:
                    sys_stat, sys_col = "DRIVER DISTRACTED", YELLOW
                else:
                    sys_stat, sys_col = "SAFE", GREEN
                    
                cv2.putText(frame, sys_stat, (w-330, 230), F, 0.7, sys_col, 2)

                # --- BIG ALERTS ---
                center_x = w // 2
                center_y = h - 80
                if sys_col == RED:
                    # Flashing effect
                    if int(time.time() * 4) % 2 == 0:
                        cv2.rectangle(frame, (center_x-250, center_y-40), (center_x+250, center_y+20), RED, -1)
                        cv2.putText(frame, f"WARNING: {sys_stat}", (center_x-200, center_y), F, 0.8, WHITE, 2)

                # --- Status Bar ---
                cv2.rectangle(frame, (0, h-30), (w, h), (20, 20, 20), -1)
                curr_time = time.time()
                fps = 1.0 / max(curr_time - prev_time, 1e-6)
                prev_time = curr_time
                cv2.putText(frame, "SafeDrive AI | Stable Release", (10, h-10), F, 0.45, GREY, 1)
                cv2.putText(frame, f"FPS: {fps:.1f}", (w-120, h-10), F, 0.45, GREY, 1)

                cv2.imshow("SafeDrive AI - Stable Dashboard", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            except Exception as e:
                print(f"UI Error: {e}")
        except Exception as e:
            print(f"Unexpected Main Loop Error: {e}")
            time.sleep(1) # Prevent CPU spinning on crash loop

    if cap:
        cap.release()
    cv2.destroyAllWindows()
    print("SafeDrive AI Shutdown.")

if __name__ == "__main__":
    main()
