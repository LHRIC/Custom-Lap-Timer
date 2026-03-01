import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import serial
import serial.tools.list_ports
import threading
import time
import math
import json

class ESP32LapTimerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ESP32 Lap Timer (Single Button Arm)")
        self.root.geometry("600x850")
        self.root.configure(bg="#1e293b")
        
        # Lap Timer GPS Data
        self.lap_timer_lat = 0.0
        self.lap_timer_lon = 0.0
        self.lap_timer_has_gps_fix = False

        # DAQ GPS Data
        self.daq_lat = 0.0
        self.daq_lon = 0.0
        self.daq_has_gps_fix = False
        
        # Trigger Zones
        self.start_line_lat = None
        self.start_line_lon = None
        self.finish_line_lat = None
        self.finish_line_lon = None
        
        # Logic Flags
        self.is_armed = False        # The "Safety Switch"
        self.is_running = False
        self.trigger_radius = 15.0   # Meters
        self.start_time = 0
        self.cooldown_ts = 0         # Prevents double-triggering
        
        # Serial
        self.serial_port = None
        self.is_connected = False
        self.reading_thread = True 
        
        # Toggle mode variables
        self.toggle_mode = True
        self.toggle_state = True  # first hit will be start timer
        
        self.setup_ui()
        self.update_timer_loop()
        
    def setup_ui(self):
        # --- Header ---
        header = tk.Frame(self.root, bg="#1e293b")
        header.pack(fill=tk.X, padx=20, pady=20)
        
        tk.Label(header, text="LAP TIMER", font=("Arial", 28, "bold"), fg="white", bg="#1e293b").pack(side=tk.LEFT)
        
        # Connection Status
        self.status_lbl = tk.Label(header, text="Disconnected", font=("Arial", 10), fg="#ef4444", bg="#1e293b")
        self.status_lbl.pack(side=tk.RIGHT)

        # --- Connection Controls ---
        conn_frame = tk.Frame(self.root, bg="#1e293b")
        conn_frame.pack(fill=tk.X, padx=20)
        
        self.port_combo = ttk.Combobox(conn_frame, width=20, state="readonly")
        self.port_combo.pack(side=tk.LEFT, padx=5)
        
        tk.Button(conn_frame, text="🔄", command=self.refresh_ports, bg="#475569", fg="white", relief=tk.FLAT).pack(side=tk.LEFT, padx=2)
        
        self.connect_btn = tk.Button(conn_frame, text="Connect", command=self.toggle_connection, bg="#3b82f6", fg="black", font=("Arial", 10, "bold"))
        self.connect_btn.pack(side=tk.LEFT, padx=10)
        self.refresh_ports()

        # --- Main Timer Display ---
        timer_box = tk.Frame(self.root, bg="#0f172a", bd=2, relief=tk.RIDGE)
        timer_box.pack(fill=tk.X, padx=20, pady=20, ipady=15)
        
        self.timer_label = tk.Label(timer_box, text="00:00.00", font=("Courier New", 75, "bold"), fg="#94a3b8", bg="#0f172a")
        self.timer_label.pack()
        
        self.state_label = tk.Label(timer_box, text="SYSTEM IDLE", font=("Arial", 16, "bold"), fg="#64748b", bg="#0f172a")
        self.state_label.pack()

        # --- The Big ARM Button ---
        self.arm_btn = tk.Button(self.root, text="ARM SYSTEM\n(Click to Ready)", command=self.toggle_arm, 
                                 bg="#334155", fg="black", font=("Arial", 16, "bold"), height=3, state=tk.DISABLED)
        self.arm_btn.pack(fill=tk.X, padx=20, pady=10)

        # --- Setup Section ---
        setup_frame = tk.LabelFrame(self.root, text="Track Setup", bg="#1e293b", fg="white", padx=10, pady=10)
        setup_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Lap Timer GPS Live View
        self.lap_timer_gps_label = tk.Label(setup_frame, text="Lap Timer GPS: Waiting...", font=("Courier New", 12), fg="#fbbf24", bg="#1e293b")
        self.lap_timer_gps_label.pack(anchor=tk.W)

        # DAQ GPS Live View
        self.daq_gps_label = tk.Label(setup_frame, text="DAQ GPS: Waiting...", font=("Courier New", 12), fg="#fbbf24", bg="#1e293b")
        self.daq_gps_label.pack(anchor=tk.W)

        # Set Buttons
        btn_row = tk.Frame(setup_frame, bg="#1e293b")
        btn_row.pack(fill=tk.X, pady=10)
        
        tk.Button(btn_row, text="📍 Set START Line", command=self.set_start, bg="#16a34a", fg="black", width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_row, text="🏁 Set FINISH Line", command=self.set_finish, bg="#dc2626", fg="black", width=15).pack(side=tk.RIGHT, padx=5)

        self.start_lbl = tk.Label(setup_frame, text="Start: Not Set", fg="#64748b", bg="#1e293b")
        self.start_lbl.pack(anchor=tk.W)
        self.finish_lbl = tk.Label(setup_frame, text="Finish: Not Set", fg="#64748b", bg="#1e293b")
        self.finish_lbl.pack(anchor=tk.W)

        # Reset
        tk.Button(self.root, text="RESET TIMER", command=self.reset_timer, bg="#dc2626", fg="black", width=20).pack(pady=20)

    # --- Logic ---

    def refresh_ports(self):
        self.port_combo['values'] = [p.device for p in serial.tools.list_ports.comports()]
        if self.port_combo['values']: self.port_combo.current(0)

    def toggle_connection(self):
        if self.is_connected: self.disconnect()
        else: self.connect()

    def connect(self):
        try:
            self.serial_port = serial.Serial(self.port_combo.get(), 9600, timeout=1)
            self.is_connected = True
            self.status_lbl.config(text="Connected", fg="#4ade80")
            self.connect_btn.config(text="Disconnect", bg="#dc2626")
            threading.Thread(target=self.read_loop, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def disconnect(self):
        self.is_connected = False
        if self.serial_port: self.serial_port.close()
        self.status_lbl.config(text="Disconnected", fg="#ef4444")
        self.connect_btn.config(text="Connect", bg="#3b82f6")

    def read_loop(self):
        while self.is_connected and self.reading_thread:
            try:
                if self.serial_port.in_waiting:
                    line = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                    if line and line.startswith("LAP_TIMER:"):
                        self.process_lap_timer_data(line[len("LAP_TIMER:"):])
                    elif line:
                        formatted_data = json.loads(line)
                        self.process_daq_data(formatted_data)
            except: break
            time.sleep(0.01)

    def process_lap_timer_data(self, line):
        try:
            # Expected format: "30.123456,-97.123456"
            parts = line.split(',')
            if len(parts) == 2:
                lat = float(parts[0])
                lon = float(parts[1])
                
                self.lap_timer_lat = lat
                self.lap_timer_lon = lon
                self.lap_timer_has_gps_fix = True
                
                # Update UI
                self.root.after(0, lambda: self.lap_timer_gps_label.config(text=f"Lap Timer GPS: {lat:.6f}, {lon:.6f}"))
                self.check_zones()
        except ValueError: pass
    
    def process_daq_data(self, formatted_data):
        try:
            lat = float(formatted_data.get("lat"))
            lon = float(formatted_data.get("lon"))
            
            self.daq_lat = lat
            self.daq_lon = lon
            self.daq_has_gps_fix = True
            
            # Update UI
            self.root.after(0, lambda: self.daq_gps_label.config(text=f"DAQ GPS: {lat:.6f}, {lon:.6f}"))
            self.check_zones()
        except ValueError: pass

    def toggle_arm(self):
        # The Master Switch Logic
        if self.is_armed:
            # DISARM
            self.is_armed = False
            self.arm_btn.config(text="ARM SYSTEM\n(Click to Ready)", bg="#334155", fg="black")
            self.state_label.config(text="SYSTEM PAUSED", fg="#facc15")
        else:
            # ARM
            if not self.start_line_lat or not self.finish_line_lat:
                messagebox.showwarning("Setup Error", "You must set Start and Finish lines first")
                return
            
            self.is_armed = True
            self.arm_btn.config(text="SYSTEM ARMED\n(Crossing lines will trigger timer)", bg="#ef4444", fg="black")
            
            if self.is_running:
                self.state_label.config(text="LOOKING FOR FINISH...", fg="#ef4444")
            else:
                self.state_label.config(text="LOOKING FOR START...", fg="#4ade80")

    def check_zones(self):
        # 1. Global Safety Check: If not armed, ignore everything
        if not self.is_armed: return
        
        # 2. Cooldown Check (Don't trigger twice in 5 seconds)
        if time.time() - self.cooldown_ts < 5: return

        # 3. Check Start Line (Only if timer is stopped)
        if not self.is_running:
            dist = self.haversine(self.daq_lat, self.daq_lon, self.start_line_lat, self.start_line_lon)
            if dist <= self.trigger_radius:
                self.start_timer()

        # 4. Check Finish Line (Only if timer is running)
        else:
            dist = self.haversine(self.daq_lat, self.daq_lon, self.finish_line_lat, self.finish_line_lon)
            if dist <= self.trigger_radius:
                self.stop_timer()

    def start_timer(self):
        self.is_running = True
        self.start_time = time.time()
        self.cooldown_ts = time.time()
        
        self.root.after(0, lambda: self.timer_label.config(fg="#4ade80")) # Green
        self.root.after(0, lambda: self.state_label.config(text="LAP STARTED", fg="#4ade80"))
        # Note: We stay ARMED so we can catch the finish line

    def stop_timer(self):
        self.is_running = False
        self.is_armed = False # AUTO DISARM for safety
        
        self.root.after(0, lambda: self.timer_label.config(fg="#fbbf24")) # Gold
        self.root.after(0, lambda: self.state_label.config(text="LAP FINISHED (Disarmed)", fg="#fbbf24"))
        self.root.after(0, lambda: self.arm_btn.config(text="ARM SYSTEM\n(Click to Ready)", bg="#334155", fg="black"))

    def reset_timer(self):
        self.is_running = False
        self.is_armed = False
        self.timer_label.config(text="00:00.00", fg="#94a3b8")
        self.state_label.config(text="IDLE", fg="#64748b")
        self.arm_btn.config(text="ARM SYSTEM\n(Click to Ready)", bg="#334155", fg="black")
        
        # Re-enable button if we have coords
        if self.start_line_lat and self.finish_line_lat:
             self.arm_btn.config(state=tk.NORMAL)

    def set_start(self):
        if self.lap_timer_has_gps_fix:
            self.start_line_lat = self.lap_timer_lat
            self.start_line_lon = self.lap_timer_lon
            self.start_lbl.config(text=f"Start: {self.lap_timer_lat:.5f}, {self.lap_timer_lon:.5f}", fg="#4ade80")
            if self.finish_line_lat: self.arm_btn.config(state=tk.NORMAL)

    def set_finish(self):
        if self.lap_timer_has_gps_fix:
            self.finish_line_lat = self.lap_timer_lat
            self.finish_line_lon = self.lap_timer_lon
            self.finish_lbl.config(text=f"Finish: {self.lap_timer_lat:.5f}, {self.lap_timer_lon:.5f}", fg="#ef4444")
            if self.start_line_lat: self.arm_btn.config(state=tk.NORMAL)

    def update_timer_loop(self):
        if self.is_running:
            diff = time.time() - self.start_time
            m = int(diff // 60)
            s = int(diff % 60)
            c = int((diff * 100) % 100)
            self.timer_label.config(text=f"{m:02d}:{s:02d}.{c:02d}")
        self.root.after(30, self.update_timer_loop)

    def haversine(self, lat1, lon1, lat2, lon2):
        R = 6371000
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

if __name__ == "__main__":
    root = tk.Tk()
    app = ESP32LapTimerApp(root)
    root.mainloop()