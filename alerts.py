import time
import requests
import datetime
from twilio.rest import Client

import config

class AlertSystem:
    def __init__(self, serial_interface=None):
        self.serial = serial_interface
        
        if config.TWILIO_SID != "your_sid" and config.TWILIO_TOKEN != "your_token":
            try:
                self.twilio = Client(config.TWILIO_SID, config.TWILIO_TOKEN)
            except Exception as e:
                self._log(f"Twilio Initialization Error: {e}")
                self.twilio = None
        else:
            self.twilio = None
            
        self.last_sms_time = 0
        self.cancel_countdown_start = 0
        self.cancel_active = False
        self.cancel_remaining = 0
        
    def _log(self, message):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        print(log_line.strip())
        try:
             with open("alerts_log.txt", "a") as f:
                 f.write(log_line)
        except Exception:
             pass

    def _send_command_to_esp32(self, cmd):
        if self.serial and hasattr(self.serial, 'write'):
            try:
                self.serial.write(f"{cmd}\n".encode('utf-8'))
            except Exception as e:
                self._log(f"Failed to send to ESP32: {e}")
        # Log regardless for simulation
        self._log(f"COMMAND to ESP32: {cmd}")

    def _get_nearest_hospital(self, lat, lng):
        try:
            # OpenStreetMap Nominatim API (Free, no API key needed)
            url = f"https://nominatim.openstreetmap.org/search.php?q=hospital&format=jsonv2&lat={lat}&lon={lng}&radius=5000"
            headers = {
                'User-Agent': 'VitalDriveApp/1.0 (Student Hackathon Project)'
            }
            # 5 second timeout to prevent blocking the thread
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    name = data[0].get('display_name', 'Unknown Hospital').split(',')[0]
                    
                    # Approximate distance calculation in km
                    h_lat = float(data[0]['lat'])
                    h_lon = float(data[0]['lon'])
                    # Simple euclidian approx (1 degree is approx 111km)
                    dist = ((lat - h_lat)**2 + (lng - h_lon)**2)**0.5 * 111
                    return name, round(dist, 1)
        except Exception as e:
            self._log(f"OSM Routing Error: {e}")
            
        return "Nearest Hospital", 0.0

    def _send_sms(self, to_number, body):
        self._log(f"Sending SMS to {to_number}:\n{body}")
        if self.twilio:
            try:
                message = self.twilio.messages.create(
                    body=body,
                    from_=config.TWILIO_FROM,
                    to=to_number
                )
                self._log(f"SMS Successfully Sent! SID: {message.sid}")
            except Exception as e:
                self._log(f"Twilio API Request Error: {e}")
        else:
            self._log("(SIMULATED SMS - Twilio not configured)")

    def handle(self, classification_result, button_pressed=False):
        state = classification_result.get("state", "NORMAL")
        action = classification_result.get("action_needed", "NONE")
        
        # Handle 10-second Cancellation Window Logic
        if button_pressed and self.cancel_active:
            self._log("ALERT CANCELLED BY DRIVER (Button Pressed)")
            self._send_command_to_esp32("RESET")
            self.cancel_active = False
            self.cancel_remaining = 0
            return
            
        if self.cancel_active:
            elapsed = time.time() - self.cancel_countdown_start
            self.cancel_remaining = max(0, config.CANCEL_WINDOW_SECONDS - int(elapsed))
            
            if elapsed >= config.CANCEL_WINDOW_SECONDS:
                self._log("CANCEL WINDOW EXPIRED - ESCALATING TO EMERGENCY")
                self.cancel_active = False
                self.cancel_remaining = 0
                
                # Logic implicitly states: If countdown reaches 0 → escalate to next level
                if state == "EYES_CLOSED" or action == "LOUD_BUZZER":
                    state = "DRIVER_ASLEEP"
                    action = "MAX_BUZZER + CALL_DRIVER"
            else:
                # Still in cancellation window, wait it out
                return

        # Start of countdown for EYES_CLOSED
        if (state == "EYES_CLOSED" or action == "LOUD_BUZZER") and not self.cancel_active:
            self.cancel_active = True
            self.cancel_countdown_start = time.time()
            self.cancel_remaining = config.CANCEL_WINDOW_SECONDS
            self._log(f"STARTING {config.CANCEL_WINDOW_SECONDS}s CANCELLATION COUNTDOWN.")
            self._send_command_to_esp32("BUZZ_LOUD")
            return

        # Send Hardware Commands
        if action == "SOFT_BUZZER":
            self._send_command_to_esp32("BUZZ_SOFT")
        elif action == "MEDIUM_BUZZER":
            self._send_command_to_esp32("BUZZ_MEDIUM")
        elif "MAX_BUZZER" in action:
            self._send_command_to_esp32("BUZZ_MAX")
            self._send_command_to_esp32("VIBRATE_MAX")

        # Throttling SMS logic (Never send duplicate SMS within 5 minutes)
        current_time = time.time()
        if "SMS" in action or "CALL" in action:
            if (current_time - self.last_sms_time) < 300:
                # Already sent an emergency SMS within the last 5 minutes
                return

        # Prepare Text Payload Data
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lat = classification_result.get("lat", 0.0)
        lng = classification_result.get("lng", 0.0)
        hr = classification_result.get("hr", 0)
        spo2 = classification_result.get("spo2", 0)

        # Handle SMS Generation
        if state == "CARDIAC_EMERGENCY":
            hosp_name, dist = self._get_nearest_hospital(lat, lng)
            body = (f"CARDIAC EMERGENCY - VitalDrive Alert\n"
                    f"Patient: Driver\n"
                    f"HR: {hr} BPM | SpO2: {spo2}%\n"
                    f"ECG: Irregular pattern detected\n"
                    f"Location: https://maps.google.com/?q={lat},{lng}\n"
                    f"Nearest Hospital: {hosp_name} ({dist}km)\n"
                    f"Time: {timestamp}")
            self._send_sms(config.HOSPITAL_CONTACT, body)
            self._send_sms(config.EMERGENCY_CONTACT, body)
            self.last_sms_time = current_time
            
        elif state in ["ACCIDENT", "CARDIAC_CAUSED_CRASH"]:
            body = (f"CRASH EMERGENCY - VitalDrive Alert\n"
                    f"High impact detected\n"
                    f"HR: {hr} BPM | SpO2: {spo2}%\n"
                    f"Location: https://maps.google.com/?q={lat},{lng}\n"
                    f"Time: {timestamp}")
            self._send_sms(config.EMERGENCY_CONTACT, body)
            self.last_sms_time = current_time
            
        elif state == "MEDICAL_SHOCK":
            body = (f"CRITICAL MEDICAL SHOCK - VitalDrive Alert\n"
                    f"Driver vitals crashed below critical limits.\n"
                    f"HR: {hr} BPM | SpO2: {spo2}%\n"
                    f"Location: https://maps.google.com/?q={lat},{lng}\n"
                    f"Time: {timestamp}")
            self._send_sms(config.HOSPITAL_CONTACT, body)
            self._send_sms(config.EMERGENCY_CONTACT, body)
            self.last_sms_time = current_time

        elif state == "DRIVER_ASLEEP":
            self._log("Calling Emergency Contact... (Simulated Phone Call)")
            # You could insert Twilio Call client logic here
            self.last_sms_time = current_time
