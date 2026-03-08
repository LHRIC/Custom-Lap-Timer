import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import serial
import serial.tools.list_ports

class ESP32LapTimerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FSAE Lap Timer (Pro Precision)")
        self.root.geometry("650x950")
        self.root.configure(bg="#1e293b")
        
        # FSAE Event Mode ("circuit" or "point2point")
        self.track_mode = tk.StringVar(value="circuit") 
        
        # Lap Timer GPS Data (Used for setting track gates)
        self.lap_timer_lat = 0.0
        self.lap_timer_lon = 0.0
        self.lap_timer_has_gps_fix = False

        # DAQ GPS Data (The Car)
        self.daq_lat = 0.0
        self.daq_lon = 0.0
        self.daq_has_gps_fix = False
        self.prev_daq_pos = None # Stores (lat, lon) from the previous tick
        self.prev_time = None    # Stores the timestamp of the previous tick
        
        # Trigger Gates (Stored as tuples: (lat, lon))
        self.start_left = None
        self.start_right = None
        self.finish_left = None
        self.finish_right = None
        
        # Logic Flags
        self.is_armed = False        
        self.is_running = False
        self.start_time = 0
        self.lap_count = 0           
        
        # Serial
        self.serial_port = None
        self.is_connected = False
        self.reading_thread = True 
        
        self.setup_ui()
        self.update_timer_loop()
        
    def setup_ui(self):
        # --- Header ---
        header = tk.Frame(self.root, bg="#1e293b")
        header.pack(fill=tk.X, padx=20, pady=15)
        
        tk.Label(header, text="LAP TIMER", font=("Arial", 28, "bold"), fg="white", bg="#1e293b").pack(side=tk.LEFT)
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
        timer_box.pack(fill=tk.X, padx=20, pady=15, ipady=15)
        
        self.timer_label = tk.Label(timer_box, text="00:00.000", font=("Courier New", 70, "bold"), fg="#94a3b8", bg="#0f172a")
        self.timer_label.pack()
        self.state_label = tk.Label(timer_box, text="IDLE", font=("Arial", 16, "bold"), fg="#64748b", bg="#0f172a")
        self.state_label.pack()

        # --- Lap Times Table ---
        table_frame = tk.Frame(self.root, bg="#1e293b")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#334155", foreground="white", fieldbackground="#334155", rowheight=25, borderwidth=0)
        style.configure("Treeview.Heading", font=('Arial', 10, 'bold'), background="#0f172a", foreground="white")
        style.map('Treeview', background=[('selected', '#3b82f6')])

        columns = ("lap", "time")
        self.lap_table = ttk.Treeview(table_frame, columns=columns, show="headings", height=5)
        self.lap_table.heading("lap", text="Lap Number")
        self.lap_table.heading("time", text="Lap Time")
        self.lap_table.column("lap", anchor=tk.CENTER, width=100)
        self.lap_table.column("time", anchor=tk.CENTER, width=200)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.lap_table.yview)
        self.lap_table.configure(yscroll=scrollbar.set)
        self.lap_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- The Big ARM Button ---
        self.arm_btn = tk.Button(self.root, text="ARM SYSTEM\n(Requires Gates Set)", command=self.toggle_arm, 
                                 bg="#334155", fg="black", font=("Arial", 16, "bold"), height=2, state=tk.DISABLED)
        self.arm_btn.pack(fill=tk.X, padx=20, pady=5)

        # --- Setup Section (FSAE Modes & Gates) ---
        setup_frame = tk.LabelFrame(self.root, text="Track Setup (Walk to edges and set points)", bg="#1e293b", fg="white", padx=10, pady=5)
        setup_frame.pack(fill=tk.X, padx=20, pady=5)
        
        self.lap_timer_gps_label = tk.Label(setup_frame, text="Lap Timer GPS: Waiting...", font=("Courier New", 10), fg="#fbbf24", bg="#1e293b")
        self.lap_timer_gps_label.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=2)

        self.daq_gps_label = tk.Label(setup_frame, text="DAQ GPS: Waiting...", font=("Courier New", 10), fg="#fbbf24", bg="#1e293b")
        self.daq_gps_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)

        # Event Mode Selector
        mode_frame = tk.Frame(setup_frame, bg="#1e293b")
        mode_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky=tk.W)
        tk.Radiobutton(mode_frame, text="Endurance / Circuit (Same Start & Finish)", variable=self.track_mode, value="circuit", command=self.update_mode_ui, bg="#1e293b", fg="white", selectcolor="#334155").pack(anchor=tk.W)
        tk.Radiobutton(mode_frame, text="Autocross / Accel (Separate Start & Finish)", variable=self.track_mode, value="point2point", command=self.update_mode_ui, bg="#1e293b", fg="white", selectcolor="#334155").pack(anchor=tk.W)

        # Start Gate Buttons & Labels
        tk.Button(setup_frame, text="📍 Set START Left", command=lambda: self.set_point("start_left"), bg="#16a34a", fg="black", width=18).grid(row=3, column=0, pady=5, padx=5)
        self.sl_lbl = tk.Label(setup_frame, text="Not Set", fg="#64748b", bg="#1e293b", font=("Courier New", 8))
        self.sl_lbl.grid(row=4, column=0)

        tk.Button(setup_frame, text="📍 Set START Right", command=lambda: self.set_point("start_right"), bg="#16a34a", fg="black", width=18).grid(row=3, column=1, pady=5, padx=5)
        self.sr_lbl = tk.Label(setup_frame, text="Not Set", fg="#64748b", bg="#1e293b", font=("Courier New", 8))
        self.sr_lbl.grid(row=4, column=1)

        # Finish Gate Buttons & Labels
        self.btn_fin_l = tk.Button(setup_frame, text="🏁 Set FINISH Left", command=lambda: self.set_point("finish_left"), bg="#dc2626", fg="black", width=18)
        self.btn_fin_l.grid(row=5, column=0, pady=5, padx=5)
        self.fl_lbl = tk.Label(setup_frame, text="Not Set", fg="#64748b", bg="#1e293b", font=("Courier New", 8))
        self.fl_lbl.grid(row=6, column=0)

        self.btn_fin_r = tk.Button(setup_frame, text="🏁 Set FINISH Right", command=lambda: self.set_point("finish_right"), bg="#dc2626", fg="black", width=18)
        self.btn_fin_r.grid(row=5, column=1, pady=5, padx=5)
        self.fr_lbl = tk.Label(setup_frame, text="Not Set", fg="#64748b", bg="#1e293b", font=("Courier New", 8))
        self.fr_lbl.grid(row=6, column=1)

        # Reset
        tk.Button(self.root, text="RESET SYSTEM", command=self.reset_system, bg="#dc2626", fg="black", width=20).pack(pady=5)
        
        # Initialize UI state based on default radio button
        self.update_mode_ui()

    # --- Geometry & Math Helpers ---
    def ccw(self, A, B, C):
        """Helper to determine if three points are listed in a counter-clockwise order."""
        return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

    def crossed_line(self, car_prev, car_current, gate_left, gate_right):
        """Returns True if the line segment from the car's last position to current position intersects the gate."""
        A, B = car_prev, car_current
        C, D = gate_left, gate_right
        return self.ccw(A, C, D) != self.ccw(B, C, D) and self.ccw(A, B, C) != self.ccw(A, B, D)

    def get_intersection_fraction(self, car_prev, car_current, gate_left, gate_right):
        """Returns a float between 0.0 and 1.0 representing exactly where the car crossed the gate."""
        x1, y1 = car_prev
        x2, y2 = car_current
        x3, y3 = gate_left
        x4, y4 = gate_right
        
        # Calculate the denominator
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if den == 0:
            return 0.5 # Fallback if lines are perfectly parallel
            
        # Calculate the numerator
        num = (x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)
        
        return num / den

    # --- UI Logic Helpers ---
    def update_mode_ui(self):
        """Enables/Disables the Finish line buttons based on FSAE Event Mode"""
        if self.track_mode.get() == "circuit":
            self.btn_fin_l.config(state=tk.DISABLED, bg="#475569")
            self.btn_fin_r.config(state=tk.DISABLED, bg="#475569")
        else:
            self.btn_fin_l.config(state=tk.NORMAL, bg="#dc2626")
            self.btn_fin_r.config(state=tk.NORMAL, bg="#dc2626")
        self.check_arm_status()

    def check_arm_status(self):
        """Checks if we have the required gates to arm the system"""
        if self.track_mode.get() == "circuit":
            can_arm = bool(self.start_left and self.start_right)
        else:
            can_arm = bool(self.start_left and self.start_right and self.finish_left and self.finish_right)
            
        self.arm_btn.config(state=tk.NORMAL if can_arm else tk.DISABLED)

    # --- Serial Logic ---
    def refresh_ports(self):
        self.port_combo['values'] = [p.device for p in serial.tools.list_ports.comports()]
        if self.port_combo['values']: self.port_combo.current(0)

    def toggle_connection(self):
        if self.is_connected: self.disconnect()
        else: self.connect()

    def connect(self):
        try:
            self.serial_port = serial.Serial(self.port_combo.get(), 115200, timeout=1)
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
            except json.JSONDecodeError: pass
            time.sleep(0.01)

    def process_lap_timer_data(self, line):
        try:
            parts = line.split(',')
            if len(parts) == 2:
                lat, lon = float(parts[0]), float(parts[1])
                self.lap_timer_lat, self.lap_timer_lon = lat, lon
                self.lap_timer_has_gps_fix = True
                self.root.after(0, lambda: self.lap_timer_gps_label.config(text=f"Lap Timer GPS: {lat:.9f}, {lon:.9f}"))
        except ValueError: pass
    
    def process_daq_data(self, formatted_data):
        try:
            lat = float(formatted_data.get("lat")) / 10**7
            lon = float(formatted_data.get("lon")) / 10**7
            self.daq_lat, self.daq_lon = lat, lon
            self.daq_has_gps_fix = True
            self.root.after(0, lambda: self.daq_gps_label.config(text=f"DAQ GPS: {lat:.9f}, {lon:.9f}"))
            self.check_zones()
        except: pass

    # --- Core Application Logic ---
    def set_point(self, point_name):
        if not self.lap_timer_has_gps_fix:
            messagebox.showwarning("No GPS Fix", "Waiting for valid GPS fix from Lap Timer.")
            return

        coords = (self.lap_timer_lat, self.lap_timer_lon)
        setattr(self, point_name, coords)
        
        lbl_map = {"start_left": self.sl_lbl, "start_right": self.sr_lbl, "finish_left": self.fl_lbl, "finish_right": self.fr_lbl}
        lbl_map[point_name].config(text=f"{coords[0]:.9f}, {coords[1]:.9f}", fg="#4ade80")

        self.check_arm_status()

    def toggle_arm(self):
        if self.is_armed:
            self.is_armed = False
            self.is_running = False
            self.arm_btn.config(text="ARM SYSTEM\n(Click to Ready)", bg="#334155", fg="black")
            self.state_label.config(text="SESSION PAUSED", fg="#facc15")
            self.timer_label.config(fg="#94a3b8")
            self.prev_daq_pos = None 
            self.prev_time = None
        else:
            self.is_armed = True
            self.arm_btn.config(text="SYSTEM ARMED\n(Click to Disarm & Stop)", bg="#ef4444", fg="black")
            if self.is_running:
                self.state_label.config(text=f"LAP {self.lap_count} RUNNING...", fg="#4ade80")
            else:
                self.state_label.config(text="LOOKING FOR START GATE...", fg="#4ade80")

    def check_zones(self):
        if not self.is_armed: return
        
        current_daq_pos = (self.daq_lat, self.daq_lon)
        current_time = time.time() # Capture the exact moment we processed this GPS tick

        # Initialize car history so we have a line and a time to draw from
        if not self.prev_daq_pos:
            self.prev_daq_pos = current_daq_pos
            self.prev_time = current_time
            return

        if not self.is_running:
            # Looking for Start Gate
            if self.crossed_line(self.prev_daq_pos, current_daq_pos, self.start_left, self.start_right):
                fraction = self.get_intersection_fraction(self.prev_daq_pos, current_daq_pos, self.start_left, self.start_right)
                exact_start_time = self.prev_time + (fraction * (current_time - self.prev_time))
                self.start_timer(exact_start_time)
        else:
            # Look for the correct Finish Gate based on FSAE Mode
            gate_left = self.start_left if self.track_mode.get() == "circuit" else self.finish_left
            gate_right = self.start_right if self.track_mode.get() == "circuit" else self.finish_right
            
            if self.crossed_line(self.prev_daq_pos, current_daq_pos, gate_left, gate_right):
                fraction = self.get_intersection_fraction(self.prev_daq_pos, current_daq_pos, gate_left, gate_right)
                exact_finish_time = self.prev_time + (fraction * (current_time - self.prev_time))
                self.record_lap(exact_finish_time)

        # Save current position and time for the next loop's calculation
        self.prev_daq_pos = current_daq_pos
        self.prev_time = current_time

    def start_timer(self, exact_start_time):
        self.is_running = True
        self.start_time = exact_start_time 
        self.lap_count += 1
        
        for item in self.lap_table.get_children():
            self.lap_table.delete(item)
            
        self.root.after(0, lambda: self.timer_label.config(fg="#4ade80"))
        self.root.after(0, lambda: self.state_label.config(text=f"LAP {self.lap_count} RUNNING", fg="#4ade80"))

    def record_lap(self, exact_finish_time):
        diff = exact_finish_time - self.start_time
        m = int(diff // 60)
        s = int(diff % 60)
        c = int((diff * 1000) % 1000) # Formatted to thousandths!
        lap_time_str = f"{m:02d}:{s:02d}.{c:03d}"
        
        self.lap_table.insert("", tk.END, values=(f"Lap {self.lap_count}", lap_time_str))
        self.lap_table.yview_moveto(1) 
        
        if self.track_mode.get() == "circuit":
            self.start_time = exact_finish_time  
            self.lap_count += 1
            self.root.after(0, lambda: self.state_label.config(text=f"LAP {self.lap_count} RUNNING", fg="#4ade80"))
        else:
            self.is_running = False
            self.root.after(0, lambda: self.timer_label.config(fg="#fbbf24"))
            self.root.after(0, lambda: self.state_label.config(text="FINISH CROSSED! WAITING FOR START...", fg="#fbbf24"))

    def reset_system(self):
        self.is_running = False
        self.is_armed = False
        self.lap_count = 0
        self.prev_daq_pos = None
        self.prev_time = None
        
        self.timer_label.config(text="00:00.000", fg="#94a3b8")
        self.state_label.config(text="IDLE", fg="#64748b")
        self.arm_btn.config(text="ARM SYSTEM\n(Requires Gates Set)", bg="#334155", fg="black")
        
        for item in self.lap_table.get_children():
            self.lap_table.delete(item)
            
        self.check_arm_status()

    def update_timer_loop(self):
        if self.is_running:
            diff = time.time() - self.start_time
            m = int(diff // 60)
            s = int(diff % 60)
            c = int((diff * 1000) % 1000)
            self.timer_label.config(text=f"{m:02d}:{s:02d}.{c:03d}")
        self.root.after(30, self.update_timer_loop)

if __name__ == "__main__":
    root = tk.Tk()
    app = ESP32LapTimerApp(root)
    root.mainloop()