import time
import math
import random
import json
import threading
import serial
import serial.tools.list_ports

import config

class SensorMonitor:
    def __init__(self):
        self.data_lock = threading.Lock()
        
        # Last known / default values
        self.data = {
            "hr": 75,
            "spo2": 98,
            "ecg": 0.0,
            "lat": 12.9716,
            "lng": 77.5946,
            "gps_available": False,
            "status": "initializing"
        }
        
        self.running = False
        self.thread = None
        self.sim_emergency = None
        self.emergency_start_time = 0
        self.sim_time = 0.0

    def get_data(self):
        with self.data_lock:
            return self.data.copy()

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join()

    def inject_cardiac_emergency(self):
        self.sim_emergency = "CARDIAC"
        self.emergency_start_time = time.time()

    def inject_accident(self):
        self.sim_emergency = "ACCIDENT"
        self.emergency_start_time = time.time()

    def _auto_detect_port(self):
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            # Simple heuristic: esp32 often uses CP210x or CH340, but grab the first available if not specific
            if "Serial" in port.description or "UART" in port.description or "CH340" in port.description or "CP210" in port.description:
                return port.device
        
        # Fallback to the first found port
        if ports:
            return ports[0].device
            
        return None

    def _parse_serial_line(self, line):
        line = line.strip()
        if not line:
            return None
            
        updates = {}
        
        # Try JSON
        if line.startswith('{') and line.endswith('}'):
            try:
                data = json.loads(line)
                updates["hr"] = data.get("hr", self.data["hr"])
                updates["spo2"] = data.get("spo2", self.data["spo2"])
                updates["ecg"] = data.get("ecg", self.data["ecg"])
                if "lat" in data and "lng" in data:
                    updates["lat"] = data["lat"]
                    updates["lng"] = data["lng"]
                    updates["gps_available"] = True
                return updates
            except json.JSONDecodeError:
                pass
                
        # Try Key-Value "HR:82,SPO2:97,ECG:0.023,LAT:12.97,LNG:77.59"
        if "HR:" in line or "SPO2:" in line:
            parts = line.split(',')
            for p in parts:
                kv = p.split(':')
                if len(kv) == 2:
                    k = kv[0].strip().upper()
                    try:
                        v = float(kv[1].strip())
                        if k == "HR": updates["hr"] = v
                        elif k == "SPO2": updates["spo2"] = v
                        elif k == "ECG": updates["ecg"] = v
                        elif k == "LAT": updates["lat"] = v
                        elif k == "LNG": updates["lng"] = v
                    except ValueError:
                        pass
            
            if "lat" in updates and "lng" in updates:
                updates["gps_available"] = True
            return updates
            
        # Try CSV "82,97,0.023,12.97,77.59"
        parts = line.split(',')
        if len(parts) >= 3:
            try:
                updates["hr"] = float(parts[0])
                updates["spo2"] = float(parts[1])
                updates["ecg"] = float(parts[2])
                if len(parts) >= 5:
                    updates["lat"] = float(parts[3])
                    updates["lng"] = float(parts[4])
                    updates["gps_available"] = True
                return updates
            except ValueError:
                pass
                
        return None

    def _simulate_data(self):
        self.sim_time += 0.1
        
        # Default baseline
        hr = 75 + math.sin(self.sim_time * 0.5) * 5 + random.uniform(-2, 2)
        spo2 = 98 - random.uniform(0, 1.5)
        # Simple ECG waveform simulation (P, QRS, T waves)
        t_mod = self.sim_time % 1.0
        ecg = 0.0
        if 0.1 < t_mod < 0.2: ecg = 0.2  # P wave
        elif 0.3 < t_mod < 0.35: ecg = -0.3 # Q wave
        elif 0.35 <= t_mod < 0.4: ecg = 1.0 # R wave
        elif 0.4 <= t_mod < 0.45: ecg = -0.4 # S wave
        elif 0.6 < t_mod < 0.75: ecg = 0.3 # T wave
        else: ecg = random.uniform(-0.05, 0.05) # Baseline noise
        
        lat = 12.9716 + random.uniform(-0.0001, 0.0001)
        lng = 77.5946 + random.uniform(-0.0001, 0.0001)
        
        # Apply injected emergencies
        if self.sim_emergency == "CARDIAC":
            elapsed = time.time() - self.emergency_start_time
            if elapsed < 30:
                hr = 130 + math.sin(self.sim_time * 2) * 20 # Tachycardia
                spo2 = max(80, 95 - elapsed) # SpO2 dropping
                ecg += random.uniform(-0.5, 0.5) # Irregular ECG
                
        elif self.sim_emergency == "ACCIDENT":
            hr = 140 + random.uniform(-5, 5) # Spiking HR
            spo2 = 98 - random.uniform(0, 5) # Slight drop
            # Sudden GPS coordinate spike mimicking impact displacement
            lat += 0.01
            lng += 0.01

        with self.data_lock:
            self.data["hr"] = round(hr, 1)
            self.data["spo2"] = round(spo2, 1)
            self.data["ecg"] = round(ecg, 3)
            self.data["lat"] = round(lat, 6)
            self.data["lng"] = round(lng, 6)
            self.data["gps_available"] = True
            self.data["status"] = "simulating"

    def _run(self):
        ser = None
        
        while self.running:
            if config.SIMULATION_MODE:
                self._simulate_data()
                time.sleep(0.1) # 10Hz update rate
                continue
                
            # Hardware mode
            try:
                if ser is None or not ser.is_open:
                    port = config.SERIAL_PORT
                    if port == "AUTO":
                        port = self._auto_detect_port()
                        
                    if port:
                        ser = serial.Serial(port, config.BAUD_RATE, timeout=1)
                        with self.data_lock:
                            self.data["status"] = "ok"
                    else:
                        with self.data_lock:
                            self.data["status"] = "no_port"
                            
                        # Wait a bit before retry, don't crash
                        time.sleep(1)
                        continue
                
                # Check hardware serial reading
                if ser.in_waiting:
                    raw_line = ser.readline().decode('utf-8', errors='ignore')
                    updates = self._parse_serial_line(raw_line)
                    
                    if updates:
                        with self.data_lock:
                            for k, v in updates.items():
                                self.data[k] = v
                            self.data["status"] = "ok"
                            
            except Exception as e:
                # Handle disconnect or read error seamlessly
                if ser:
                    ser.close()
                ser = None
                with self.data_lock:
                    self.data["status"] = "disconnected"
                
                with open("error_log.txt", "a") as f:
                    f.write(f"SENSORS ERROR: {str(e)}\n")
                    
                time.sleep(1) # Reconnect delay
                
            time.sleep(0.01) # Small sleep to prevent busy-waiting
            
        if ser:
            ser.close()
