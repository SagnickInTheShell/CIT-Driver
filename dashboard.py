import cv2
import time
import math
import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageTk

import config

class Dashboard:
    def __init__(self, bg_update_callback=None, cancel_callback=None):
        self.root = tk.Tk()
        self.root.title("VitalDrive AI — Driver Monitoring System")
        self.root.geometry("1280x720")
        self.root.configure(bg="#121212")
        self.root.resizable(True, True)

        self.bg_update_callback = bg_update_callback
        self.cancel_callback = cancel_callback

        self.ecg_data = [0] * 100
        self.is_flashing = False

        # Driver safety score
        self.safety_score = 100
        self.last_clean_time = time.time()

        # Demo stage display
        self.demo_stage_text = ""

        self._setup_fonts()
        self._setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_fonts(self):
        self.font_title = ("Segoe UI", 11, "bold")
        self.font_big = ("Segoe UI", 32, "bold")
        self.font_medium = ("Segoe UI", 16, "bold")
        self.font_small = ("Segoe UI", 10)
        self.font_tiny = ("Segoe UI", 9)
        self.font_status = ("Segoe UI", 20, "bold")

    def _make_section(self, parent, title, bg="#1e1e1e"):
        frame = tk.Frame(parent, bg=bg, highlightbackground="#333333", highlightthickness=1)
        if title:
            tk.Label(frame, text=title, font=self.font_title, fg="#888888", bg=bg,
                     anchor="w").pack(fill=tk.X, padx=8, pady=(6, 2))
        return frame

    def _setup_ui(self):
        # ═══════════════ LEFT COLUMN: Camera ═══════════════
        left_col = tk.Frame(self.root, bg="#121212")
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, padx=(12, 6), pady=12)

        # Camera feed
        cam_section = self._make_section(left_col, None)
        cam_section.pack(fill=tk.BOTH, expand=True)

        self.video_label = tk.Label(cam_section, bg="black")
        self.video_label.pack(padx=4, pady=4)

        # Status bar below camera
        self.status_label = tk.Label(cam_section, text="INITIALIZING...",
                                     font=self.font_status, fg="#00ff00", bg="#1e1e1e")
        self.status_label.pack(pady=(2, 8))

        # Demo stage indicator
        self.demo_label = tk.Label(cam_section, text="", font=self.font_small,
                                    fg="#ffcc00", bg="#1e1e1e")
        self.demo_label.pack(pady=(0, 4))

        # ═══════════════ RIGHT COLUMN: Stats ═══════════════
        right_col = tk.Frame(self.root, bg="#121212")
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 12), pady=12)

        # ─── Row 1: Vitals + Safety Score ───
        row1 = tk.Frame(right_col, bg="#121212")
        row1.pack(fill=tk.X, pady=(0, 6))

        # Heart Rate
        hr_section = self._make_section(row1, "HEART RATE")
        hr_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))
        self.hr_label = tk.Label(hr_section, text="--", font=self.font_big,
                                  fg="#00ff00", bg="#1e1e1e")
        self.hr_label.pack(pady=(0, 4))
        self.hrv_label = tk.Label(hr_section, text="HRV: --", font=self.font_tiny,
                                   fg="#888888", bg="#1e1e1e")
        self.hrv_label.pack(pady=(0, 6))

        # SpO2
        spo2_section = self._make_section(row1, "SpO2")
        spo2_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3)
        self.spo2_label = tk.Label(spo2_section, text="--%", font=self.font_big,
                                    fg="#00ff00", bg="#1e1e1e")
        self.spo2_label.pack(pady=(0, 4))
        self.spo2_trend_label = tk.Label(spo2_section, text="Trend: STABLE", font=self.font_tiny,
                                          fg="#888888", bg="#1e1e1e")
        self.spo2_trend_label.pack(pady=(0, 6))

        # Safety Score
        safety_section = self._make_section(row1, "SAFETY SCORE")
        safety_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3, 0))
        self.safety_label = tk.Label(safety_section, text="100", font=self.font_big,
                                      fg="#00ff00", bg="#1e1e1e")
        self.safety_label.pack(pady=(0, 10))

        # ─── Row 2: Risk Score Gauge + PERCLOS + Blink Rate ───
        row2 = tk.Frame(right_col, bg="#121212")
        row2.pack(fill=tk.X, pady=6)

        # Risk Score Gauge
        risk_section = self._make_section(row2, "RISK SCORE")
        risk_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))
        self.risk_canvas = tk.Canvas(risk_section, width=120, height=120, bg="#1e1e1e",
                                      highlightthickness=0)
        self.risk_canvas.pack(pady=(4, 4))
        self.risk_level_label = tk.Label(risk_section, text="NORMAL", font=self.font_tiny,
                                          fg="#00ff00", bg="#1e1e1e")
        self.risk_level_label.pack(pady=(0, 6))

        # PERCLOS + Blink Rate stacked
        perc_blink_section = self._make_section(row2, None)
        perc_blink_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3)

        # PERCLOS
        tk.Label(perc_blink_section, text="PERCLOS", font=self.font_title,
                 fg="#888888", bg="#1e1e1e", anchor="w").pack(fill=tk.X, padx=8, pady=(6, 2))
        self.perclos_canvas = tk.Canvas(perc_blink_section, width=180, height=24,
                                         bg="#333333", highlightthickness=0)
        self.perclos_canvas.pack(padx=8, pady=(0, 4))
        self.perclos_text = tk.Label(perc_blink_section, text="0.0%", font=self.font_small,
                                      fg="#00ff00", bg="#1e1e1e")
        self.perclos_text.pack(pady=(0, 6))

        # Blink Rate
        tk.Label(perc_blink_section, text="BLINK RATE", font=self.font_title,
                 fg="#888888", bg="#1e1e1e", anchor="w").pack(fill=tk.X, padx=8, pady=(2, 2))
        self.blink_label = tk.Label(perc_blink_section, text="-- bpm", font=self.font_medium,
                                     fg="#00ff00", bg="#1e1e1e")
        self.blink_label.pack(pady=(0, 2))
        self.blink_status = tk.Label(perc_blink_section, text="NORMAL", font=self.font_tiny,
                                      fg="#888888", bg="#1e1e1e")
        self.blink_status.pack(pady=(0, 6))

        # ECG Status
        ecg_status_section = self._make_section(row2, "ECG STATUS")
        ecg_status_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3, 0))
        self.ecg_dot_canvas = tk.Canvas(ecg_status_section, width=30, height=30,
                                         bg="#1e1e1e", highlightthickness=0)
        self.ecg_dot_canvas.pack(pady=(10, 2))
        self.ecg_status_label = tk.Label(ecg_status_section, text="NORMAL", font=self.font_medium,
                                          fg="#00ff00", bg="#1e1e1e")
        self.ecg_status_label.pack(pady=(2, 6))

        # ─── Row 3: ECG Trace ───
        ecg_section = self._make_section(right_col, "ECG TRACE")
        ecg_section.pack(fill=tk.X, pady=6)
        self.ecg_canvas = tk.Canvas(ecg_section, width=380, height=80, bg="black",
                                     highlightthickness=0)
        self.ecg_canvas.pack(padx=8, pady=(0, 8))

        # GPS
        self.gps_label = tk.Label(ecg_section, text="GPS: Waiting...", font=self.font_tiny,
                                   fg="#666666", bg="#1e1e1e")
        self.gps_label.pack(pady=(0, 4))

        # ─── Row 4: Alert State + History ───
        row4 = tk.Frame(right_col, bg="#121212")
        row4.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        # Current Alert + Cancel
        alert_section = self._make_section(row4, "CURRENT ALERT")
        alert_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))

        self.alert_text = tk.Label(alert_section, text="ALL SYSTEMS NORMAL",
                                    font=self.font_medium, fg="#00ff00", bg="#1e1e1e")
        self.alert_text.pack(pady=(4, 2))

        self.countdown_label = tk.Label(alert_section, text="", font=self.font_big,
                                         fg="red", bg="#1e1e1e")
        self.countdown_label.pack()

        self.cancel_btn = tk.Button(alert_section, text="CANCEL ALERT",
                                     font=("Segoe UI", 10, "bold"), bg="#444444", fg="white",
                                     activebackground="#666666", command=self._on_cancel,
                                     state=tk.DISABLED, relief=tk.FLAT)
        self.cancel_btn.pack(pady=(4, 8), ipadx=12, ipady=6)

        # Alert History
        history_section = self._make_section(row4, "ALERT HISTORY")
        history_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3, 0))

        self.history_text = tk.Text(history_section, font=self.font_tiny, fg="#cccccc",
                                     bg="#1a1a1a", height=6, width=30, state=tk.DISABLED,
                                     relief=tk.FLAT, wrap=tk.WORD)
        self.history_text.pack(padx=8, pady=(0, 8), fill=tk.BOTH, expand=True)

    # ─── Event handlers ───

    def _on_close(self):
        self.root.destroy()

    def _on_cancel(self):
        if self.cancel_callback:
            self.cancel_callback()

    # ─── Frame rendering ───

    def set_camera_frame(self, cv2_img):
        if cv2_img is not None:
            cv2_img = cv2.resize(cv2_img, (540, 400))
            rgb = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)

    # ─── Sensor data update ───

    def update_sensors(self, data):
        hr = data.get("hr", 0)
        spo2 = data.get("spo2", 0)
        ecg = data.get("ecg", 0.0)
        hrv = data.get("hrv", 0.0)
        spo2_trend = data.get("spo2_trend", "STABLE")
        ecg_status = data.get("ecg_status", "NORMAL")
        lat = data.get("lat", 0.0)
        lng = data.get("lng", 0.0)

        # HR
        if hr < config.HR_MIN or hr > config.HR_MAX:
            self.hr_label.config(text=f"{hr:.0f}", fg="red")
        elif hr > 100 or hr < 50:
            self.hr_label.config(text=f"{hr:.0f}", fg="orange")
        else:
            self.hr_label.config(text=f"{hr:.0f}", fg="#00ff00")

        # HRV
        hrv_color = "#00ff00"
        if hrv > config.HRV_HIGH_THRESHOLD:
            hrv_color = "red"
        elif hrv < config.HRV_LOW_THRESHOLD:
            hrv_color = "orange"
        self.hrv_label.config(text=f"HRV: {hrv:.1f}", fg=hrv_color)

        # SpO2
        if spo2 <= config.SPO2_CRITICAL:
            self.spo2_label.config(text=f"{spo2:.0f}%", fg="red")
        elif spo2 < config.SPO2_MIN:
            self.spo2_label.config(text=f"{spo2:.0f}%", fg="orange")
        else:
            self.spo2_label.config(text=f"{spo2:.0f}%", fg="#00ff00")

        # SpO2 Trend
        trend_colors = {"STABLE": "#00ff00", "DROPPING": "orange", "CRITICAL": "red"}
        self.spo2_trend_label.config(text=f"Trend: {spo2_trend}",
                                      fg=trend_colors.get(spo2_trend, "#888888"))

        # ECG Status Dot
        self.ecg_dot_canvas.delete("all")
        dot_colors = {"NORMAL": "#00ff00", "IRREGULAR": "red", "MISSED_BEAT": "red"}
        dot_color = dot_colors.get(ecg_status, "#888888")
        self.ecg_dot_canvas.create_oval(5, 5, 25, 25, fill=dot_color, outline="")
        self.ecg_status_label.config(text=ecg_status, fg=dot_color)

        # GPS
        self.gps_label.config(text=f"GPS: {lat:.5f}, {lng:.5f}")

        # ECG Trace
        self.ecg_data.append(ecg)
        self.ecg_data.pop(0)

        self.ecg_canvas.delete("all")
        w = self.ecg_canvas.winfo_width() or 380
        h = self.ecg_canvas.winfo_height() or 80
        dx = w / len(self.ecg_data)

        points = []
        for i, val in enumerate(self.ecg_data):
            x = i * dx
            y = h / 2 - (val * 35)
            points.extend([x, y])

        if len(points) >= 4:
            self.ecg_canvas.create_line(points, fill="#00ff00", width=2, smooth=True)

    # ─── Vision metrics update ───

    def update_vision_metrics(self, perclos, blink_rate):
        # PERCLOS bar
        self.perclos_canvas.delete("all")
        bar_w = self.perclos_canvas.winfo_width() or 180
        bar_h = self.perclos_canvas.winfo_height() or 24
        fill_pct = min(perclos, 1.0)
        fill_w = fill_pct * bar_w

        # Color gradient: green → orange → red
        if perclos < 0.10:
            bar_color = "#00ff00"
        elif perclos < 0.15:
            bar_color = "#ffaa00"
        else:
            bar_color = "#ff0000"

        self.perclos_canvas.create_rectangle(0, 0, fill_w, bar_h, fill=bar_color, outline="")
        self.perclos_text.config(text=f"{perclos * 100:.1f}%", fg=bar_color)

        # Blink rate
        if blink_rate < config.BLINK_LOW:
            blink_color = "orange"
            blink_tag = "LOW"
        elif blink_rate > config.BLINK_HIGH:
            blink_color = "red"
            blink_tag = "HIGH"
        else:
            blink_color = "#00ff00"
            blink_tag = "NORMAL"

        self.blink_label.config(text=f"{blink_rate} bpm", fg=blink_color)
        self.blink_status.config(text=blink_tag, fg=blink_color)

    # ─── Risk score gauge ───

    def update_risk_gauge(self, risk_score, risk_level):
        self.risk_canvas.delete("all")
        cx, cy, r = 60, 60, 50

        # Background arc
        self.risk_canvas.create_arc(cx - r, cy - r, cx + r, cy + r,
                                     start=225, extent=-270, style=tk.ARC,
                                     outline="#333333", width=10)

        # Score arc (max score ~15 for full sweep)
        max_score = 15
        sweep = min(risk_score / max_score, 1.0) * 270

        # Gradient color
        if risk_score <= 4:
            arc_color = "#00ff00"
        elif risk_score <= 6:
            arc_color = "#ffaa00"
        elif risk_score <= 8:
            arc_color = "#ff6600"
        else:
            arc_color = "#ff0000"

        if sweep > 0:
            self.risk_canvas.create_arc(cx - r, cy - r, cx + r, cy + r,
                                         start=225, extent=-sweep, style=tk.ARC,
                                         outline=arc_color, width=10)

        # Score number in center
        self.risk_canvas.create_text(cx, cy, text=str(risk_score),
                                      font=("Segoe UI", 22, "bold"), fill=arc_color)

        # Risk level label
        self.risk_level_label.config(text=risk_level, fg=arc_color)

    # ─── Safety score ───

    def update_safety_score(self, state):
        now = time.time()

        # Decrease score based on alert severity
        penalties = {
            "YAWNING": 1, "DISTRACTED": 2, "HEAD_DROOPING": 2,
            "EYES_CLOSING": 3, "EYES_CLOSED": 5, "MICROSLEEP": 8,
            "DRIVER_ASLEEP": 10, "CARDIAC_EMERGENCY": 15,
            "ACCIDENT": 20, "MEDICAL_SHOCK": 20,
        }

        penalty = penalties.get(state, 0)
        if penalty > 0:
            self.safety_score = max(0, self.safety_score - penalty)
            self.last_clean_time = now
        else:
            # Recover score after 5 minutes of clean driving
            if (now - self.last_clean_time) > 300:
                self.safety_score = min(100, self.safety_score + 1)

        # Display
        if self.safety_score >= 80:
            color = "#00ff00"
        elif self.safety_score >= 50:
            color = "#ffaa00"
        else:
            color = "#ff0000"

        self.safety_label.config(text=str(self.safety_score), fg=color)

    # ─── Alert history ───

    def update_history(self, history_list):
        self.history_text.config(state=tk.NORMAL)
        self.history_text.delete("1.0", tk.END)
        for ts, msg in history_list:
            self.history_text.insert(tk.END, f"{ts} — {msg}\n")
        self.history_text.config(state=tk.DISABLED)
        self.history_text.see(tk.END)

    # ─── State update (colors + flashing) ───

    def update_state(self, state, action, cancel_remaining):
        bg_main = "#121212"
        bg_section = "#1e1e1e"

        if state in ["NORMAL", "ALERT"]:
            self.status_label.config(text="ALERT — ALL CLEAR", fg="#00ff00", bg=bg_section)
            self.alert_text.config(text="ALL SYSTEMS NORMAL", fg="#00ff00")
            self.countdown_label.config(text="")
            self.cancel_btn.config(state=tk.DISABLED)

        elif state in ["YAWNING", "HEAD_DROOPING", "EYES_CLOSING", "DISTRACTED"]:
            self.status_label.config(text=state.replace("_", " "), fg="orange", bg=bg_section)
            self.alert_text.config(text=f"WARNING: {state.replace('_', ' ')}", fg="orange")
            self.countdown_label.config(text="")
            self.cancel_btn.config(state=tk.DISABLED)

        else:
            # Emergency states: flash red
            self.is_flashing = not self.is_flashing
            flash_fg = "white" if self.is_flashing else "#ff4444"

            self.status_label.config(text=state.replace("_", " "), fg=flash_fg, bg=bg_section)
            self.alert_text.config(text=f"EMERGENCY: {state.replace('_', ' ')}", fg=flash_fg)

            if cancel_remaining is not None and cancel_remaining > 0:
                self.countdown_label.config(text=f"{cancel_remaining}s")
                self.cancel_btn.config(state=tk.NORMAL)
            else:
                self.countdown_label.config(text="")
                self.cancel_btn.config(state=tk.DISABLED)

        # Update safety score
        self.update_safety_score(state)

    # ─── Demo stage display ───

    def set_demo_stage(self, text):
        self.demo_label.config(text=text)

    # ─── Main loop ───

    def run_update_loop(self):
        if self.bg_update_callback:
            self.bg_update_callback(self)
        self.root.after(100, self.run_update_loop)

    def mainloop(self):
        self.root.after(100, self.run_update_loop)
        self.root.mainloop()
