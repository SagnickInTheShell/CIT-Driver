import cv2
import time
import tkinter as tk
from tkinter import font, Scrollbar, Canvas, Frame, Label, Button
from PIL import Image, ImageTk
import math

import config

class Dashboard:
    def __init__(self, bg_update_callback=None, cancel_callback=None):
        self.root = tk.Tk()
        self.root.title("VitalDrive AI - Driver Monitoring System")
        self.root.geometry("1024x600")
        self.root.configure(bg="#1e1e1e")
        
        self.bg_update_callback = bg_update_callback
        self.cancel_callback = cancel_callback
        
        self.ecg_data = [0]*100 # buffer for scrolling graph
        
        self._setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
    def _setup_ui(self):
        # LEFT PANE (Video)
        self.left_frame = Frame(self.root, bg="#1e1e1e", width=640, height=540)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=20, pady=20)
        
        self.video_label = Label(self.left_frame, bg="black", width=640, height=480)
        self.video_label.pack(side=tk.TOP)
        
        self.status_label = Label(self.left_frame, text="INITIALIZING...", 
                                  font=("Arial", 24, "bold"), fg="#ffffff", bg="#1e1e1e")
        self.status_label.pack(side=tk.BOTTOM, pady=10)
        
        # RIGHT PANE (Stats & Controls)
        self.right_frame = Frame(self.root, bg="#2d2d2d", width=340, height=540)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Top right - Vitals
        self.vitals_frame = Frame(self.right_frame, bg="#2d2d2d")
        self.vitals_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        
        Label(self.vitals_frame, text="HEART RATE", font=("Arial", 12), fg="#aaaaaa", bg="#2d2d2d").grid(row=0, column=0, sticky="w")
        self.hr_label = Label(self.vitals_frame, text="--", font=("Arial", 36, "bold"), fg="#00ff00", bg="#2d2d2d")
        self.hr_label.grid(row=1, column=0, sticky="w", padx=10)
        
        Label(self.vitals_frame, text="SpO2", font=("Arial", 12), fg="#aaaaaa", bg="#2d2d2d").grid(row=0, column=1, sticky="w", padx=20)
        self.spo2_label = Label(self.vitals_frame, text="--%", font=("Arial", 36, "bold"), fg="#00ff00", bg="#2d2d2d")
        self.spo2_label.grid(row=1, column=1, sticky="w", padx=30)
        
        self.gps_label = Label(self.right_frame, text="GPS: Waiting...", font=("Arial", 10), fg="#888888", bg="#2d2d2d")
        self.gps_label.pack(side=tk.TOP, pady=5)
        
        # Middle right - ECG Graph
        Label(self.right_frame, text="ECG TRACE", font=("Arial", 12), fg="#aaaaaa", bg="#2d2d2d").pack(side=tk.TOP, pady=(20, 0))
        self.ecg_canvas = Canvas(self.right_frame, width=300, height=100, bg="black", highlightthickness=0)
        self.ecg_canvas.pack(side=tk.TOP, pady=5)
        
        # Bottom right - Alert Status & Cancel
        self.alert_frame = Frame(self.right_frame, bg="#2d2d2d")
        self.alert_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=20)
        
        self.alert_text = Label(self.alert_frame, text="ALL SYSTEMS NORMAL", font=("Arial", 16, "bold"), fg="#00ff00", bg="#2d2d2d")
        self.alert_text.pack(side=tk.TOP, pady=10)
        
        self.countdown_label = Label(self.alert_frame, text="", font=("Arial", 36, "bold"), fg="red", bg="#2d2d2d")
        self.countdown_label.pack(side=tk.TOP)
        
        self.cancel_btn = Button(self.alert_frame, text="CANCEL ALERT (Simulate Button)", 
                                 font=("Arial", 12, "bold"), bg="#555555", fg="white", 
                                 command=self._on_cancel, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.BOTTOM, pady=10, ipadx=10, ipady=10)
        
        self.is_flashing = False

    def _on_close(self):
        self.root.destroy()
        
    def _on_cancel(self):
        if self.cancel_callback:
            self.cancel_callback()
            
    def set_camera_frame(self, cv2_img):
        if cv2_img is not None:
            # Resize appropriately
            cv2_img = cv2.resize(cv2_img, (640, 480))
            # Convert OpenCV BGR to RGB
            rgb = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)
            
    def update_sensors(self, data):
        hr = data.get("hr", 0)
        spo2 = data.get("spo2", 0)
        ecg = data.get("ecg", 0.0)
        lat = data.get("lat", 0.0)
        lng = data.get("lng", 0.0)
        
        # HR Color
        if hr < config.HR_MIN or hr > config.HR_MAX:
            self.hr_label.config(text=f"{hr:.0f}", fg="red")
        elif hr > 100 or hr < 50:
             self.hr_label.config(text=f"{hr:.0f}", fg="orange")
        else:
            self.hr_label.config(text=f"{hr:.0f}", fg="#00ff00")
            
        # SpO2 Color
        if spo2 <= config.SPO2_CRITICAL:
            self.spo2_label.config(text=f"{spo2:.0f}%", fg="red")
        elif spo2 < config.SPO2_MIN:
            self.spo2_label.config(text=f"{spo2:.0f}%", fg="orange")
        else:
            self.spo2_label.config(text=f"{spo2:.0f}%", fg="#00ff00")
            
        # GPS
        self.gps_label.config(text=f"GPS: {lat:.5f}, {lng:.5f}")
        
        # ECG Canvas drawing
        self.ecg_data.append(ecg)
        self.ecg_data.pop(0)
        
        self.ecg_canvas.delete("all")
        width = 300
        height = 100
        dx = width / len(self.ecg_data)
        
        points = []
        for i, val in enumerate(self.ecg_data):
            x = i * dx
            # scale val: assumes ecg range is approx -1 to 1
            y = height/2 - (val * 40)
            points.append(x)
            points.append(y)
            
        if len(points) >= 4:
            self.ecg_canvas.create_line(points, fill="#00ff00", width=2)
            
    def update_state(self, state, action, cancel_remaining):
        # Update UI Colors based on state severity
        if state in ["NORMAL", "ALERT"]:
            self.root.configure(bg="#1e1e1e")
            self.status_label.config(text=state.replace("_", " "), fg="#00ff00", bg="#1e1e1e")
            self.alert_text.config(text="ALL SYSTEMS NORMAL", fg="#00ff00")
            self.countdown_label.config(text="")
            self.cancel_btn.config(state=tk.DISABLED)
            
        elif state in ["HEAD_DROOPING", "EYES_CLOSING"]:
            self.root.configure(bg="#2a1f00") # Dark orange
            self.status_label.config(text=state.replace("_", " "), fg="orange", bg="#2a1f00")
            self.alert_text.config(text="WARNING: DROWSINESS", fg="orange")
            self.countdown_label.config(text="")
            self.cancel_btn.config(state=tk.DISABLED)
            
        else:
            # Emergency states: EYES_CLOSED, DRIVER_ASLEEP, CARDIAC_EMERGENCY, ACCIDENT, etc
            self.is_flashing = not self.is_flashing
            bg_color = "red" if self.is_flashing else "#4a0000"
            
            self.root.configure(bg=bg_color)
            self.status_label.config(text=state.replace("_", " "), fg="white", bg=bg_color)
            self.alert_text.config(text=f"EMERGENCY: {state}", fg="white")
            
            if cancel_remaining is not None and cancel_remaining > 0:
                self.countdown_label.config(text=f"{cancel_remaining}s")
                self.cancel_btn.config(state=tk.NORMAL)
            else:
                self.countdown_label.config(text="")
                self.cancel_btn.config(state=tk.DISABLED)

    def run_update_loop(self):
        if self.bg_update_callback:
            self.bg_update_callback(self)
        self.root.after(100, self.run_update_loop)

    def mainloop(self):
        # Initial call to start the loop
        self.root.after(100, self.run_update_loop)
        self.root.mainloop()
