import sys
import datetime
import pyodbc
import requests
import time
import tkinter as tk
from tkinter import ttk, messagebox
import threading
from config import DB_CONNECTION_STRING
import logging
import os

def setup_logging():
    # Create a formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Setup file handler
    file_handler = logging.FileHandler('crypto_collection.log')
    file_handler.setFormatter(formatter)
    
    # Setup console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Setup logger
    logger = logging.getLogger('CryptoCollector')
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

class CryptoCollector:
    def __init__(self):
        self.coin_ids = {}
        self.logger = setup_logging()
        self.init_database()

    def init_database(self):
        try:
            self.logger.info("Connecting to database...")
            self.conn = pyodbc.connect(DB_CONNECTION_STRING)
            self.cursor = self.conn.cursor()
            
            # Check tables
            self.cursor.execute("SELECT COUNT(*) FROM Coins")
            coins_count = self.cursor.fetchone()[0]
            self.cursor.execute("SELECT COUNT(*) FROM price_data")
            price_count = self.cursor.fetchone()[0]
            
            self.logger.info(f"Database connected. Found {coins_count} coins and {price_count} price records")
            
            # Cache coin IDs
            self.coin_ids = {}
            self.cursor.execute("SELECT coin_id, symbol, full_name FROM Coins")
            for row in self.cursor.fetchall():
                self.coin_ids[row[1]] = {'id': row[0], 'full_name': row[2]}
            
            self.logger.info(f"Cached {len(self.coin_ids)} coin IDs for tracking")
            
        except pyodbc.Error as e:
            self.logger.error(f"Database connection error: {str(e)}")
            sys.exit(1)

    def get_top_coins(self, limit=50):
        self.logger.info(f"Fetching top {limit} coins from CoinGecko...")
        try:
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                'vs_currency': 'usd',
                'order': 'market_cap_desc',
                'per_page': limit,
                'page': 1,
                'sparkline': False
            }
            
            self.logger.info(f"Calling CoinGecko API: {url}")
            response = requests.get(url, params=params)
            self.logger.info(f"API Response Status: {response.status_code}")
            
            if response.status_code == 200:
                coins = response.json()
                self.logger.info(f"Raw API response received: {len(coins)} coins")
                
                # List of stablecoins to exclude
                stablecoins = ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP', 'USDD', 
                              'GUSD', 'USDN', 'USDS', 'WBTC', 'WETH', 'FRAX']
                
                coin_data = []
                for coin in coins:
                    try:
                        symbol = coin['symbol'].upper()
                        name = coin['name']
                        self.logger.info(f"Processing coin: {symbol} ({name})")
                        
                        # Skip if it's a stablecoin
                        if symbol not in stablecoins and not any(s in name.upper() for s in ['USD', 'STABLE']):
                            coin_data.append({
                                'symbol': symbol,
                                'full_name': name,
                                'trading_pair': f"{symbol}/USDT"
                            })
                            self.logger.info(f"Added coin: {symbol} - {name}")
                    except KeyError as ke:
                        self.logger.error(f"Missing key in coin data: {ke}")
                
                self.logger.info(f"Processed {len(coin_data)} non-stablecoin coins")
                return coin_data
            else:
                self.logger.error(f"CoinGecko API error: {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error fetching top coins: {str(e)}")
            return None

    def get_binance_data(self, symbol):
        try:
            ticker = self.exchanges['binance'].fetch_ticker(symbol)
            return {
                'price_usd': ticker['last'] if ticker['last'] is not None else 0,
                'volume_24h': ticker['baseVolume'] if ticker['baseVolume'] is not None else 0,
                'price_change_24h': ticker['percentage'] if ticker.get('percentage') is not None else 0
            }
        except Exception as e:
            self.logger.error(f"Error fetching {symbol} from Binance: {str(e)}")
            return None

    def collect_data(self, is_gui_mode=False):
        thread_conn = pyodbc.connect(DB_CONNECTION_STRING)
        thread_cursor = thread_conn.cursor()
        records_added = 0
        start_time = datetime.datetime.now()
        
        self.logger.info("="*50)
        self.logger.info(f"STARTING NEW COLLECTION CYCLE: {start_time}")
        self.logger.info("="*50)

        try:
            # 1. First get top coins from CoinGecko
            self.logger.info("Step 1: Fetching top coins from CoinGecko...")
            top_coins = self.get_top_coins()
            if not top_coins:
                self.logger.error("Failed to get coin list from CoinGecko. Aborting.")
                return False

            self.logger.info(f"Retrieved {len(top_coins)} coins from CoinGecko")

            # 2. Initialize Binance connection
            self.logger.info("Step 2: Initializing Binance connection...")
            import ccxt
            self.exchanges = {
                'binance': ccxt.binance({
                    'enableRateLimit': True,
                })
            }
            self.logger.info("Binance connection established")

            # 3. Process each coin
            current_time = datetime.datetime.now()
            total_coins = len(top_coins)
            processed_coins = 0
            failed_coins = 0

            self.logger.info("Step 3: Starting price collection from Binance...")
            for coin_info in top_coins:
                try:
                    symbol = coin_info['trading_pair']
                    self.logger.info(f"\nProcessing {symbol} ({processed_coins + 1}/{total_coins})")
                    
                    data = self.get_binance_data(symbol)
                    if data:
                        coin_symbol = coin_info['symbol']
                        cached_coin = self.coin_ids.get(coin_symbol)

                        # Handle new coins
                        if not cached_coin:
                            self.logger.info(f"New coin detected: {coin_symbol} ({coin_info['full_name']})")
                            try:
                                thread_cursor.execute('''
                                    INSERT INTO Coins (symbol, full_name)
                                    VALUES (?, ?)
                                ''', (coin_symbol, coin_info['full_name']))
                                thread_conn.commit()
                                
                                thread_cursor.execute('SELECT @@IDENTITY')
                                new_coin_id = thread_cursor.fetchone()[0]
                                self.coin_ids[coin_symbol] = {
                                    'id': new_coin_id,
                                    'full_name': coin_info['full_name']
                                }
                                cached_coin = self.coin_ids[coin_symbol]
                                self.logger.info(f"Added new coin: {coin_symbol} - {coin_info['full_name']} (ID: {new_coin_id})")
                            except Exception as e:
                                self.logger.error(f"Failed to add new coin {coin_symbol}: {str(e)}")
                                continue

                        # Save price data
                        try:
                            thread_cursor.execute('''
                                INSERT INTO price_data (
                                    timestamp, coin_id, price_usd, 
                                    volume_24h, price_change_24h, data_source
                                )
                                VALUES (?, ?, ?, ?, ?, ?)
                            ''', (
                                current_time,
                                cached_coin['id'],
                                data['price_usd'],
                                data['volume_24h'],
                                data['price_change_24h'],
                                'binance'
                            ))
                            thread_conn.commit()
                            records_added += 1
                            self.logger.info(f"Saved price data for {coin_symbol}:")
                            self.logger.info(f"  Price: ${data['price_usd']:.2f}")
                            self.logger.info(f"  Volume 24h: ${data['volume_24h']:,.2f}")
                            self.logger.info(f"  Change 24h: {data['price_change_24h']:+.2f}%")

                            # Update GUI only if in GUI mode
                            if is_gui_mode and hasattr(self, 'tree'):
                                self.tree.insert("", 0, values=(
                                    current_time.strftime('%Y-%m-%d %H:%M:%S'),
                                    coin_symbol,
                                    f"${data['price_usd']:.2f}",
                                    f"${data['volume_24h']:,.2f}",
                                    f"{data['price_change_24h']:+.2f}%",
                                    'Binance'
                                ), tags=('positive' if data['price_change_24h'] > 0 else 'negative'))

                        except Exception as e:
                            self.logger.error(f"Failed to save price data for {coin_symbol}: {str(e)}")
                            failed_coins += 1
                    else:
                        self.logger.warning(f"No price data received for {symbol}")
                        failed_coins += 1

                    processed_coins += 1
                    if is_gui_mode and hasattr(self, 'status_label'):
                        self.status_label.config(
                            text=f"Processing: {processed_coins}/{total_coins} | Added: {records_added}"
                        )

                except Exception as e:
                    self.logger.error(f"Error processing {symbol}: {str(e)}")
                    failed_coins += 1
                    continue

            # Collection Summary
            end_time = datetime.datetime.now()
            duration = end_time - start_time
            self.logger.info("\n" + "="*50)
            self.logger.info("COLLECTION CYCLE SUMMARY:")
            self.logger.info(f"Start Time: {start_time}")
            self.logger.info(f"End Time: {end_time}")
            self.logger.info(f"Duration: {duration}")
            self.logger.info(f"Coins Processed: {processed_coins}/{total_coins}")
            self.logger.info(f"Records Added: {records_added}")
            self.logger.info(f"Failed Coins: {failed_coins}")
            self.logger.info("="*50 + "\n")

        except Exception as e:
            self.logger.error(f"Critical error in collection cycle: {str(e)}")
            return False

        finally:
            try:
                thread_conn.close()
                self.logger.info("Database connection closed")
            except Exception as e:
                self.logger.error(f"Error closing database connection: {str(e)}")

        return records_added > 0

    def log_to_output(self, message):
        try:
            # Write to output.txt with absolute path
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_message = f"{timestamp} - {message}\n"
            
            # Get current directory and create full path
            current_dir = os.path.dirname(os.path.abspath(__file__))
            output_file = os.path.join(current_dir, 'output.txt')
            
            # Write to file
            with open(output_file, 'a', encoding='utf-8') as f:
                f.write(log_message)
            
            # Print to console
            print(log_message.strip())
            
            # Update GUI status only if running in GUI mode
            if hasattr(self, 'status_label'):
                self.status_label.config(text=message)
                # Force GUI to update
                self.root.update_idletasks()
            
        except Exception as e:
            print(f"Error writing to output.txt: {str(e)}")

