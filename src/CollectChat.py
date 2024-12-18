import sys
import datetime
import pyodbc
import logging
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from newsapi import NewsApiClient
from config import (
    DB_CONNECTION_STRING, 
    REDDIT_CLIENT_ID, 
    REDDIT_CLIENT_SECRET, 
    TWITTER_BEARER_TOKEN, 
    CRYPTOCOMPARE_API_KEY,
    CRYPTOPANIC_API_KEY,
    CRYPTOPANIC_BASE_URL,
    NEWS_API_URL,
    NEWS_API_KEY
)
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import webbrowser
from tweepy import Client as TwitterClient
import cryptocompare
import requests
import os
import traceback

def setup_logging():
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler = logging.FileHandler('crypto_chat.log')
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger = logging.getLogger('ChatCollector')
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

class ChatCollector:
    def __init__(self):
        self.logger = setup_logging()
        self.init_database()
        self.init_apis()
        self.load_sources()
        self.analyzer = SentimentIntensityAnalyzer()

    def init_database(self):
        try:
            self.conn = pyodbc.connect(DB_CONNECTION_STRING)
            self.cursor = self.conn.cursor()
            self.logger.info("Database connected successfully")
        except Exception as e:
            self.logger.error(f"Database connection error: {str(e)}")
            sys.exit(1)

    def init_apis(self):
        try:
            # Replace Reddit API initialization with requests
            self.reddit_headers = {
                'User-Agent': 'CryptoSentimentBot/1.0'
            }
            
            # Initialize Twitter API
            self.twitter = TwitterClient(bearer_token=TWITTER_BEARER_TOKEN)
            
            # CryptoCompare headers
            self.cryptocompare_headers = {
                'authorization': f'Apikey {CRYPTOCOMPARE_API_KEY}'
            }
            
        except Exception as e:
            self.logger.error(f"API initialization error: {str(e)}")
            sys.exit(1)

    def load_sources(self):
        try:
            self.cursor.execute("SELECT source_id, source_name FROM chat_source")
            self.sources = {row[1]: row[0] for row in self.cursor.fetchall()}
            self.logger.info(f"Loaded {len(self.sources)} chat sources")
        except Exception as e:
            self.logger.error(f"Error loading chat sources: {str(e)}")
            sys.exit(1)

    def get_coins(self):
        try:
            self.cursor.execute("""
                SELECT coin_id, symbol, full_name 
                FROM coins 
                WHERE symbol NOT IN ('USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP', 'USDD', 'GUSD', 'USDN', 'USDS')
            """)
            return [{'coin_id': row[0], 'symbol': row[1], 'full_name': row[2]} 
                   for row in self.cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error getting coins: {str(e)}")
            return []

    def analyze_sentiment(self, text):
        scores = self.analyzer.polarity_scores(text)
        return scores['compound']  # Returns value between -1 and 1

    def collect_news_mentions(self, coin):
        mentions = []
        try:
            self.logger.info(f"Starting News API search for {coin['symbol']}")
            
            search_query = f"{coin['symbol']} OR {coin['full_name']} cryptocurrency"
            
            response = requests.get(
                NEWS_API_URL,
                params={
                    'q': search_query,
                    'apiKey': NEWS_API_KEY,
                    'language': 'en',
                    'sortBy': 'publishedAt'
                }
            )
            
            if response.status_code == 200:
                articles = response.json().get('articles', [])
                self.logger.info(f"Found {len(articles)} news articles")
                
                for article in articles:
                    sentiment_score = self.analyze_sentiment(article['title'])
                    mentions.append({
                        'content': article['title'][:500],
                        'url': article['url'],
                        'sentiment_score': sentiment_score,
                        'sentiment_label': 'Positive' if sentiment_score > 0 else 'Negative' if sentiment_score < 0 else 'Neutral'
                    })
                    self.logger.info(f"Added news mention for {coin['symbol']}")
                
            else:
                self.logger.error(f"News API error: {response.text}")
                
        except Exception as e:
            self.logger.error(f"News API error for {coin['symbol']}: {str(e)}")
            
        self.logger.info(f"News API - Found {len(mentions)} mentions for {coin['symbol']}")
        return mentions

    def collect_reddit_mentions(self, coin):
        mentions = []
        subreddits = ['cryptocurrency', 'CryptoMarkets']
        
        for subreddit in subreddits:
            try:
                url = f"https://www.reddit.com/r/{subreddit}/search.json"
                params = {
                    'q': f"{coin['symbol']} OR {coin['full_name']}",
                    't': 'day',
                    'limit': 100
                }
                response = requests.get(url, headers=self.reddit_headers, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    posts = data.get('data', {}).get('children', [])
                    
                    for post in posts:
                        post_data = post['data']
                        content = f"Title: {post_data['title']}\nContent: {post_data.get('selftext', '')}"
                        
                        if len(content.strip()) < 10:
                            continue

                        sentiment_score = self.analyze_sentiment(content)
                        mentions.append({
                            'source_id': self.sources['Reddit'],
                            'content': content[:500],
                            'url': f"https://reddit.com{post_data['permalink']}",
                            'sentiment_score': sentiment_score,
                            'sentiment_label': 'Positive' if sentiment_score > 0 else 'Negative' if sentiment_score < 0 else 'Neutral'
                        })

            except Exception as e:
                self.logger.error(f"Reddit error for {subreddit}/{coin['symbol']}: {str(e)}")
                continue
        
        return mentions

    def collect_twitter_mentions(self, coin):
        mentions = []
        try:
            self.logger.info(f"Searching Twitter for {coin['symbol']}")
            
            # Add delay to avoid rate limits
            time.sleep(2)
            
            query = f"#{coin['symbol'].lower()} OR #{coin['full_name'].lower()} crypto -is:retweet lang:en"
            tweets = self.twitter.search_recent_tweets(
                query=query,
                max_results=100,
                tweet_fields=['created_at', 'text', 'public_metrics']
            )
            
            if not hasattr(tweets, 'data') or not tweets.data:
                return mentions

            for tweet in tweets.data:
                sentiment_score = self.analyze_sentiment(tweet.text)
                mentions.append({
                    'source_id': self.sources['Twitter'],
                    'content': tweet.text[:500],
                    'sentiment_score': sentiment_score,
                    'sentiment_label': 'Positive' if sentiment_score > 0 else 'Negative' if sentiment_score < 0 else 'Neutral'
                })
                
        except Exception as e:
            self.logger.error(f"Twitter API error for {coin['symbol']}: {str(e)}")
            # Don't let Twitter errors crash the program
            return []
            
        return mentions

    def collect_cryptocompare_mentions(self, coin):
        mentions = []
        try:
            self.logger.info(f"Fetching CryptoCompare news for {coin['symbol']}")
            
            url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
            response = requests.get(url, headers=self.cryptocompare_headers)
            
            if response.status_code == 200:
                data = response.json()
                if 'Data' not in data:
                    return mentions
                
                news = data['Data']
                search_terms = [coin['symbol'].lower()]
                
                coin_news = [
                    n for n in news 
                    if any(term in n['title'].lower() for term in search_terms)
                ]
                
                for article in coin_news:
                    sentiment_score = self.analyze_sentiment(article['title'])
                    mentions.append({
                        'source_id': self.sources['CryptoCompare'],
                        'content': article['title'][:500],
                        'sentiment_score': sentiment_score,
                        'sentiment_label': 'Positive' if sentiment_score > 0 else 'Negative' if sentiment_score < 0 else 'Neutral'
                    })
                    
            else:
                self.logger.error(f"CryptoCompare API error: {response.text}")
                
        except Exception as e:
            self.logger.error(f"CryptoCompare API error for {coin['symbol']}: {str(e)}")
            
        return mentions

    def collect_coingecko_mentions(self, coin):
        mentions = []
        try:
            self.log_to_output(f"Starting CoinGecko search for {coin['symbol']}")
            
            search_url = f"https://api.coingecko.com/api/v3/search?query={coin['symbol']}"
            self.log_to_output(f"CoinGecko search URL: {search_url}")
            
            response = requests.get(search_url)
            self.log_to_output(f"CoinGecko search response status: {response.status_code}")
            
            if response.status_code == 200:
                search_data = response.json()
                coins = search_data.get('coins', [])
                self.log_to_output(f"CoinGecko coins found: {len(coins)}")
                
                if coins:
                    coin_id = coins[0]['id']
                    details_url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
                    details_response = requests.get(details_url)
                    self.log_to_output(f"CoinGecko details response status: {details_response.status_code}")
                    
                    if details_response.status_code == 200:
                        details = details_response.json()
                        if 'description' in details and 'en' in details['description']:
                            content = details['description']['en']
                            sentiment_score = self.analyze_sentiment(content)
                            mentions.append({
                                'source_id': self.sources['CoinGecko'],
                                'content': content[:500],
                                'url': f"https://www.coingecko.com/en/coins/{coin_id}",
                                'sentiment_score': sentiment_score,
                                'sentiment_label': 'Positive' if sentiment_score > 0 else 'Negative' if sentiment_score < 0 else 'Neutral'
                            })
                    
        except Exception as e:
            self.log_to_output(f"CoinGecko API error for {coin['symbol']}: {str(e)}")
        
        self.log_to_output(f"CoinGecko - Found {len(mentions)} mentions for {coin['symbol']}")
        return mentions

    def save_mentions(self, coin, mentions):
        try:
            for mention in mentions:
                self.cursor.execute("""
                    INSERT INTO chat_data (
                        coin_id, source_id, content, sentiment_score, 
                        sentiment_label, url, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, GETDATE())
                """, (
                    mention['coin_id'],
                    mention['source_id'],
                    mention['content'][:500],
                    mention.get('sentiment_score', 0.0),
                    mention.get('sentiment_label', 'NEUTRAL'),
                    mention.get('url', '')
                ))
            self.conn.commit()
            self.logger.info(f"Saved {len(mentions)} mentions successfully")
        except Exception as e:
            self.logger.error(f"Error saving mentions: {str(e)}")
            self.conn.rollback()
            raise

    def collect_mentions_template(self, source_name, coin, collection_function):
        try:
            raw_mentions = collection_function(coin)
            processed_mentions = []
            
            # Debug logging
            self.logger.info(f"Processing {len(raw_mentions)} raw mentions from {source_name}")
            
            for raw_mention in raw_mentions:
                try:
                    processed_mention = {
                        'coin_id': coin['coin_id'],
                        'source_id': self.sources.get(source_name, 3),  # Default to 3 for News
                        'content': raw_mention.get('content', ''),
                        'url': raw_mention.get('url', ''),
                        'sentiment_score': raw_mention.get('sentiment_score', 0.0),
                        'sentiment_label': raw_mention.get('sentiment_label', 'NEUTRAL')
                    }
                    processed_mentions.append(processed_mention)
                except Exception as e:
                    self.logger.error(f"Error processing mention for {source_name}: {str(e)}")
                    continue
                
            self.logger.info(f"Processed {len(processed_mentions)} mentions for {source_name}")
            return processed_mentions
            
        except Exception as e:
            self.logger.error(f"{source_name} API error for {coin['symbol']}: {str(e)}")
            return []

    def collect_chat_data(self):
        try:
            coins = self.get_coins()
            total_coins = len(coins)
            total_mentions = 0

            self.log_to_output("\nStarting data collection...")
            
            for index, coin in enumerate(coins, 1):
                coin_symbol = coin['symbol']
                self.log_to_output(f"\nProcessing {coin_symbol} ({index}/{total_coins})")
                
                mentions = []
                
                sources = {
                    'News API': self.collect_news_mentions,
                    'Reddit': self.collect_reddit_mentions,
                    'Twitter': self.collect_twitter_mentions,
                    'CryptoCompare': self.collect_cryptocompare_mentions,
                    'CoinGecko': self.collect_coingecko_mentions,
                    'CryptoPanic': self.collect_cryptopanic_mentions
                }
                
                for source_name, collection_func in sources.items():
                    try:
                        source_mentions = self.collect_mentions_template(source_name, coin, collection_func)
                        mentions.extend(source_mentions)
                        self.log_to_output(f"{source_name} - {coin_symbol}: Found {len(source_mentions)} mentions")
                        
                        # Update GUI with new mentions
                        for mention in source_mentions:
                            self.update_tree((
                                datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                coin_symbol,
                                source_name,
                                mention['sentiment_label'],
                                mention['content'][:100]
                            ))
                            
                    except Exception as e:
                        self.log_to_output(f"ERROR - {source_name} - {coin_symbol}: {str(e)}")

                if mentions:
                    try:
                        self.save_mentions(coin, mentions)
                        total_mentions += len(mentions)
                        self.log_to_output("Save completed")
                    except Exception as e:
                        self.log_to_output(f"ERROR - Database - {coin_symbol}: {str(e)}")
                
                self.log_to_output(f"Progress: {index}/{total_coins} coins processed")
                self.log_to_output(f"Total mentions collected so far: {total_mentions}")

            self.log_to_output(f"\nData collection completed!")
            self.log_to_output(f"Total mentions collected: {total_mentions}")

            return True

        except Exception as e:
            self.log_to_output(f"ERROR - Collection Process - SYSTEM: {str(e)}")
            return False

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
            if hasattr(self, 'status_label') and hasattr(self, 'root'):
                self.status_label.config(text=message)
                self.root.update_idletasks()
            
        except Exception as e:
            print(f"Error writing to output.txt: {str(e)}")

    def update_tree(self, data):
        # Only update tree if in GUI mode
        if hasattr(self, 'tree'):
            if isinstance(data, tuple) and len(data) == 5:
                self.tree.insert("", 0, values=data)
            else:
                logging.warning(f"Invalid data format for tree update: {data}")

    def collect_mentions(self, coin_symbol):
        """Collect mentions from all sources"""
        all_mentions = []
        
        # Skip News API for now
        # news_mentions = self.collect_news_api_mentions(coin_symbol)
        # all_mentions.extend(news_mentions)
        
        # Collect from other sources
        reddit_mentions = self.collect_reddit_mentions(coin_symbol)
        all_mentions.extend(reddit_mentions)
        
        twitter_mentions = self.collect_twitter_mentions(coin_symbol)
        all_mentions.extend(twitter_mentions)
        
        cryptocompare_mentions = self.collect_cryptocompare_mentions(coin_symbol)
        all_mentions.extend(cryptocompare_mentions)
        
        binance_mentions = self.collect_binance_mentions(coin_symbol)
        all_mentions.extend(binance_mentions)
        
        return all_mentions

    def collect_cryptopanic_mentions(self, coin):
        """Collect mentions from CryptoPanic for a specific coin"""
        mentions = []
        try:
            self.logger.info("=" * 50)
            self.logger.info(f"Starting CryptoPanic API search for {coin['symbol']}")
            
            # Debug the sources dictionary
            self.logger.info(f"Sources dictionary: {self.sources}")
            
            # Updated parameters based on API examples
            params = {
                'auth_token': CRYPTOPANIC_API_KEY,
                'currencies': coin['symbol'],
                'public': 'true',
                'filter': 'hot',  # Get hot/trending news
                'kind': 'news'    # Only get news items
            }
            
            url = f"{CRYPTOPANIC_BASE_URL}posts/"
            
            # Log the full URL with parameters (but mask the API key)
            full_url = requests.Request('GET', url, params=params).prepare().url
            masked_url = full_url.replace(CRYPTOPANIC_API_KEY, 'XXXXX')
            self.logger.info(f"CryptoPanic URL (masked): {masked_url}")
            
            response = requests.get(url, params=params)
            self.logger.info(f"CryptoPanic status code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                self.logger.info(f"CryptoPanic results count: {len(results)}")
                
                for post in results:
                    sentiment_score = self.analyze_sentiment(post['title'])
                    mention = {
                        'source_id': self.sources['CryptoPanic'],
                        'content': post['title'][:500],
                        'url': post['url'],
                        'sentiment_score': sentiment_score,
                        'sentiment_label': 'Positive' if sentiment_score > 0 else 'Negative' if sentiment_score < 0 else 'Neutral'
                    }
                    mentions.append(mention)
                    self.logger.info(f"Added mention for {coin['symbol']}: {post['title'][:100]}...")
                    
            else:
                self.logger.error(f"CryptoPanic error response: {response.text}")
                
        except Exception as e:
            self.logger.error(f"CryptoPanic API error for {coin['symbol']}: {str(e)}")
            traceback.print_exc()
            
        self.logger.info(f"CryptoPanic - Found {len(mentions)} mentions for {coin['symbol']}")
        return mentions

class ChatGUI(ChatCollector):
    def __init__(self):
        super().__init__()
        self.root = tk.Tk()
        self.root.title("Crypto Chat Collector")
        self.is_collecting = False
        self.create_gui()

    def create_gui(self):
        # Create main frame
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Create control frame for collection controls
        collection_frame = ttk.LabelFrame(self.main_frame, text="Data Collection", padding="5")
        collection_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)

        # Add Start/Stop button
        self.collect_button = ttk.Button(
            collection_frame, 
            text="Start Collection", 
            command=self.toggle_collection
        )
        self.collect_button.pack(side="left", padx=5)

        # Add status label
        self.status_label = ttk.Label(collection_frame, text="Ready")
        self.status_label.pack(side="left", padx=5)

        # Create historic view frame
        historic_frame = ttk.LabelFrame(self.main_frame, text="Historic Data View", padding="5")
        historic_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)

        # Coin filter dropdown
        ttk.Label(historic_frame, text="Coin:").pack(side=tk.LEFT, padx=5)
        self.hist_coin_var = tk.StringVar()
        self.hist_coin_dropdown = ttk.Combobox(
            historic_frame, 
            textvariable=self.hist_coin_var,
            state='readonly',
            width=10
        )
        self.update_coin_dropdown()
        self.hist_coin_dropdown.pack(side=tk.LEFT, padx=5)

        # Source filter dropdown
        ttk.Label(historic_frame, text="Source:").pack(side=tk.LEFT, padx=5)
        self.hist_source_var = tk.StringVar()
        self.hist_source_dropdown = ttk.Combobox(
            historic_frame,
            textvariable=self.hist_source_var,
            values=['All'] + list(self.sources.keys()),
            state='readonly',
            width=15
        )
        self.hist_source_dropdown.set('All')
        self.hist_source_dropdown.pack(side=tk.LEFT, padx=5)

        # View button
        self.view_historic_button = ttk.Button(
            historic_frame,
            text="View Historic Data",
            command=self.refresh_historic_data
        )
        self.view_historic_button.pack(side=tk.LEFT, padx=5)

        # Create treeview for data display
        self.tree = ttk.Treeview(self.main_frame, columns=(
            "timestamp", "symbol", "source", "sentiment", "content"
        ), show="headings", height=20)

        # Configure columns
        self.tree.heading("timestamp", text="Timestamp")
        self.tree.heading("symbol", text="Symbol")
        self.tree.heading("source", text="Source")
        self.tree.heading("sentiment", text="Sentiment")
        self.tree.heading("content", text="Content")

        # Configure column widths
        self.tree.column("timestamp", width=150)
        self.tree.column("symbol", width=100)
        self.tree.column("source", width=100)
        self.tree.column("sentiment", width=100)
        self.tree.column("content", width=400)

        # Add treeview to main frame
        self.tree.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure tag colors for sentiment
        self.tree.tag_configure('positive', foreground='green')
        self.tree.tag_configure('negative', foreground='red')
        self.tree.tag_configure('neutral', foreground='gray')

        # Add scrollbar
        scrollbar = ttk.Scrollbar(self.main_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.grid(row=2, column=1, sticky=(tk.N, tk.S))
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Make the content column expandable
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(2, weight=1)

        # Add bindings for automatic refresh when dropdowns change
        self.hist_coin_dropdown.bind('<<ComboboxSelected>>', lambda e: self.refresh_historic_data())
        self.hist_source_dropdown.bind('<<ComboboxSelected>>', lambda e: self.refresh_historic_data())

    def refresh_historic_data(self):
        try:
            # Clear existing items
            for item in self.tree.get_children():
                self.tree.delete(item)

            # Build query based on filters
            query = """
                SELECT TOP 1000 
                    c.symbol, 
                    cs.source_name, 
                    cd.sentiment_label, 
                    cd.content, 
                    cd.timestamp, 
                    cd.url
                FROM chat_data cd
                JOIN coins c ON cd.coin_id = c.coin_id
                JOIN chat_source cs ON cd.source_id = cs.source_id
                WHERE 1=1
            """
            params = []

            # Add coin filter if not 'All'
            if self.hist_coin_var.get() and self.hist_coin_var.get() != 'All':
                query += " AND c.symbol = ?"
                params.append(self.hist_coin_var.get())

            # Add source filter if not 'All'
            if self.hist_source_var.get() and self.hist_source_var.get() != 'All':
                query += " AND cs.source_name = ?"
                params.append(self.hist_source_var.get())

            # Add order by
            query += " ORDER BY cd.timestamp DESC"

            # Execute query
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            
            # Populate tree
            for row in rows:
                self.tree.insert("", 'end', values=(
                    row[4].strftime('%Y-%m-%d %H:%M:%S'),
                    row[0],  # symbol
                    row[1],  # source
                    row[2],  # sentiment
                    row[3][:200]  # content (truncated)
                ), tags=(row[2].lower(),))

            # Update status
            record_count = len(rows)
            status_message = f"Loaded {record_count} records"
            self.status_label.config(text=status_message)
            self.log_to_output(status_message)

        except Exception as e:
            error_msg = f"Failed to load historic data: {str(e)}"
            self.log_to_output(error_msg)
            messagebox.showerror("Error", error_msg)

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
            success = self.collect_chat_data()
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

    def update_coin_dropdown(self):
        try:
            # Get coins from database
            coins = self.get_coins()
            coin_symbols = ['All'] + [coin['symbol'] for coin in coins]
            
            # Update both dropdowns if they exist
            if hasattr(self, 'hist_coin_dropdown'):
                self.hist_coin_dropdown['values'] = coin_symbols
                self.hist_coin_dropdown.set('All')
                
            self.log_to_output(f"Updated coin dropdown with {len(coin_symbols)-1} coins")
        except Exception as e:
            self.log_to_output(f"Error updating coin dropdown: {str(e)}")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--service':
        # Run in CLI mode
        collector = ChatCollector()
        collector.collect_chat_data()
    else:
        # Run in GUI mode
        app = ChatGUI()
        app.root.mainloop()

if __name__ == "__main__":
    main()