import tkinter as tk
from tkinter import ttk, scrolledtext
import serial
import serial.tools.list_ports
import threading
import time

class ESP32TimerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ESP32 Timer")
        self.root.geometry("600x700")
        self.root.configure(bg="#1e293b")
        
        # Timer variables
        self.time_ms = 0
        self.is_running = False
        self.timer_thread = None
        
        # Serial variables
        self.serial_port = None
        self.is_connected = False
        self.read_thread = None
        self.running = True
        
        self.setup_ui()
        self.update_timer_display()
        
    def setup_ui(self):
        # Main container
        main_frame = tk.Frame(self.root, bg="#1e293b")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Header
        header_frame = tk.Frame(main_frame, bg="#1e293b")
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        title_label = tk.Label(
            header_frame,
            text="⏰ ESP32 Timer",
            font=("Arial", 24, "bold"),
            fg="#a78bfa",
            bg="#1e293b"
        )
        title_label.pack(side=tk.LEFT)
        
        # Connection frame
        conn_frame = tk.Frame(header_frame, bg="#1e293b")
        conn_frame.pack(side=tk.RIGHT)
        
        self.status_label = tk.Label(
            conn_frame,
            text="● Disconnected",
            font=("Arial", 12),
            fg="#64748b",
            bg="#1e293b"
        )
        self.status_label.pack(side=tk.TOP)
        
        # COM Port selection
        port_frame = tk.Frame(conn_frame, bg="#1e293b")
        port_frame.pack(side=tk.TOP, pady=5)
        
        tk.Label(port_frame, text="Port:", fg="white", bg="#1e293b").pack(side=tk.LEFT, padx=5)
        
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(
            port_frame,
            textvariable=self.port_var,
            width=12,
            state="readonly"
        )
        self.port_combo.pack(side=tk.LEFT, padx=5)
        self.refresh_ports()
        
        refresh_btn = tk.Button(
            port_frame,
            text="🔄",
            command=self.refresh_ports,
            bg="#475569",
            fg="white",
            relief=tk.FLAT,
            padx=5
        )
        refresh_btn.pack(side=tk.LEFT)
        
        self.connect_btn = tk.Button(
            conn_frame,
            text="Connect",
            command=self.toggle_connection,
            bg="#7e22ce",
            fg="white",
            font=("Arial", 12, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=5,
            cursor="hand2"
        )
        self.connect_btn.pack(side=tk.TOP, pady=5)
        
        # Timer display
        timer_frame = tk.Frame(main_frame, bg="#0f172a", relief=tk.RIDGE, bd=2)
        timer_frame.pack(fill=tk.X, pady=20, ipady=40)
        
        self.timer_label = tk.Label(
            timer_frame,
            text="00:00.00",
            font=("Courier New", 60, "bold"),
            fg="#a78bfa",
            bg="#0f172a"
        )
        self.timer_label.pack()
        
        # Control buttons
        controls_frame = tk.Frame(main_frame, bg="#1e293b")
        controls_frame.pack(fill=tk.X, pady=20)
        
        self.start_btn = tk.Button(
            controls_frame,
            text="▶ Start",
            command=self.start_timer,
            bg="#16a34a",
            fg="white",
            font=("Arial", 14, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=15,
            cursor="hand2"
        )
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.pause_btn = tk.Button(
            controls_frame,
            text="⏸ Pause",
            command=self.pause_timer,
            bg="#ca8a04",
            fg="white",
            font=("Arial", 14, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=15,
            cursor="hand2",
            state=tk.DISABLED
        )
        self.pause_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.reset_btn = tk.Button(
            controls_frame,
            text="↺ Reset",
            command=self.reset_timer,
            bg="#dc2626",
            fg="white",
            font=("Arial", 14, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=15,
            cursor="hand2"
        )
        self.reset_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Serial data display
        serial_frame = tk.Frame(main_frame, bg="#0f172a", relief=tk.RIDGE, bd=2)
        serial_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        tk.Label(
            serial_frame,
            text="Serial Data:",
            font=("Arial", 12, "bold"),
            fg="#94a3b8",
            bg="#0f172a"
        ).pack(anchor=tk.W, padx=10, pady=(10, 5))
        
        self.serial_text = scrolledtext.ScrolledText(
            serial_frame,
            height=8,
            font=("Courier New", 10),
            bg="#0f172a",
            fg="#4ade80",
            relief=tk.FLAT,
            wrap=tk.WORD
        )
        self.serial_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Instructions
        info_frame = tk.Frame(main_frame, bg="#0f172a", relief=tk.RIDGE, bd=2)
        info_frame.pack(fill=tk.X, pady=10)
        
        info_text = """ESP32 Commands:
• Send "START" to start the timer
• Send "STOP" to pause the timer
• Send "RESET" to reset the timer
• Baud rate: 115200"""
        
        tk.Label(
            info_frame,
            text=info_text,
            font=("Arial", 10),
            fg="#94a3b8",
            bg="#0f172a",
            justify=tk.LEFT
        ).pack(anchor=tk.W, padx=15, pady=15)
    
    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        port_list = [port.device for port in ports]
        self.port_combo['values'] = port_list
        if port_list:
            self.port_combo.current(0)
    
    def toggle_connection(self):
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        port_name = self.port_var.get()
        if not port_name:
            self.log_serial("No port selected!")
            return
        
        try:
            self.serial_port = serial.Serial(port_name, 115200, timeout=1)
            self.is_connected = True
            self.status_label.config(text="● Connected", fg="#4ade80")
            self.connect_btn.config(text="Disconnect", bg="#dc2626")
            self.log_serial(f"Connected to {port_name}")
            
            # Start reading thread
            self.read_thread = threading.Thread(target=self.read_serial, daemon=True)
            self.read_thread.start()
        except Exception as e:
            self.log_serial(f"Connection failed: {str(e)}")
    
    def disconnect(self):
        self.is_connected = False
        if self.serial_port:
            self.serial_port.close()
            self.serial_port = None
        self.status_label.config(text="● Disconnected", fg="#64748b")
        self.connect_btn.config(text="Connect", bg="#7e22ce")
        self.log_serial("Disconnected")
    
    def read_serial(self):
        while self.is_connected and self.running:
            try:
                if self.serial_port and self.serial_port.in_waiting:
                    data = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                    if data:
                        self.log_serial(f"Received: {data}")
                        self.process_command(data)
            except Exception as e:
                self.log_serial(f"Read error: {str(e)}")
                break
            time.sleep(0.01)
    
    def process_command(self, cmd):
        cmd = cmd.upper().strip()
        if cmd == "START":
            self.root.after(0, self.start_timer)
        elif cmd == "STOP":
            self.root.after(0, self.pause_timer)
        elif cmd == "RESET":
            self.root.after(0, self.reset_timer)
    
    def log_serial(self, message):
        self.serial_text.insert(tk.END, message + "\n")
        self.serial_text.see(tk.END)
    
    def start_timer(self):
        if not self.is_running:
            self.is_running = True
            self.start_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.NORMAL)
            self.timer_thread = threading.Thread(target=self.run_timer, daemon=True)
            self.timer_thread.start()
    
    def pause_timer(self):
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED)
    
    def reset_timer(self):
        self.is_running = False
        self.time_ms = 0
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED)
        self.update_timer_display()
    
    def run_timer(self):
        while self.is_running:
            time.sleep(0.01)
            self.time_ms += 10
            self.root.after(0, self.update_timer_display)
    
    def update_timer_display(self):
        minutes = self.time_ms // 60000
        seconds = (self.time_ms % 60000) // 1000
        centiseconds = (self.time_ms % 1000) // 10
        time_str = f"{minutes:02d}:{seconds:02d}.{centiseconds:02d}"
        self.timer_label.config(text=time_str)
    
    def on_closing(self):
        self.running = False
        if self.is_connected:
            self.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ESP32TimerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()