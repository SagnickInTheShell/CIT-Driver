import time
import datetime
import requests
from twilio.rest import Client

import config
from voice import VoiceAlert

class AlertSystem:
    def __init__(self, serial_interface=None):
        self.serial = serial_interface

        # Twilio setup
        if config.TWILIO_SID != "your_sid" and config.TWILIO_TOKEN != "your_token":
            try:
                self.twilio = Client(config.TWILIO_SID, config.TWILIO_TOKEN)
            except Exception as e:
                self._log(f"Twilio Initialization Error: {e}")
                self.twilio = None
        else:
            self.twilio = None

        # Voice engine
        self.voice = VoiceAlert()
        self.voice.start()

        # SMS throttle
        self.last_sms_time = 0
        self.last_warning_sms_time = 0

        # Cancel window
        self.cancel_countdown_start = 0
        self.cancel_active = False
        self.cancel_remaining = 0

        # Escalating alert pattern
        self.offence_count = 0
        self.offence_window_start = 0
        self.offence_window = 300  # 5 minutes

        # Buzzer command throttle (prevents spam)
        self.last_command = None
        self.last_command_time = 0
        self.command_cooldown = 3  # seconds between identical commands

        # State handling throttle
        self.last_handled_state = None
        self.last_handle_time = 0
        self.handle_cooldown = 3  # seconds between re-handling same state

        # Alert history (for dashboard)
        self.alert_history = []  # list of (timestamp_str, message)
        self.max_history = 20

    def _log(self, message):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        print(log_line.strip())
        try:
            with open("alerts_log.txt", "a") as f:
                f.write(log_line)
        except Exception:
            pass

    def _add_history(self, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.alert_history.append((timestamp, message))
        if len(self.alert_history) > self.max_history:
            self.alert_history = self.alert_history[-self.max_history:]

    def get_history(self):
        return list(self.alert_history[-5:])  # last 5 for dashboard

    def _send_command_to_esp32(self, cmd):
        now = time.time()

        # Throttle: skip if same command was sent within cooldown (RESET always goes through)
        if cmd != "RESET" and cmd == self.last_command and (now - self.last_command_time) < self.command_cooldown:
            return

        self.last_command = cmd
        self.last_command_time = now

        if self.serial and hasattr(self.serial, 'write'):
            try:
                self.serial.write(f"{cmd}\n".encode('utf-8'))
            except Exception as e:
                self._log(f"Failed to send to ESP32: {e}")
        self._log(f"COMMAND to ESP32: {cmd}")

    # ─── Smart Hospital Selection ───

    def _get_nearest_hospitals(self, lat, lng, count=3):
        hospitals = []
        try:
            url = (
                f"https://nominatim.openstreetmap.org/search.php"
                f"?q=hospital&format=jsonv2&lat={lat}&lon={lng}&limit={count}"
            )
            headers = {'User-Agent': 'VitalDriveApp/1.0 (Student Hackathon Project)'}
            response = requests.get(url, headers=headers, timeout=5)

            if response.status_code == 200:
                data = response.json()
                for entry in data[:count]:
                    name = entry.get('display_name', 'Unknown Hospital').split(',')[0]
                    h_lat = float(entry['lat'])
                    h_lon = float(entry['lon'])
                    dist = ((lat - h_lat)**2 + (lng - h_lon)**2)**0.5 * 111
                    hospitals.append((name, round(dist, 1)))

        except Exception as e:
            self._log(f"OSM API Error: {e}")

        if not hospitals:
            hospitals = [("Nearest Hospital", 0.0)]

        # Sort by distance and return
        hospitals.sort(key=lambda x: x[1])
        return hospitals

    # ─── SMS ───

    def _send_sms(self, to_number, body):
        self._log(f"Sending SMS to {to_number}:\n{body}")
        if self.twilio:
            try:
                message = self.twilio.messages.create(
                    body=body, from_=config.TWILIO_FROM, to=to_number
                )
                self._log(f"SMS Sent! SID: {message.sid}")
            except Exception as e:
                self._log(f"Twilio Error: {e}")
        else:
            self._log("(SIMULATED SMS - Twilio not configured)")

    # ─── Escalation Logic ───

    def _track_offence(self):
        now = time.time()

        # Reset window after 5 minutes of no offences
        if now - self.offence_window_start > self.offence_window:
            self.offence_count = 0
            self.offence_window_start = now

        self.offence_count += 1
        return self.offence_count

    def _get_escalation_level(self, base_action):
        count = self._track_offence()

        if count >= 3:
            # Third offence within 5 min → emergency mode
            if "SOFT" in base_action:
                return "BUZZ_LOUD"
            elif "MEDIUM" in base_action:
                return "BUZZ_MAX"
            return base_action
        elif count >= 2:
            # Second offence → louder + voice
            if "SOFT" in base_action:
                return "BUZZ_MEDIUM"
            elif "MEDIUM" in base_action:
                return "BUZZ_LOUD"
            return base_action
        else:
            return base_action

    # ─── Main handler ───

    def handle(self, classification_result, button_pressed=False):
        state = classification_result.get("state", "NORMAL")
        action = classification_result.get("action_needed", "NONE")
        risk_score = classification_result.get("risk_score", 0)
        risk_level = classification_result.get("risk_level", "NORMAL")

        # ─── Cancel window logic ───
        if button_pressed and self.cancel_active:
            self._log("ALERT CANCELLED BY DRIVER (Button Pressed)")
            self._add_history("ALERT CANCELLED")
            self._send_command_to_esp32("RESET")
            self.cancel_active = False
            self.cancel_remaining = 0
            return

        if self.cancel_active:
            elapsed = time.time() - self.cancel_countdown_start
            self.cancel_remaining = max(0, config.CANCEL_WINDOW_SECONDS - int(elapsed))

            if elapsed >= config.CANCEL_WINDOW_SECONDS:
                self._log("CANCEL WINDOW EXPIRED - ESCALATING")
                self._add_history("CANCEL EXPIRED - ESCALATING")
                self.cancel_active = False
                self.cancel_remaining = 0

                if state in ["EYES_CLOSED", "MICROSLEEP"]:
                    state = "DRIVER_ASLEEP"
                    action = "MAX_BUZZER + CALL_DRIVER"
            else:
                return

        # Skip non-alert states
        if state == "NORMAL" and action == "NONE":
            return

        # Throttle: don't re-handle the same non-emergency state within cooldown
        emergency_states = {"CARDIAC_EMERGENCY", "ACCIDENT", "CARDIAC_CAUSED_CRASH",
                            "MEDICAL_SHOCK", "DRIVER_ASLEEP", "RISK_EMERGENCY"}
        now = time.time()
        if state not in emergency_states:
            if state == self.last_handled_state and (now - self.last_handle_time) < self.handle_cooldown:
                return
        self.last_handled_state = state
        self.last_handle_time = now

        # ─── Start countdown for EYES_CLOSED / MICROSLEEP ───
        if state in ["EYES_CLOSED", "MICROSLEEP"] and "LOUD" in action and not self.cancel_active:
            self.cancel_active = True
            self.cancel_countdown_start = time.time()
            self.cancel_remaining = config.CANCEL_WINDOW_SECONDS
            self._log(f"STARTING {config.CANCEL_WINDOW_SECONDS}s CANCELLATION COUNTDOWN")
            self._add_history(f"{state} - {config.CANCEL_WINDOW_SECONDS}s COUNTDOWN")
            self._send_command_to_esp32("BUZZ_LOUD")
            self.voice.speak(state)
            return

        # ─── Hardware buzzer commands with escalation ───
        if action == "SOFT_BUZZER":
            escalated = self._get_escalation_level("BUZZ_SOFT")
            self._send_command_to_esp32(escalated)
            self._add_history(f"{state} detected")
            self.voice.speak(state)

        elif action == "MEDIUM_BUZZER":
            escalated = self._get_escalation_level("BUZZ_MEDIUM")
            self._send_command_to_esp32(escalated)
            self._add_history(f"{state} detected")
            self.voice.speak(state)

        elif "MAX_BUZZER" in action:
            self._send_command_to_esp32("BUZZ_MAX")
            self._send_command_to_esp32("VIBRATE_MAX")
            self._add_history(f"{state} - MAX ALERT")
            self.voice.speak(state)

        # ─── Pre-Emergency Warning SMS (risk score 7-8) ───
        current_time = time.time()
        if risk_score >= config.PRE_EMERGENCY_SCORE and risk_level == "HIGH_ALERT":
            if (current_time - self.last_warning_sms_time) > 300:
                lat = classification_result.get("lat", 0.0)
                lng = classification_result.get("lng", 0.0)
                body = (
                    f"VitalDrive Warning: Driver showing signs of fatigue.\n"
                    f"Risk Score: {risk_score}/15\n"
                    f"Monitoring closely.\n"
                    f"Location: https://maps.google.com/?q={lat},{lng}"
                )
                self._send_sms(config.EMERGENCY_CONTACT, body)
                self._add_history("WARNING SMS sent to contact")
                self.last_warning_sms_time = current_time

        # ─── Emergency SMS (throttled: 5 min cooldown) ───
        if "SMS" in action or "CALL" in action:
            if (current_time - self.last_sms_time) < 300:
                return

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lat = classification_result.get("lat", 0.0)
        lng = classification_result.get("lng", 0.0)
        hr = classification_result.get("hr", 0)
        spo2 = classification_result.get("spo2", 0)

        if state == "CARDIAC_EMERGENCY":
            hospitals = self._get_nearest_hospitals(lat, lng, count=3)
            primary = hospitals[0]
            hospital_lines = "\n".join([f"  {i+1}. {h[0]} ({h[1]}km)" for i, h in enumerate(hospitals)])

            body = (
                f"CARDIAC EMERGENCY - VitalDrive Alert\n"
                f"Patient: Driver\n"
                f"HR: {hr} BPM | SpO2: {spo2}%\n"
                f"ECG: Irregular pattern detected\n"
                f"Location: https://maps.google.com/?q={lat},{lng}\n"
                f"Nearest Hospitals:\n{hospital_lines}\n"
                f"Time: {timestamp}"
            )
            self._send_sms(config.HOSPITAL_CONTACT, body)
            self._send_sms(config.EMERGENCY_CONTACT, body)
            self._add_history("CARDIAC EMERGENCY - SMS sent")
            self.voice.speak(state)
            self.last_sms_time = current_time

        elif state in ["ACCIDENT", "CARDIAC_CAUSED_CRASH"]:
            hospitals = self._get_nearest_hospitals(lat, lng, count=3)
            hospital_lines = "\n".join([f"  {i+1}. {h[0]} ({h[1]}km)" for i, h in enumerate(hospitals)])

            body = (
                f"CRASH EMERGENCY - VitalDrive Alert\n"
                f"High impact detected\n"
                f"HR: {hr} BPM | SpO2: {spo2}%\n"
                f"Location: https://maps.google.com/?q={lat},{lng}\n"
                f"Nearest Hospitals:\n{hospital_lines}\n"
                f"Time: {timestamp}"
            )
            self._send_sms(config.EMERGENCY_CONTACT, body)
            self._add_history("CRASH EMERGENCY - SMS sent")
            self.voice.speak(state)
            self.last_sms_time = current_time

        elif state == "MEDICAL_SHOCK":
            hospitals = self._get_nearest_hospitals(lat, lng, count=3)
            hospital_lines = "\n".join([f"  {i+1}. {h[0]} ({h[1]}km)" for i, h in enumerate(hospitals)])

            body = (
                f"CRITICAL MEDICAL SHOCK - VitalDrive Alert\n"
                f"Driver vitals crashed below critical limits.\n"
                f"HR: {hr} BPM | SpO2: {spo2}%\n"
                f"Location: https://maps.google.com/?q={lat},{lng}\n"
                f"Nearest Hospitals:\n{hospital_lines}\n"
                f"Time: {timestamp}"
            )
            self._send_sms(config.HOSPITAL_CONTACT, body)
            self._send_sms(config.EMERGENCY_CONTACT, body)
            self._add_history("MEDICAL SHOCK - SMS sent")
            self.voice.speak(state)
            self.last_sms_time = current_time

        elif state == "DRIVER_ASLEEP":
            self._log("Calling Emergency Contact... (Simulated Phone Call)")
            self._add_history("DRIVER ASLEEP - Calling contact")
            self.voice.speak(state)
            self.last_sms_time = current_time

        elif state == "RISK_EMERGENCY":
            hospitals = self._get_nearest_hospitals(lat, lng, count=3)
            hospital_lines = "\n".join([f"  {i+1}. {h[0]} ({h[1]}km)" for i, h in enumerate(hospitals)])

            body = (
                f"RISK EMERGENCY - VitalDrive Alert\n"
                f"Multiple risk factors detected simultaneously.\n"
                f"Risk Score: {classification_result.get('risk_score', 0)}\n"
                f"HR: {hr} BPM | SpO2: {spo2}%\n"
                f"Location: https://maps.google.com/?q={lat},{lng}\n"
                f"Nearest Hospitals:\n{hospital_lines}\n"
                f"Time: {timestamp}"
            )
            self._send_sms(config.HOSPITAL_CONTACT, body)
            self._send_sms(config.EMERGENCY_CONTACT, body)
            self._add_history("RISK EMERGENCY - SMS sent")
            self.last_sms_time = current_time

    def stop(self):
        self.voice.stop()
