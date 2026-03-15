import cv2
import time
import math
import numpy as np
import threading
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

import config

LEFT_EYE  = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33,  160, 158, 133, 153, 144]

class VisionMonitor:
    def __init__(self):
        self.status = "NO_FACE"
        self.running = False
        self.thread = None
        self.eyes_closed_start_time = None
        self.current_frame = None
        
        # Load FaceLandmarker (mp.tasks API)
        try:
            base_options = python.BaseOptions(model_asset_path='face_landmarker.task')
            options = vision.FaceLandmarkerOptions(
                base_options=base_options,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=True,
                num_faces=1
            )
            self.detector = vision.FaceLandmarker.create_from_options(options)
        except Exception as e:
            print(f"Failed to load FaceLandmarker. Is 'face_landmarker.task' in the same folder? Error: {e}")
            self.detector = None

    def get_status(self):
        return self.status

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join()

    def _calculate_ear(self, landmarks, eye_indices):
        p = [landmarks[i] for i in eye_indices]
        
        def dist(p1, p2):
            return math.hypot(p1.x - p2.x, p1.y - p2.y)
        
        # EAR formula: (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
        v1 = dist(p[1], p[5])
        v2 = dist(p[2], p[4])
        h = dist(p[0], p[3])
        
        if h == 0:
            return 0.0
        return (v1 + v2) / (2.0 * h)
        
    def _calculate_head_angle(self, transformation_matrix):
        # Extract pitch (tilting up/down) from the transformation matrix
        rmat = transformation_matrix[:3, :3]
        sy = math.sqrt(rmat[0,0] * rmat[0,0] + rmat[1,0] * rmat[1,0])
        singular = sy < 1e-6

        if not singular:
            x = math.atan2(rmat[2,1] , rmat[2,2])
            y = math.atan2(-rmat[2,0], sy)
            z = math.atan2(rmat[1,0], rmat[0,0])
        else:
            x = math.atan2(-rmat[1,2], rmat[1,1])
            y = math.atan2(-rmat[2,0], sy)
            z = 0
            
        pitch_deg = math.degrees(x)
        # Using simplified pitch magnitude as droop angle
        return abs(pitch_deg)

    def _open_camera(self):
        cam = None
        if config.USE_ESP32_CAM:
            try:
                cam = cv2.VideoCapture(config.ESP32_CAM_URL)
                if not cam.isOpened():
                    raise Exception("ESP32 stream failed to open.")
            except Exception as e:
                print(f"Failed to open ESP32_CAM stream: {e}. Falling back to webcam.")
                cam = None

        if cam is None or not cam.isOpened():
            cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        
        if cam.isOpened():
            # Warm up loop (30 frames) for cameras that need time to adjust exposure (e.g., Lenovo webcams)
            for _ in range(30):
                cam.read()
                
        return cam

    def _run(self):
        if not self.detector:
            return

        cap = self._open_camera()
        
        while self.running:
            if cap is None or not cap.isOpened():
                self.status = "NO_FACE"
                time.sleep(1)
                cap = self._open_camera() # Attempt reconnect continuously
                continue
                
            try:
                ret, frame = cap.read()
                if not ret:
                    self.status = "NO_FACE"
                    time.sleep(1)
                    cap.release()
                    cap = self._open_camera()
                    continue
                    
                self.current_frame = frame.copy()
                
                # Convert BGR to RGB for Mediapipe
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                
                # Process the frame with mp.tasks API
                result = self.detector.detect(mp_image)
                
                if not result.face_landmarks:
                    self.status = "NO_FACE"
                    self.eyes_closed_start_time = None
                    continue
                    
                landmarks = result.face_landmarks[0]
                transform_matrix = result.facial_transformation_matrixes[0]
                
                # Calculate metrics
                left_ear = self._calculate_ear(landmarks, LEFT_EYE)
                right_ear = self._calculate_ear(landmarks, RIGHT_EYE)
                avg_ear = (left_ear + right_ear) / 2.0
                head_angle = self._calculate_head_angle(transform_matrix)
                
                # Classify based on conditions
                if head_angle > config.HEAD_ANGLE_THRESHOLD:
                    self.status = "HEAD_DROOPING"
                    self.eyes_closed_start_time = None
                elif avg_ear < config.EAR_THRESHOLD:
                    if self.eyes_closed_start_time is None:
                        self.eyes_closed_start_time = time.time()
                    
                    closed_duration = time.time() - self.eyes_closed_start_time
                    if closed_duration >= config.DROWSY_SECONDS:
                        self.status = "EYES_CLOSED"
                    else:
                        self.status = "EYES_CLOSING"
                else:
                    self.status = "ALERT"
                    self.eyes_closed_start_time = None
                    
            except Exception as e:
                # Log error and continue to prevent thread crash
                with open("error_log.txt", "a") as f:
                    f.write(f"VISION ERROR: {str(e)}\n")
                self.status = "NO_FACE"
                
            # Run at stable speed, don't monopolise CPU (~20 FPS)
            time.sleep(0.05)
            
        if cap:
            cap.release()
