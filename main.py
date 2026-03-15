import time
import sys
import datetime

import config
from vision import VisionMonitor
from sensors import SensorMonitor
from logic import LogicController
from alerts import AlertSystem
from dashboard import Dashboard

class AppSystem:
    def __init__(self):
        self.start_time = time.time()
        self.demo_active = False
        self.demo_started = False
        
        print("====== VITALDRIVE AI INITIALIZING ======")
        print(f"Simulation Mode: {config.SIMULATION_MODE}")
        print(f"Camera Mode: {'ESP32-CAM' if config.USE_ESP32_CAM else 'LOCAL WEBCAM'}")
        
        # Initialize Core Components
        self.sensors = SensorMonitor()
        self.vision = VisionMonitor()
        self.logic = LogicController()
        
        # Start Sensor Thread
        print("Starting Hardware/Sensor thread...")
        self.sensors.start()
        time.sleep(2) # Wait for init
        
        # Alert System needs serial interface for buzzer commands
        serial_interface = None
        # Note: In a full hardware setup, you would pass the pyserial object from sensors here.
        # For simplicity/simulation handling as requested:
        self.alerts = AlertSystem(serial_interface=serial_interface)
        
        # Start Vision Thread
        print("Starting Camera/Vision thread...")
        self.vision.start()
        time.sleep(1) # Wait for camera
        
        print("Starting UI Dashboard...")
        self.dashboard = Dashboard(bg_update_callback=self.update_loop, cancel_callback=self.on_driver_cancel)
        
    def demo_mode(self):
        """Hackathon Demo Mode logic triggered internally"""
        elapsed = time.time() - self.start_time
        
        if elapsed < 10:
            return None # Run normal
            
        elif 10 <= elapsed < 25:
            # Simulate eyes closing after 10 seconds
            # Injects "EYES_CLOSED" vision state overriding the real camera
            return "EYES_CLOSED"
            
        elif elapsed >= 25:
            if not self.demo_started:
                print("--- DEMO INJECTING CARDIAC EMERGENCY ---")
                self.sensors.inject_cardiac_emergency()
                self.demo_started = True
                
        return None

    def update_loop(self, dashboard_ref):
        try:
            # Get latest vision status
            vision_status = self.vision.get_status()
            
            # Apply demo overrides if activated
            if self.demo_active:
                override = self.demo_mode()
                if override:
                    vision_status = override

            # Get latest sensor data
            sensor_data = self.sensors.get_data()
            
            # Brain Classification
            result = self.logic.classify(vision_status, sensor_data)
            
            # Trigger corresponding Hardware/SMS Alerts
            self.alerts.handle(result, button_pressed=False)
            
            # Update Tkinter Display Data
            dashboard_ref.update_sensors(sensor_data)
            dashboard_ref.update_state(
                state=result["state"], 
                action=result["action_needed"],
                cancel_remaining=self.alerts.cancel_remaining
            )
            
            # Render camera frame to UI
            frame = self.vision.current_frame
            if frame is not None:
                dashboard_ref.set_camera_frame(frame)
                
        except Exception as e:
            print(f"MAIN LOOP ERROR: {e}")

    def on_driver_cancel(self):
        print("Dashboard Cancel Button Pressed!")
        # Trigger Handle with flag to intercept the cancel window
        dummy_result = {"state": "NORMAL", "action_needed": "NONE"}
        self.alerts.handle(dummy_result, button_pressed=True)
        
    def run(self, enable_demo=False):
        self.demo_active = enable_demo
        try:
             self.dashboard.mainloop()
        except KeyboardInterrupt:
             pass
        self.shutdown()

    def shutdown(self):
        print("\nShutting down VitalDrive AI...")
        
        # Send Reset
        if self.alerts:
            self.alerts._send_command_to_esp32("RESET")
            
        if self.vision:
            self.vision.stop()
            
        if self.sensors:
            self.sensors.stop()
            
        # Save final log
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open("alerts_log.txt", "a") as f:
                 f.write(f"\n[{timestamp}] SYSTEM STOPPED CLEANLY.\n")
        except:
            pass
        
        print("Shutdown complete.")
        sys.exit(0)

if __name__ == "__main__":
    app_system = AppSystem()
    
    # Set to True if hackathon judges want the fully automated pipeline demo
    DEMO_MODE_FLAG = True 
    
    app_system.run(enable_demo=DEMO_MODE_FLAG)
