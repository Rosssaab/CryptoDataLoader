import tkinter as tk
from tkinter import ttk, messagebox
import win32serviceutil
import win32service
import win32event
import win32api
import os
import json
import logging
import traceback

class ServiceControlPanel:
    def __init__(self, root):
        self.root = root
        self.root.title("Crypto AI Service Control Panel")
        self.root.geometry("600x500")  # Made taller for log display
        
        # Setup logging
        self.setup_logging()
        
        # Load current config
        self.config = self.load_config()
        
        self.create_widgets()
        self.update_service_status()

    def setup_logging(self):
        """Setup logging configuration"""
        log_dir = 'C:/PythonApps/CryptoAiAnalyzer/logs'
        os.makedirs(log_dir, exist_ok=True)
        
        self.log_file = f'{log_dir}/service_gui.log'
        logging.basicConfig(
            filename=self.log_file,
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('ServiceGUI')

    def load_config(self):
        """Load service configuration"""
        config_path = 'C:/PythonApps/CryptoAiAnalyzer/config/service_config.json'
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except:
            return {
                'price_interval': 15,
                'chat_interval': 60,
                'prediction_interval': 360
            }

    def save_config(self):
        """Save service configuration"""
        config_path = 'C:/PythonApps/CryptoAiAnalyzer/config/service_config.json'
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        try:
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            messagebox.showinfo("Success", "Configuration saved successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration: {str(e)}")

    def create_widgets(self):
        # Service Status Frame
        status_frame = ttk.LabelFrame(self.root, text="Service Status", padding=10)
        status_frame.pack(fill="x", padx=10, pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Status: Checking...")
        self.status_label.pack(side="left", padx=5)
        
        # Control Buttons Frame
        control_frame = ttk.Frame(status_frame)
        control_frame.pack(side="right", padx=5)
        
        self.start_btn = ttk.Button(control_frame, text="Start", command=self.start_service)
        self.start_btn.pack(side="left", padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="Stop", command=self.stop_service)
        self.stop_btn.pack(side="left", padx=5)
        
        # Settings Frame
        settings_frame = ttk.LabelFrame(self.root, text="Collection Settings", padding=10)
        settings_frame.pack(fill="x", padx=10, pady=5)
        
        # Price Interval
        ttk.Label(settings_frame, text="Price Collection Interval (minutes):").grid(row=0, column=0, padx=5, pady=5)
        self.price_interval = ttk.Entry(settings_frame)
        self.price_interval.insert(0, str(self.config.get('price_interval', 15)))
        self.price_interval.grid(row=0, column=1, padx=5, pady=5)
        
        # Chat Interval
        ttk.Label(settings_frame, text="Chat Collection Interval (minutes):").grid(row=1, column=0, padx=5, pady=5)
        self.chat_interval = ttk.Entry(settings_frame)
        self.chat_interval.insert(0, str(self.config.get('chat_interval', 60)))
        self.chat_interval.grid(row=1, column=1, padx=5, pady=5)
        
        # Prediction Interval
        ttk.Label(settings_frame, text="Prediction Interval (minutes):").grid(row=2, column=0, padx=5, pady=5)
        self.pred_interval = ttk.Entry(settings_frame)
        self.pred_interval.insert(0, str(self.config.get('prediction_interval', 360)))
        self.pred_interval.grid(row=2, column=1, padx=5, pady=5)
        
        # Save Button
        ttk.Button(settings_frame, text="Save Settings", command=self.save_settings).grid(row=3, column=0, columnspan=2, pady=10)
        
        # Log Display
        log_frame = ttk.LabelFrame(self.root, text="Service Logs", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.log_text = tk.Text(log_frame, height=10, wrap=tk.WORD)
        self.log_text.pack(fill="both", expand=True)
        
        # Refresh button
        ttk.Button(self.root, text="Refresh Status", command=self.update_service_status).pack(pady=5)

    def update_service_status(self):
        """Update service status with detailed error reporting"""
        try:
            status = win32serviceutil.QueryServiceStatus("CryptoAiService")[1]
            status_text = {
                win32service.SERVICE_RUNNING: "Running",
                win32service.SERVICE_STOPPED: "Stopped",
                win32service.SERVICE_START_PENDING: "Starting",
                win32service.SERVICE_STOP_PENDING: "Stopping"
            }.get(status, f"Unknown ({status})")
            
            self.status_label.config(text=f"Status: {status_text}")
            self.logger.info(f"Service status updated: {status_text}")
            
            # Update log display
            self.update_log_display()
            
        except Exception as e:
            error_msg = f"Error checking service status: {str(e)}\n{traceback.format_exc()}"
            self.logger.error(error_msg)
            self.status_label.config(text="Status: Error checking status")
            messagebox.showerror("Error", error_msg)

    def start_service(self):
        """Start the service with enhanced error handling"""
        try:
            self.logger.info("Attempting to start service...")
            win32serviceutil.StartService("CryptoAiService")
            self.logger.info("Service start command sent successfully")
            
            # Wait for service to start
            for _ in range(30):  # 30-second timeout
                status = win32serviceutil.QueryServiceStatus("CryptoAiService")[1]
                if status == win32service.SERVICE_RUNNING:
                    self.logger.info("Service started successfully")
                    messagebox.showinfo("Success", "Service started successfully!")
                    self.update_service_status()
                    return
                elif status == win32service.SERVICE_START_PENDING:
                    self.root.after(1000)  # Wait 1 second
                else:
                    raise Exception(f"Unexpected service status: {status}")
                    
            raise TimeoutError("Service failed to start within 30 seconds")
            
        except Exception as e:
            error_msg = f"Failed to start service: {str(e)}\n{traceback.format_exc()}"
            self.logger.error(error_msg)
            messagebox.showerror("Error", error_msg)
            self.update_log_display()

    def update_log_display(self):
        """Update the log display with recent logs"""
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r') as f:
                    # Get last 20 lines
                    lines = f.readlines()[-20:]
                    self.log_text.delete(1.0, tk.END)
                    self.log_text.insert(tk.END, ''.join(lines))
                    
            # Also check service log
            service_log = 'C:/PythonApps/CryptoAiAnalyzer/logs/service.log'
            if os.path.exists(service_log):
                with open(service_log, 'r') as f:
                    lines = f.readlines()[-20:]
                    self.log_text.insert(tk.END, '\nService Log:\n' + ''.join(lines))
                    
        except Exception as e:
            self.logger.error(f"Error updating log display: {str(e)}")

    def stop_service(self):
        """Stop the Windows service"""
        try:
            win32serviceutil.StopService("CryptoAiService")
            messagebox.showinfo("Success", "Service stopped successfully!")
            self.update_service_status()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to stop service: {str(e)}")

    def save_settings(self):
        """Save current settings"""
        try:
            self.config['price_interval'] = int(self.price_interval.get())
            self.config['chat_interval'] = int(self.chat_interval.get())
            self.config['prediction_interval'] = int(self.pred_interval.get())
            
            self.save_config()
            
            # Restart service if running
            if win32serviceutil.QueryServiceStatus("CryptoAiService")[1] == win32service.SERVICE_RUNNING:
                self.stop_service()
                self.start_service()
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ServiceControlPanel(root)
    root.mainloop() 