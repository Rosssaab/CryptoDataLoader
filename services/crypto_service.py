import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import sys
import time
import logging
import os
from pathlib import Path
import schedule
from datetime import datetime
import importlib.util
import threading
import traceback

# Add the parent directory to sys.path to import src modules
parent_dir = str(Path(__file__).resolve().parent.parent)
sys.path.append(parent_dir)

from src.PriceCollector import CryptoCollector
from src.CollectChat import ChatCollector
from src.PricePredictor import PricePredictor

class CryptoAiService(win32serviceutil.ServiceFramework):
    _svc_name_ = "CryptoAiService"
    _svc_display_name_ = "Crypto AI Analysis Service"
    _svc_description_ = "Collects crypto prices, social media sentiment, and makes predictions"

    def __init__(self, args):
        if len(args) > 1 and args[1] == '--debug':
            # Debug mode initialization
            self.running = True
            self.stop_event = None
        else:
            # Normal service initialization
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
            self.running = True
        
        # Setup logging
        log_dir = Path(parent_dir) / 'logs'
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            filename=str(log_dir / 'crypto_service.log'),
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('CryptoAiService')

    def SvcStop(self):
        """Stop the service"""
        self.logger.info('Service stop requested')
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        self.running = False

    def SvcDoRun(self):
        """Main service run method"""
        try:
            self.logger.info('='*50)
            self.logger.info(f'Service starting at {datetime.now()}')
            self.logger.info('='*50)
            
            # Run initial collection on startup
            self.logger.info("Running initial data collection...")
            print("Running initial data collection...") if 'debug' in sys.argv else None
            
            self.run_price_collector()
            self.run_chat_collector()
            self.run_price_predictor()

            # Schedule tasks
            schedule.every(5).minutes.do(self.run_price_collector)
            schedule.every(15).minutes.do(self.run_chat_collector)
            schedule.every().hour.do(self.run_price_predictor)

            self.logger.info("Service scheduled tasks:")
            self.logger.info("- Price collection: every 5 minutes")
            self.logger.info("- Chat collection: every 15 minutes")
            self.logger.info("- Price prediction: every hour")
            
            if 'debug' in sys.argv:
                print("Service scheduled and running. Press Ctrl+C to stop.")

            # Main service loop
            while self.running:
                try:
                    schedule.run_pending()
                    time.sleep(1)
                except Exception as e:
                    self.logger.error(f"Schedule error: {str(e)}")
                    self.logger.error(traceback.format_exc())
                    time.sleep(5)  # Wait before retrying

        except Exception as e:
            self.logger.error(f'Service error: {str(e)}')
            self.logger.error(traceback.format_exc())
            if 'debug' in sys.argv:
                print(f"Service error: {str(e)}")
                traceback.print_exc()

    def run_price_collector(self):
        """Run the price collection task"""
        try:
            start_time = datetime.now()
            self.logger.info(f"Starting price collection at {start_time}")
            
            collector = CryptoCollector()
            success = collector.collect_data(is_gui_mode=False)
            
            end_time = datetime.now()
            duration = end_time - start_time
            
            if success:
                self.logger.info(f"Price collection completed in {duration}")
            else:
                self.logger.error("Price collection failed")
                
        except Exception as e:
            self.logger.error(f"Price collection error: {str(e)}")
            self.logger.error(traceback.format_exc())

    def run_chat_collector(self):
        """Run the chat collection task"""
        try:
            self.logger.info("Starting chat collection")
            # Import NLTK here when needed
            import nltk
            nltk_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'nltk_data')
            nltk.data.path.append(nltk_data_dir)
            
            collector = ChatCollector()
            collector.collect_chat_data()
            self.logger.info("Chat collection completed")
        except Exception as e:
            self.logger.error(f"Chat collection error: {str(e)}", exc_info=True)

    def run_price_predictor(self):
        """Run the price prediction task"""
        try:
            self.logger.info("Starting price prediction")
            predictor = PricePredictor()
            predictor.run_predictions()
            self.logger.info("Price prediction completed")
        except Exception as e:
            self.logger.error(f"Price prediction error: {str(e)}", exc_info=True)

    def debug_run(self):
        """Run method for debug mode without Windows service framework"""
        try:
            print('='*50)
            print(f'Service starting in debug mode at {datetime.now()}')
            print('='*50)
            
            # Run initial collection on startup
            print("Running initial data collection...")
            
            self.run_price_collector()
            self.run_chat_collector()
            self.run_price_predictor()

            # Schedule tasks
            schedule.every(5).minutes.do(self.run_price_collector)
            schedule.every(15).minutes.do(self.run_chat_collector)
            schedule.every().hour.do(self.run_price_predictor)

            print("Service scheduled tasks:")
            print("- Price collection: every 5 minutes")
            print("- Chat collection: every 15 minutes")
            print("- Price prediction: every hour")
            print("\nService running. Press Ctrl+C to stop.")

            # Main service loop
            while True:
                try:
                    schedule.run_pending()
                    time.sleep(1)
                except KeyboardInterrupt:
                    print("\nStopping service...")
                    break
                except Exception as e:
                    print(f"Schedule error: {str(e)}")
                    traceback.print_exc()
                    time.sleep(5)

        except Exception as e:
            print(f'Service error: {str(e)}')
            traceback.print_exc()

def main():
    if len(sys.argv) == 2 and sys.argv[1] == 'debug':
        # Debug mode
        try:
            # Create service instance with minimal args
            args = ['CryptoAiService', '--debug']
            service = CryptoAiService(args)
            print("Starting service in debug mode...")
            service.debug_run()  # Use debug_run instead of SvcDoRun
        except Exception as e:
            print(f"Error in debug mode: {str(e)}")
            traceback.print_exc()
    else:
        # Service mode
        win32serviceutil.HandleCommandLine(CryptoAiService)

if __name__ == '__main__':
    main()