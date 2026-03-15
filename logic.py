import time
import config

class LogicController:
    def __init__(self):
        self.eyes_closed_since = None
        self.last_cardiac_emergency_time = 0
        self.last_lat = None
        self.last_lng = None

    def classify(self, vision_status, sensors_data):
        hr = sensors_data.get("hr", 75)
        spo2 = sensors_data.get("spo2", 98)
        ecg = sensors_data.get("ecg", 0.0)
        lat = sensors_data.get("lat", 0.0)
        lng = sensors_data.get("lng", 0.0)
        
        current_time = time.time()
        
        # Track eyes closed duration for DRIVER_ASLEEP
        if vision_status == "EYES_CLOSED":
            if self.eyes_closed_since is None:
                self.eyes_closed_since = current_time
        else:
            self.eyes_closed_since = None
            
        eyes_closed_duration = 0
        if self.eyes_closed_since is not None:
            eyes_closed_duration = current_time - self.eyes_closed_since

        # Default normal return
        result = {
            "state": "NORMAL",
            "confidence": 1.0,
            "vision_input": vision_status,
            "hr": hr,
            "spo2": spo2,
            "ecg": ecg,
            "lat": lat,
            "lng": lng,
            "action_needed": "NONE",
            "cancel_countdown": None
        }

        # Check conditions (Highest priority first)
        
        # CASE 8 - MEDICAL_SHOCK
        # Condition: SpO2 below 85% + HR crashing below 40
        if spo2 < config.SPO2_CRITICAL and hr < config.HR_MIN:
            result["state"] = "MEDICAL_SHOCK"
            result["action_needed"] = "CRITICAL_SMS"
            result["confidence"] = 0.95
            return result

        # Detect clear GPS spike for ACCIDENT
        gps_spike = False
        if self.last_lat is not None and self.last_lng is not None:
            # Simple euclidean distance to detect sudden leap (simulated accident)
            dist = ((lat - self.last_lat)**2 + (lng - self.last_lng)**2)**0.5
            if dist > 0.005: # Arbitrary threshold for sudden jump
                gps_spike = True
                
        self.last_lat = lat
        self.last_lng = lng

        # CASE 5 & 7 PRE-REQUISITES
        is_cardiac = False
        # Simplified ECG irregularity calculation using simple threshold
        if abs(ecg) > config.ECG_IRREGULARITY_THRESHOLD and spo2 < config.SPO2_MIN and (hr > config.HR_MAX or hr < config.HR_MIN):
            is_cardiac = True

        if is_cardiac:
            self.last_cardiac_emergency_time = current_time

        # CASE 6 - ACCIDENT
        # sudden GPS coordinate spike + vitals spiking + driver unresponsive (NO_FACE/EYES_CLOSED)
        if gps_spike and (hr > 120 or hr < 50) and vision_status in ["NO_FACE", "EYES_CLOSED"]:
            # CASE 7 - CARDIAC_CAUSED_CRASH
            # Checked within 30 seconds
            if (current_time - self.last_cardiac_emergency_time) < 30:
                result["state"] = "CARDIAC_CAUSED_CRASH"
                result["action_needed"] = "COMBINED_HOSPITAL_SMS"
                result["confidence"] = 0.99
            else:
                result["state"] = "ACCIDENT"
                result["action_needed"] = "HOSPITAL_SMS"
                result["confidence"] = 0.98
            return result

        # CASE 5 - CARDIAC_EMERGENCY
        if is_cardiac:
            result["state"] = "CARDIAC_EMERGENCY"
            result["action_needed"] = "HOSPITAL_SMS"
            result["confidence"] = 0.92
            return result

        # Non-critical vitals conditions (Vision based)
        
        # CASE 4 - DRIVER_ASLEEP
        if eyes_closed_duration >= 10:
            result["state"] = "DRIVER_ASLEEP"
            result["action_needed"] = "MAX_BUZZER + CALL_DRIVER"
            result["confidence"] = 0.99
            return result
            
        # CASE 3 - EYES_CLOSED
        if vision_status == "EYES_CLOSED":
            result["state"] = "EYES_CLOSED"
            result["action_needed"] = "LOUD_BUZZER"
            result["cancel_countdown"] = config.CANCEL_WINDOW_SECONDS
            result["confidence"] = 0.85
            return result
            
        # CASE 2 - EYES_CLOSING
        if vision_status == "EYES_CLOSING":
            result["state"] = "EYES_CLOSING"
            result["action_needed"] = "MEDIUM_BUZZER"
            result["confidence"] = 0.80
            return result
            
        # CASE 1 - HEAD_DROOPING
        if vision_status == "HEAD_DROOPING":
            result["state"] = "HEAD_DROOPING"
            result["action_needed"] = "SOFT_BUZZER"
            result["confidence"] = 0.75
            return result

        return result