class CryptoGUI(CryptoCollector):
    def __init__(self):
        super().__init__()
        self.root = tk.Tk()
        self.root.title("Crypto Price Collector and Analyzer")
        self.is_collecting = False
        self.create_gui()

    def create_gui(self):
        # Create main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Create control frame
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))

        # Add Start/Stop button
        self.collect_button = ttk.Button(
            control_frame, 
            text="Start Collection", 
            command=self.toggle_collection
        )
        self.collect_button.pack(side="left", padx=5)

        # Add status label
        self.status_label = ttk.Label(control_frame, text="Ready")
        self.status_label.pack(side="left", padx=5)

        # Create treeview for data display
        self.tree = ttk.Treeview(main_frame, columns=(
            "timestamp", "symbol", "price", "volume", "change", "source"
        ), show="headings")

        # Configure columns
        self.tree.heading("timestamp", text="Timestamp")
        self.tree.heading("symbol", text="Symbol")
        self.tree.heading("price", text="Price")
        self.tree.heading("volume", text="Volume 24h")
        self.tree.heading("change", text="Change 24h")
        self.tree.heading("source", text="Source")

        # Configure column widths
        self.tree.column("timestamp", width=150)
        self.tree.column("symbol", width=100)
        self.tree.column("price", width=100)
        self.tree.column("volume", width=150)
        self.tree.column("change", width=100)
        self.tree.column("source", width=100)

        # Add treeview to main frame
        self.tree.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure tag colors for price changes
        self.tree.tag_configure('positive', foreground='green')
        self.tree.tag_configure('negative', foreground='red')
        self.tree.tag_configure('neutral', foreground='gray')

        # Add scrollbar
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))
        self.tree.configure(yscrollcommand=scrollbar.set)

    def toggle_collection(self):
        if not self.is_collecting:
            self.is_collecting = True
            self.collect_button.config(text="Stop Collection")
            self.collection_thread = threading.Thread(target=self.collect_continuously)
            self.collection_thread.daemon = True
            self.collection_thread.start()
        else:
            self.is_collecting = False
            self.collect_button.config(text="Start Collection")

    def collect_continuously(self):
        while self.is_collecting:
            success = self.collect_data(is_gui_mode=True)
            if not success:
                self.is_collecting = False
                self.collect_button.config(text="Start Collection")
                messagebox.showerror("Error", "Data collection failed")
                break
            else:
                # Show success message and update button
                self.root.after(0, lambda: messagebox.showinfo("Success", "Data collection completed successfully"))
                self.root.after(0, lambda: self.collect_button.config(text="Start Collection"))
                self.is_collecting = False
            
            if self.is_collecting:  # Only sleep if we're still meant to be collecting
                time.sleep(3600)  # Wait for 1 hour before next collection

def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--service':
        # Run in CLI mode
        collector = CryptoCollector()
        success = collector.collect_data(is_gui_mode=False)
        sys.exit(0 if success else 1)
    else:
        # Run in GUI mode
        app = CryptoGUI()
        app.root.mainloop()

if __name__ == "__main__":
    main()