import random
import time
import serial
import serial.tools.list_ports
import threading

class HealthMonitor:
    def __init__(self, baud_rate=115200):
        # Data
        self.heart_rate = 75.0
        self.spo2 = 98.0
        self.lat = 0.0
        self.lng = 0.0
        self.ecg_status = "Normal"
        self.emergency_detected = False
        self.emergency_reason = ""
        
        # Mode
        self.mode = "simulation"
        self.serial_port = None
        self.baud_rate = baud_rate
        
        # Simulation targets
        self.target_hr = 75.0
        self.target_spo2 = 98.0
        
        # Connect to hardware
        self.connect_serial()
        
    def connect_serial(self):
        try:
            ports = list(serial.tools.list_ports.comports())
            if not ports:
                print("No COM ports found. Falling back to Simulation Mode.")
                self.mode = "simulation"
                return
            
            # Auto-connect to first available port
            port = ports[0].device
            self.serial_port = serial.Serial(port, self.baud_rate, timeout=1)
            self.mode = "hardware"
            print(f"Connected to hardware on {port} at {self.baud_rate} baud.")
        except Exception as e:
            print(f"Failed to connect to serial port: {e}. Falling back to Simulation Mode.")
            self.mode = "simulation"

    def _read_serial_data(self):
        if not self.serial_port or not self.serial_port.is_open:
            self.mode = "simulation"
            return
            
        try:
            while self.serial_port.in_waiting > 0:
                line = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                # Expected format: HR:75,SPO2:98,LAT:12.9716,LNG:77.5946
                if not line:
                    continue
                parts = line.split(',')
                data = {}
                for part in parts:
                    if ':' in part:
                        k, v = part.split(':')
                        data[k.strip()] = float(v.strip())
                
                if 'HR' in data:
                    self.heart_rate = float(data['HR'])
                if 'SPO2' in data:
                    self.spo2 = float(data['SPO2'])
                if 'LAT' in data:
                    self.lat = float(data['LAT'])
                if 'LNG' in data:
                    self.lng = float(data['LNG'])
        except Exception as e:
            print(f"Serial read error: {e}. Switching to simulation.")
            self.mode = "simulation"
            if self.serial_port:
                self.serial_port.close()
                self.serial_port = None

    def _simulate_data(self):
        # 1. Random walk the underlying targets slowly
        if random.random() < 0.1: # 10% chance per frame to gently shift baseline
            self.target_hr += random.uniform(-1.5, 1.5)
            self.target_spo2 += random.uniform(-0.5, 0.5)
        
        # Keep targets in realistic normal bounds
        self.target_hr = max(55.0, min(100.0, self.target_hr))
        self.target_spo2 = max(94.0, min(100.0, self.target_spo2))
        
        # 3. Smooth mathematical approach (EMA) toward targets
        self.heart_rate += (self.target_hr - self.heart_rate) * 0.05
        self.spo2 += (self.target_spo2 - self.spo2) * 0.05

    def update_sensors(self):
        if self.mode == "hardware":
            self._read_serial_data()
        else:
            self._simulate_data()

        self.check_emergency()
        return self.get_data()

    def check_emergency(self):
        self.emergency_detected = False
        self.emergency_reason = ""
        
        if self.heart_rate > 120:
            self.emergency_detected = True
            self.emergency_reason = "High Heart Rate"
        elif self.heart_rate < 50:
            self.emergency_detected = True
            self.emergency_reason = "Low Heart Rate"
        
        if self.spo2 < 90:
            self.emergency_detected = True
            self.emergency_reason += " | Critical SpO2" if self.emergency_reason else "Critical SpO2"

    def get_data(self):
        return {
            "heart_rate": round(self.heart_rate, 1),
            "spo2": round(self.spo2, 1),
            "lat": self.lat,
            "lng": self.lng,
            "ecg_status": "Normal" if not self.emergency_detected else "Abnormal",
            "emergency": self.emergency_detected,
            "reason": self.emergency_reason,
            "mode": self.mode
        }

