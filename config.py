# Camera
USE_ESP32_CAM = False  # switch to True when ECE team gives IP
ESP32_CAM_URL = "http://192.168.1.100/stream"  # placeholder IP

# Serial
SERIAL_PORT = "AUTO"  # auto detect COM port
BAUD_RATE = 115200
SIMULATION_MODE = True  # True when ESP32 not connected

# Vision thresholds
EAR_THRESHOLD = 0.25
DROWSY_SECONDS = 2.0
HEAD_ANGLE_THRESHOLD = 30

# Health thresholds
HR_MIN = 40
HR_MAX = 120
SPO2_MIN = 90
SPO2_CRITICAL = 85
ECG_IRREGULARITY_THRESHOLD = 0.7

# Alert timings
CANCEL_WINDOW_SECONDS = 10
ESCALATION_DELAY = 5

# Twilio (placeholders)
TWILIO_SID = "your_sid"
TWILIO_TOKEN = "your_token"
TWILIO_FROM = "+1xxxxxxxxxx"
EMERGENCY_CONTACT = "+91xxxxxxxxxx"
HOSPITAL_CONTACT = "+91xxxxxxxxxx"
