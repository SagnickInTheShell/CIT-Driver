# VitalDrive AI 🚗💓

**VitalDrive AI** is an in-vehicle driver monitoring and cardiac emergency detection system built for our college hackathon. 

It seamlessly combines real-time computer vision (tracking drowsiness and head drooping) with hardware sensor data (heart rate, SpO2, and ECG) to evaluate a driver's state and instantly escalate alerts when accidents or medical emergencies occur.

## Features ✨
- **Computer Vision Pipeline**: Uses the MediaPipe FaceLandmarker API and OpenCV to accurately track eye aspect ratio (EAR) and head pitch angles for real-time drowsiness detection.
- **Hardware Integration**: Reads and processes serial data from an ESP32 connected to MAX30102 (SpO2/HR), AD8232 (ECG), and a Neo-6M GPS.
- **Smart Logic Engine**: Contextually evaluates 8 different emergency states (e.g., Driver Asleep, Medical Shock, Cardiac Emergency + Accident).
- **Communication Alerts**: Harnesses the Twilio API to automatically dispatch formatted SMS alerts containing the driver's vitals, GPS coordinates, and routing to the nearest hospital via OpenStreetMap mapping.
- **Live GUI Dashboard**: A responsive, non-blocking Tkinter dashboard overlay mapped dynamically to update vitals and hardware sensors at 10Hz.

## Project Structure 📁
- `main.py`: Coordinates the application threads, dashboard, and demo loops.
- `vision.py`: Detects driver focus utilizing MediaPipe's computer vision.
- `sensors.py`: Connects and parses real-time Serial USB vitals from the ESP32 (with a realistic simulation mode).
- `logic.py`: Evaluates the vision and sensor state continuously against predefined thresholds.
- `alerts.py`: Operates Twilio hooks, OSM logic, and buzzer communication to external hardware.
- `dashboard.py`: Renders the live graphical interface.
- `config.py`: Adjust global variables like constants, boundaries, threshold limits, API keys, and simulation modes.

## Setup & Installation 🛠️
1. Install Python 3.10+
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Download the MediaPipe `face_landmarker.task` model file and place it in the project root directory.
4. Open `config.py` and populate your API credentials (`TWILIO_SID`, `TWILIO_TOKEN`). Set `SIMULATION_MODE = True` if you are running the system without the ESP32 hardware connected.
5. Run the system:
   ```bash
   python main.py
   ```

## Hardware Note 🔌
If utilizing the live ESP32-CAM and external sensor hardware, ensure the ESP32 serial COM port is accessible, and set `SIMULATION_MODE = False` and `USE_ESP32_CAM = True` in `config.py`.
