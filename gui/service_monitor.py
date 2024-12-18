import tkinter as tk
from tkinter import ttk, messagebox
import win32serviceutil
import win32service
import win32security
import win32api
import win32con
import sys
from pathlib import Path
import json
from datetime import datetime
import threading
import time
import ctypes
import logging

# Configure logging
logging.basicConfig(
    filename='logs/service_monitor.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ServiceMonitor')

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

class ServiceMonitor(tk.Tk):
    def __init__(self):
        if not is_admin():
            messagebox.showerror("Error", "This application needs to be run as Administrator")
            sys.exit(1)
            
        super().__init__()
        
        self.title("Crypto AI Service Monitor")
        self.geometry("800x600")
        
        # Service status history
        self.history_file = Path("logs/service_history.json")
        self.load_history()
        
        self.create_widgets()
        self.update_status()
    
    def create_widgets(self):
        # Status Frame
        status_frame = ttk.LabelFrame(self, text="Service Status", padding=10)
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Status: Checking...", font=('Arial', 12))
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        # Control Buttons
        btn_frame = ttk.Frame(status_frame)
        btn_frame.pack(side=tk.RIGHT)
        
        self.start_btn = ttk.Button(btn_frame, text="Start", command=self.start_service)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="Stop", command=self.stop_service)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.restart_btn = ttk.Button(btn_frame, text="Restart", command=self.restart_service)
        self.restart_btn.pack(side=tk.LEFT, padx=5)
        
        # History Frame
        history_frame = ttk.LabelFrame(self, text="Service History", padding=10)
        history_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create Treeview
        columns = ('timestamp', 'status', 'message')
        self.history_tree = ttk.Treeview(history_frame, columns=columns, show='headings')
        
        # Define headings
        self.history_tree.heading('timestamp', text='Timestamp')
        self.history_tree.heading('status', text='Status')
        self.history_tree.heading('message', text='Message')
        
        # Column widths
        self.history_tree.column('timestamp', width=150)
        self.history_tree.column('status', width=100)
        self.history_tree.column('message', width=500)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack elements
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Load history
        self.update_history_display()
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self.monitor_service, daemon=True)
        self.monitor_thread.start()
    
    def load_history(self):
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
            else:
                self.history = []
        except Exception as e:
            print(f"Error loading history: {e}")
            self.history = []
    
    def save_history(self):
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f)
        except Exception as e:
            print(f"Error saving history: {e}")
    
    def add_history_entry(self, status, message):
        entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': status,
            'message': message
        }
        self.history.append(entry)
        if len(self.history) > 1000:  # Keep last 1000 entries
            self.history = self.history[-1000:]
        self.save_history()
        self.update_history_display()
    
    def update_history_display(self):
        # Clear existing items
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        
        # Add history items
        for entry in reversed(self.history):  # Show newest first
            self.history_tree.insert('', 'end', values=(
                entry['timestamp'],
                entry['status'],
                entry['message']
            ))
    
    def get_service_status(self):
        try:
            # Get service handle with full access
            scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
            try:
                service = win32service.OpenService(scm, "CryptoAiService", win32service.SERVICE_QUERY_STATUS)
                try:
                    status_info = win32service.QueryServiceStatusEx(service)
                    status = status_info["CurrentState"]
                    
                    status_map = {
                        win32service.SERVICE_STOPPED: "Stopped",
                        win32service.SERVICE_START_PENDING: "Starting",
                        win32service.SERVICE_STOP_PENDING: "Stopping",
                        win32service.SERVICE_RUNNING: "Running",
                        win32service.SERVICE_PAUSED: "Paused"
                    }
                    
                    status_text = status_map.get(status, f"Unknown ({status})")
                    logger.debug(f"Service status query: {status_text}")
                    return status_text
                    
                finally:
                    win32service.CloseServiceHandle(service)
            finally:
                win32service.CloseServiceHandle(scm)
            
        except Exception as e:
            error_msg = f"Error querying service status: {str(e)}"
            logger.error(error_msg)
            return "Error"
    
    def update_status(self):
        status = self.get_service_status()
        self.status_label.config(text=f"Status: {status}")
        
        # Update button states
        is_running = status == "Running"
        self.start_btn["state"] = "disabled" if is_running else "normal"
        self.stop_btn["state"] = "normal" if is_running else "disabled"
        self.restart_btn["state"] = "normal" if is_running else "disabled"
    
    def monitor_service(self):
        last_status = None
        while True:
            try:
                current_status = self.get_service_status()
                if current_status != last_status:
                    self.add_history_entry(
                        "Status", 
                        f"Service status changed to {current_status}"
                    )
                    last_status = current_status
                
                # Update GUI
                self.after(0, self.update_status)
                
            except Exception as e:
                logger.error(f"Monitor error: {str(e)}")
                
            time.sleep(5)  # Check every 5 seconds
    
    def start_service(self):
        try:
            # First check if service is already running
            current_status = self.get_service_status()
            if current_status == "Running":
                self.add_history_entry("Info", "Service is already running")
                return
            
            # Get service handle with full access
            scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
            try:
                service = win32service.OpenService(scm, "CryptoAiService", win32service.SERVICE_ALL_ACCESS)
                try:
                    win32service.StartService(service, None)
                    self.add_history_entry("Action", "Service start requested")
                    
                    # Wait for service to start (up to 30 seconds)
                    for _ in range(30):
                        status = win32service.QueryServiceStatus(service)[1]
                        if status == win32service.SERVICE_RUNNING:
                            self.add_history_entry("Success", "Service started successfully")
                            break
                        time.sleep(1)
                        
                finally:
                    win32service.CloseServiceHandle(service)
            finally:
                win32service.CloseServiceHandle(scm)
            
        except Exception as e:
            error_msg = f"Failed to start service: {str(e)}"
            self.add_history_entry("Error", error_msg)
            messagebox.showerror("Error", error_msg)
    
    def stop_service(self):
        try:
            scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
            service = win32service.OpenService(scm, "CryptoAiService", win32service.SERVICE_ALL_ACCESS)
            
            if service:
                win32service.ControlService(service, win32service.SERVICE_CONTROL_STOP)
                self.add_history_entry("Action", "Service stop requested")
                win32service.CloseServiceHandle(service)
            win32service.CloseServiceHandle(scm)
            
        except Exception as e:
            error_msg = str(e)
            self.add_history_entry("Error", f"Failed to stop service: {error_msg}")
            messagebox.showerror("Error", f"Failed to stop service:\n{error_msg}")
    
    def restart_service(self):
        try:
            self.stop_service()
            time.sleep(2)  # Wait for service to stop
            self.start_service()
            self.add_history_entry("Action", "Service restart requested")
        except Exception as e:
            error_msg = str(e)
            self.add_history_entry("Error", f"Failed to restart service: {error_msg}")
            messagebox.showerror("Error", f"Failed to restart service:\n{error_msg}")

if __name__ == "__main__":
    # Create shortcut that runs as admin
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
    else:
        app = ServiceMonitor()
        app.mainloop() 