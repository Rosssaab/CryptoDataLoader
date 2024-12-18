import tkinter as tk
from tkinter import ttk, messagebox
import win32serviceutil
import win32service
import sys
import ctypes
import time
import logging
from pathlib import Path

# Setup logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    filename='logs/monitor_debug.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

class SimpleMonitor(tk.Tk):
    def get_service_status(self):
        try:
            scm = win32service.OpenSCManager(
                None,
                None,
                win32service.SC_MANAGER_CONNECT
            )
            try:
                hs = win32service.OpenService(
                    scm,
                    "CryptoAiService",
                    win32service.SERVICE_QUERY_STATUS
                )
                if not hs:
                    return "Not Installed"
                try:
                    status = win32service.QueryServiceStatus(hs)[1]
                    status_map = {
                        win32service.SERVICE_STOPPED: "Stopped",
                        win32service.SERVICE_START_PENDING: "Starting",
                        win32service.SERVICE_STOP_PENDING: "Stopping",
                        win32service.SERVICE_RUNNING: "Running",
                        win32service.SERVICE_PAUSED: "Paused"
                    }
                    return status_map.get(status, f"Unknown ({status})")
                finally:
                    win32service.CloseServiceHandle(hs)
            finally:
                win32service.CloseServiceHandle(scm)
        except Exception as e:
            logging.error(f"Error getting service status: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"

    def update_status(self):
        status = self.get_service_status()
        self.status_label.config(text=f"Service Status: {status}")
        logging.debug(f"Status updated to: {status}")

    def schedule_update(self):
        self.update_status()
        self.after(5000, self.schedule_update)

    def __init__(self):
        super().__init__()
        logging.debug("Initializing SimpleMonitor")
        
        self.title("Simple Service Monitor")
        self.geometry("400x200")
        
        # Create main frame
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Status label
        self.status_label = ttk.Label(main_frame, text="Checking status...", font=('Arial', 12))
        self.status_label.pack(pady=20)
        
        # Buttons frame
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=20)
        
        # Control buttons
        ttk.Button(btn_frame, text="Start", command=self.start_service).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Stop", command=self.stop_service).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Refresh", command=self.update_status).pack(side=tk.LEFT, padx=5)
        
        # Update status immediately
        self.update_status()
        
        # Schedule regular updates
        self.after(5000, self.schedule_update)
        logging.debug("SimpleMonitor initialization complete")

    def start_service(self):
        try:
            logging.info("Attempting to start service...")
            status = self.get_service_status()
            
            if status == "Not Installed":
                messagebox.showerror("Error", "The service is not installed. Please install it first.")
                return
            
            if status == "Running":
                messagebox.showinfo("Info", "Service is already running")
                return
            
            scm = win32service.OpenSCManager(
                None,
                None,
                win32service.SC_MANAGER_CONNECT | win32service.SC_MANAGER_CREATE_SERVICE
            )
            try:
                hs = win32service.OpenService(
                    scm,
                    "CryptoAiService",
                    win32service.SERVICE_START | win32service.SERVICE_QUERY_STATUS
                )
                try:
                    win32service.StartService(hs, None)
                    logging.info("Service start command sent")
                    
                    # Wait for the service to start
                    for _ in range(30):
                        status = win32service.QueryServiceStatus(hs)[1]
                        if status == win32service.SERVICE_RUNNING:
                            messagebox.showinfo("Success", "Service started successfully")
                            self.update_status()
                            return
                        elif status == win32service.SERVICE_STOPPED:
                            raise Exception("Service failed to start")
                        time.sleep(1)
                    
                    raise Exception("Service start timed out")
                    
                finally:
                    win32service.CloseServiceHandle(hs)
            finally:
                win32service.CloseServiceHandle(scm)
                
        except Exception as e:
            error_msg = f"Failed to start service: {str(e)}"
            logging.error(error_msg, exc_info=True)
            messagebox.showerror("Error", error_msg)

    def stop_service(self):
        try:
            scm = win32service.OpenSCManager(
                None,
                None,
                win32service.SC_MANAGER_CONNECT
            )
            try:
                hs = win32service.OpenService(
                    scm,
                    "CryptoAiService",
                    win32service.SERVICE_STOP | win32service.SERVICE_QUERY_STATUS
                )
                try:
                    status = win32service.QueryServiceStatus(hs)[1]
                    if status == win32service.SERVICE_STOPPED:
                        messagebox.showinfo("Info", "Service is already stopped")
                        return
                    
                    win32service.ControlService(hs, win32service.SERVICE_CONTROL_STOP)
                    
                    for _ in range(30):
                        status = win32service.QueryServiceStatus(hs)[1]
                        if status == win32service.SERVICE_STOPPED:
                            messagebox.showinfo("Success", "Service stopped successfully")
                            self.update_status()
                            return
                        time.sleep(1)
                    
                    raise Exception("Service stop timed out")
                    
                finally:
                    win32service.CloseServiceHandle(hs)
            finally:
                win32service.CloseServiceHandle(scm)
                
        except Exception as e:
            error_msg = f"Failed to stop service: {str(e)}"
            logging.error(error_msg, exc_info=True)
            messagebox.showerror("Error", error_msg)

if __name__ == "__main__":
    try:
        logging.debug("Starting monitor application")
        if not is_admin():
            logging.debug("Not running as admin, requesting elevation")
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        else:
            logging.debug("Running as admin, starting GUI")
            app = SimpleMonitor()
            logging.debug("GUI created, starting mainloop")
            app.mainloop()
    except Exception as e:
        logging.error(f"Error in main: {str(e)}", exc_info=True)
        raise 