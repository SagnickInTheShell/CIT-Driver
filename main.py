import time
import sys
import datetime
import threading

import config
from vision import VisionMonitor
from sensors import SensorMonitor
from logic import LogicController
from alerts import AlertSystem
from dashboard import Dashboard

DEMO_STAGES = [
    # (start_s, end_s, label, vision_override, sensor_action)
    (0,   8,  "Stage 1/8 — Normal Driving",         None,            None),
    (8,  12,  "Stage 2/8 — Yawning Detected",       "YAWNING",       None),
    (12, 16,  "Stage 3/8 — Eyes Closing",            "EYES_CLOSING",  None),
    (16, 20,  "Stage 4/8 — Eyes Closed + Alarm",     "EYES_CLOSED",   None),
    (20, 25,  "Stage 5/8 — Driver Unresponsive",     "EYES_CLOSED",   None),
    (25, 30,  "Stage 6/8 — ECG Irregular, SpO2 Dropping", None,      "PRE_CARDIAC"),
    (30, 35,  "Stage 7/8 — CARDIAC EMERGENCY",       None,           "CARDIAC"),
    (35, 40,  "Stage 8/8 — SMS Sent, Hospital Notified", None,       None),
]

class AppSystem:
    def __init__(self):
        self.start_time = time.time()
        self.demo_active = False
        self.demo_cardiac_injected = False
        self.demo_pre_cardiac_injected = False

        print("═" * 50)
        print("   VITALDRIVE AI — INITIALIZING")
        print("═" * 50)
        print(f"  Simulation Mode : {config.SIMULATION_MODE}")
        print(f"  Camera Mode     : {'ESP32-CAM' if config.USE_ESP32_CAM else 'LOCAL WEBCAM'}")
        print(f"  Voice Enabled   : {config.VOICE_ENABLED}")
        print("═" * 50)

        # Initialize components
        self.sensors = SensorMonitor()
        self.vision = VisionMonitor()
        self.logic = LogicController()

        # Start sensors
        print("  [1/4] Starting sensor thread...")
        self.sensors.start()
        time.sleep(2)

        # Alerts (includes voice engine)
        print("  [2/4] Starting alert system...")
        self.alerts = AlertSystem(serial_interface=None)

        # Start vision
        print("  [3/4] Starting camera/vision thread...")
        self.vision.start()
        time.sleep(1)

        # Dashboard
        print("  [4/4] Starting dashboard...")
        self.dashboard = Dashboard(
            bg_update_callback=self.update_loop,
            cancel_callback=self.on_driver_cancel
        )

        # Keyboard shortcut listener
        self._bind_keys()

        print("═" * 50)
        print("  SYSTEM READY — All modules online")
        print("  Keyboard: D=Demo  R=Reset  E=Cardiac  A=Accident  Q=Quit")
        print("═" * 50)

    def _bind_keys(self):
        self.dashboard.root.bind("<KeyPress-d>", lambda e: self._toggle_demo())
        self.dashboard.root.bind("<KeyPress-D>", lambda e: self._toggle_demo())
        self.dashboard.root.bind("<KeyPress-r>", lambda e: self._reset_all())
        self.dashboard.root.bind("<KeyPress-R>", lambda e: self._reset_all())
        self.dashboard.root.bind("<KeyPress-e>", lambda e: self._inject_cardiac())
        self.dashboard.root.bind("<KeyPress-E>", lambda e: self._inject_cardiac())
        self.dashboard.root.bind("<KeyPress-a>", lambda e: self._inject_accident())
        self.dashboard.root.bind("<KeyPress-A>", lambda e: self._inject_accident())
        self.dashboard.root.bind("<KeyPress-q>", lambda e: self._quit())
        self.dashboard.root.bind("<KeyPress-Q>", lambda e: self._quit())

    # ─── Keyboard actions ───

    def _toggle_demo(self):
        self.demo_active = not self.demo_active
        self.start_time = time.time()
        self.demo_cardiac_injected = False
        self.demo_pre_cardiac_injected = False
        status = "ON" if self.demo_active else "OFF"
        print(f"  >> DEMO MODE {status}")
        if not self.demo_active:
            self.dashboard.set_demo_stage("")

    def _reset_all(self):
        print("  >> RESET ALL ALERTS")
        self.alerts._send_command_to_esp32("RESET")
        self.alerts.cancel_active = False
        self.alerts.cancel_remaining = 0
        self.alerts.offence_count = 0
        self.dashboard.safety_score = 100
        self.dashboard.set_demo_stage("")
        self.demo_active = False

    def _inject_cardiac(self):
        print("  >> INJECTING CARDIAC EMERGENCY")
        self.sensors.inject_cardiac_emergency()

    def _inject_accident(self):
        print("  >> INJECTING ACCIDENT")
        self.sensors.inject_accident()

    def _quit(self):
        self.shutdown()

    # ─── Demo mode ───

    def _get_demo_state(self, elapsed):
        for start, end, label, vis_override, sensor_action in DEMO_STAGES:
            if start <= elapsed < end:
                return label, vis_override, sensor_action

        # After all stages complete
        return "DEMO COMPLETE", None, None

    def demo_mode(self):
        elapsed = time.time() - self.start_time
        label, vis_override, sensor_action = self._get_demo_state(elapsed)

        self.dashboard.set_demo_stage(f"DEMO: {label}")

        # Handle sensor injections at appropriate stages
        if sensor_action == "PRE_CARDIAC" and not self.demo_pre_cardiac_injected:
            self.sensors.inject_cardiac_emergency()
            self.demo_pre_cardiac_injected = True

        if sensor_action == "CARDIAC" and not self.demo_cardiac_injected:
            self.sensors.inject_cardiac_emergency()
            self.demo_cardiac_injected = True

        return vis_override

    # ─── Main update loop (called at 10Hz by dashboard) ───

    def update_loop(self, dashboard_ref):
        try:
            # Get vision status
            vision_status = self.vision.get_status()

            # Apply demo overrides
            if self.demo_active:
                override = self.demo_mode()
                if override:
                    vision_status = override

            # Get sensor data
            sensor_data = self.sensors.get_data()

            # Brain classification
            result = self.logic.classify(vision_status, sensor_data)

            # Trigger alerts
            self.alerts.handle(result, button_pressed=False)

            # Update dashboard — sensors
            dashboard_ref.update_sensors(sensor_data)

            # Update dashboard — vision metrics
            dashboard_ref.update_vision_metrics(
                perclos=self.vision.get_perclos(),
                blink_rate=self.vision.get_blink_rate()
            )

            # Update dashboard — risk gauge
            dashboard_ref.update_risk_gauge(
                risk_score=result.get("risk_score", 0),
                risk_level=result.get("risk_level", "NORMAL")
            )

            # Update dashboard — state + cancel countdown
            dashboard_ref.update_state(
                state=result["state"],
                action=result["action_needed"],
                cancel_remaining=self.alerts.cancel_remaining
            )

            # Update dashboard — alert history
            dashboard_ref.update_history(self.alerts.get_history())

            # Render camera frame
            frame = self.vision.current_frame
            if frame is not None:
                dashboard_ref.set_camera_frame(frame)

        except Exception as e:
            print(f"MAIN LOOP ERROR: {e}")
            try:
                with open("error_log.txt", "a") as f:
                    f.write(f"MAIN LOOP ERROR: {str(e)}\n")
            except Exception:
                pass

    def on_driver_cancel(self):
        print("  >> Dashboard Cancel Button Pressed!")
        dummy_result = {
            "state": "NORMAL", "action_needed": "NONE",
            "risk_score": 0, "risk_level": "NORMAL"
        }
        self.alerts.handle(dummy_result, button_pressed=True)

    def run(self, enable_demo=False):
        self.demo_active = enable_demo
        try:
            self.dashboard.mainloop()
        except KeyboardInterrupt:
            pass
        self.shutdown()

    def shutdown(self):
        print("\n  Shutting down VitalDrive AI...")

        if self.alerts:
            self.alerts._send_command_to_esp32("RESET")
            self.alerts.stop()

        if self.vision:
            self.vision.stop()

        if self.sensors:
            self.sensors.stop()

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open("alerts_log.txt", "a") as f:
                f.write(f"\n[{timestamp}] SYSTEM STOPPED CLEANLY.\n")
        except Exception:
            pass

        print("  Shutdown complete.")
        sys.exit(0)


if __name__ == "__main__":
    app = AppSystem()

    # Set to True for hackathon demo (automated 8-stage showcase)
    DEMO_MODE_FLAG = True

    app.run(enable_demo=DEMO_MODE_FLAG)
