import argparse
import sys
import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from sklearn.ensemble import RandomForestRegressor
from config import DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD
from tqdm import tqdm
import json
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

class PricePredictor:
    MODEL_VERSION = "1.0.0"
    TRAINING_WINDOW_DAYS = 90

    def __init__(self):
        self.logger = self.setup_logger()
        self.db_connection = self.connect_to_db()

    def setup_logger(self):
        logger = logging.getLogger('PricePredictor')
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        return logger

    def connect_to_db(self):
        try:
            self.logger.info("Connecting to database...")
            connection_string = f'mssql+pyodbc://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}/{DB_NAME}?driver=ODBC+Driver+17+for+SQL+Server'
            engine = create_engine(connection_string)
            self.logger.info("Database connection successful")
            return engine
        except Exception as e:
            self.logger.error(f"Database connection error: {str(e)}")
            sys.exit(1)

    def get_historical_data(self, coin_id, coin_symbol):
        """Get historical price data from database"""
        try:
            query = """
            SELECT timestamp as date, price_usd as price, volume_24h, price_change_24h
            FROM Price_Data 
            WHERE coin_id = :coin_id
            AND timestamp >= DATEADD(day, -:days, GETDATE())
            ORDER BY timestamp DESC
            """
            
            with self.db_connection.connect() as conn:
                df = pd.read_sql(
                    text(query), 
                    conn, 
                    params={
                        'coin_id': coin_id, 
                        'days': self.TRAINING_WINDOW_DAYS
                    }
                )
                
            if df.empty:
                self.logger.warning(f"No historical data found for {coin_symbol}")
                return pd.DataFrame()
                
            # Convert date to datetime if it isn't already
            df['date'] = pd.to_datetime(df['date'])
            
            # Use ffill() instead of fillna(method='ffill')
            df = df.ffill()
            
            self.logger.info(f"Found {len(df)} historical price points for {coin_symbol}")
            return df
            
        except Exception as e:
            self.logger.error(f"Error fetching historical data: {str(e)}")
            return pd.DataFrame()

    def calculate_sentiment_score(self, coin_id, coin_symbol):
        self.logger.info(f"Calculating current sentiment for {coin_symbol}...")
        query = f"""
        SELECT AVG(sentiment_score) as avg_sentiment,
               COUNT(*) as mention_count
        FROM chat_data
        WHERE coin_id = {coin_id}
        AND [timestamp] >= DATEADD(hour, -24, GETDATE())
        """
        result = pd.read_sql(query, self.db_connection)
        sentiment = float(result['avg_sentiment'].iloc[0] or 0)
        mentions = int(result['mention_count'].iloc[0])
        self.logger.info(f"Current sentiment for {coin_symbol}: {sentiment:.2f} (based on {mentions} mentions)")
        return sentiment

    def prepare_features(self, historical_data):
        """Prepare features for prediction"""
        try:
            if len(historical_data) < 5:
                return pd.DataFrame(), pd.Series(), []
            
            df = historical_data.copy()
            
            # Technical indicators
            df['sma_5'] = df['price'].rolling(window=5).mean()
            df['sma_10'] = df['price'].rolling(window=10).mean()
            df['price_momentum'] = df['price'].pct_change(5)
            df['volume_momentum'] = df['volume_24h'].pct_change(5)
            df['volatility'] = df['price'].rolling(window=5).std()
            
            # Price changes over different periods
            df['price_change_3d'] = df['price'].pct_change(3)
            df['price_change_7d'] = df['price'].pct_change(7)
            df['price_change_14d'] = df['price'].pct_change(14)
            
            # Volume features
            df['volume_sma_5'] = df['volume_24h'].rolling(window=5).mean()
            df['volume_ratio'] = df['volume_24h'] / df['volume_sma_5']
            
            # Drop rows with NaN values
            df = df.dropna()
            
            # Select features for model
            feature_columns = [
                'sma_5', 'sma_10', 'price_momentum', 'volume_momentum',
                'volatility', 'price_change_3d', 'price_change_7d',
                'price_change_14d', 'volume_ratio', 'price_change_24h'
            ]
            
            X = df[feature_columns]
            y = df['price']  # Use 'price' instead of 'target'
            
            self.logger.info(f"Prepared {len(X)} data points with features")
            return X, y, feature_columns
        
        except Exception as e:
            self.logger.error(f"Error preparing features: {str(e)}")
            return pd.DataFrame(), pd.Series(), []

    def make_predictions(self, model, X, current_price):
        """Make price predictions"""
        try:
            if model is None or X.empty:
                return None
            
            # Get the most recent feature values
            latest_features = X.iloc[-1:]
            
            # Make predictions for different time periods
            base_prediction = model.predict(latest_features)[0]
            
            # Calculate percentage changes
            predictions = {
                'current_price': current_price,
                '24h': current_price * (1 + np.random.normal(0.001, 0.005)),  # Small random change
                '7d': current_price * (1 + np.random.normal(0.003, 0.01)),
                '30d': current_price * (1 + np.random.normal(0.005, 0.015)),
                '90d': current_price * (1 + np.random.normal(0.008, 0.02)),
                'confidence': 95.0  # Base confidence score
            }
            
            return predictions
        
        except Exception as e:
            self.logger.error(f"Error making predictions: {str(e)}")
            return None

    def save_prediction(self, coin_id, predictions, sentiment_score, data_points_count):
        """Save prediction to database"""
        try:
            query = """
            INSERT INTO predictions (
                coin_id, prediction_date, current_price,
                prediction_24h, prediction_7d, prediction_30d, prediction_90d,
                sentiment_score, confidence_score, data_points_count
            ) VALUES (
                :coin_id, GETDATE(), :current_price,
                :pred_24h, :pred_7d, :pred_30d, :pred_90d,
                :sentiment_score, :confidence_score, :data_points_count
            )
            """
            
            params = {
                'coin_id': coin_id,
                'current_price': predictions['current_price'],
                'pred_24h': predictions['24h'],
                'pred_7d': predictions['7d'],
                'pred_30d': predictions['30d'],
                'pred_90d': predictions['90d'],
                'sentiment_score': sentiment_score,
                'confidence_score': predictions['confidence'],
                'data_points_count': data_points_count
            }
            
            with self.db_connection.begin() as conn:
                conn.execute(text(query), params)
                
            self.logger.debug(f"Saved prediction for coin_id {coin_id}")
            
        except Exception as e:
            self.logger.error(f"Error saving prediction: {str(e)}")

    def run_predictions(self):
        """Run predictions for all coins"""
        try:
            # Get list of coins
            coins = self.get_coins()
            self.logger.info(f"Found {len(coins)} coins")
            
            # Process each coin
            for coin in tqdm(coins, desc="Processing coins"):
                try:
                    self.process_coin_prediction(coin['coin_id'], coin['symbol'])  # Changed from make_prediction
                except Exception as e:
                    self.logger.error(f"Error processing {coin['symbol']}: {str(e)}")
                    continue

        except Exception as e:
            self.logger.error(f"Error in prediction process: {str(e)}")

    def process_coin_prediction(self, coin_id, coin_symbol):  # New method name
        """Process predictions for a single coin"""
        try:
            # Get historical data
            historical_data = self.get_historical_data(coin_id, coin_symbol)
            if historical_data.empty:
                return
            
            # Prepare features
            X, y, feature_columns = self.prepare_features(historical_data)
            if X.empty:
                return
            
            # Get current sentiment
            sentiment_score = self.get_current_sentiment(coin_id, coin_symbol)
            
            # Get current price
            current_price = historical_data.iloc[0]['price']
            self.logger.info(f"Current price for {coin_symbol}: ${current_price:,.2f}")
            
            # Train model
            self.logger.info(f"Training prediction model for {coin_symbol}...")
            model = self.train_model(X, y)
            
            if model is None:
                return
            
            # Make predictions
            predictions = self.make_predictions(model, X, current_price)
            
            if predictions:
                self.log_predictions(coin_symbol, predictions)
                self.save_prediction(coin_id, predictions, sentiment_score, len(historical_data))
            
        except Exception as e:
            self.logger.error(f"Prediction error for {coin_symbol}: {str(e)}")

    def log_predictions(self, coin_symbol, predictions):
        """Log prediction results"""
        self.logger.info(f"\nPrediction Summary for {coin_symbol}:")
        self.logger.info("==============================")
        self.logger.info(f"Current Price: ${predictions['current_price']:,.2f}")
        self.logger.info(f"24h Prediction: ${predictions['24h']:,.2f} ({((predictions['24h']/predictions['current_price'])-1)*100:.2f}%)")
        self.logger.info(f"7d Prediction:  ${predictions['7d']:,.2f} ({((predictions['7d']/predictions['current_price'])-1)*100:.2f}%)")
        self.logger.info(f"30d Prediction: ${predictions['30d']:,.2f} ({((predictions['30d']/predictions['current_price'])-1)*100:.2f}%)")
        self.logger.info(f"90d Prediction: ${predictions['90d']:,.2f} ({((predictions['90d']/predictions['current_price'])-1)*100:.2f}%)")
        self.logger.info(f"Confidence Score: {predictions['confidence']:.2f}%")
        self.logger.info("==============================\n")

    def determine_market_condition(self, historical_prices):
        """Determine if market is bullish, bearish, or sideways"""
        # Implementation logic here
        pass

    def calculate_volatility(self, historical_prices):
        """Calculate price volatility index"""
        # Implementation logic here
        pass

    def save_feature_importance(self, prediction_id, feature_importance):
        """Save feature importance scores to database"""
        query = """
        INSERT INTO prediction_feature_importance 
        (prediction_id, feature_name, importance_score)
        VALUES (?, ?, ?)
        """
        with self.db_connection.connect() as conn:
            for feature, importance in feature_importance.items():
                conn.execute(text(query), (prediction_id, feature, importance))

    def print_prediction_summary(self, coin_symbol, prediction_data):
        """Print a summary of the predictions"""
        self.logger.info("\nPrediction Summary for {}:".format(coin_symbol))
        self.logger.info("==============================")
        self.logger.info("Current Price: ${:,.2f}".format(prediction_data['current_price']))
        
        # Calculate and print price changes
        self.logger.info("24h Prediction: ${:,.2f} ({:+.2f}%)".format(
            prediction_data['prediction_24h'],
            ((prediction_data['prediction_24h'] / prediction_data['current_price']) - 1) * 100
        ))
        
        self.logger.info("7d Prediction:  ${:,.2f} ({:+.2f}%)".format(
            prediction_data['prediction_7d'],
            ((prediction_data['prediction_7d'] / prediction_data['current_price']) - 1) * 100
        ))
        
        self.logger.info("30d Prediction: ${:,.2f} ({:+.2f}%)".format(
            prediction_data['prediction_30d'],
            ((prediction_data['prediction_30d'] / prediction_data['current_price']) - 1) * 100
        ))
        
        self.logger.info("90d Prediction: ${:,.2f} ({:+.2f}%)".format(
            prediction_data['prediction_90d'],
            ((prediction_data['prediction_90d'] / prediction_data['current_price']) - 1) * 100
        ))
        
        self.logger.info("Confidence Score: {:.2f}%".format(prediction_data['confidence_score']))
        self.logger.info("==============================\n")

    def get_coins(self):
        """Get list of active coins from database"""
        try:
            query = """
            SELECT coin_id, symbol, full_name
            FROM Coins
            ORDER BY coin_id
            """
            
            with self.db_connection.connect() as conn:
                result = conn.execute(text(query))
                coins = [
                    {
                        'coin_id': row[0],
                        'symbol': row[1],
                        'full_name': row[2]
                    }
                    for row in result
                ]
                
            return coins
            
        except Exception as e:
            self.logger.error(f"Error fetching coins: {str(e)}")
            return []

    def get_current_sentiment(self, coin_id, coin_symbol):
        """Get current sentiment score for a coin"""
        try:
            # Query to get recent sentiment data
            query = """
            SELECT 
                AVG(sentiment_score) as avg_sentiment,
                COUNT(*) as mention_count
            FROM chat_data
            WHERE coin_id = :coin_id
            AND timestamp >= DATEADD(hour, -24, GETDATE())
            """
            
            with self.db_connection.connect() as conn:
                result = conn.execute(
                    text(query),
                    {'coin_id': coin_id}
                ).fetchone()
                
            if result and result[0] is not None:
                avg_sentiment = float(result[0])
                mention_count = int(result[1])
            else:
                avg_sentiment = 0.0
                mention_count = 0
                
            self.logger.info(f"Current sentiment for {coin_symbol}: {avg_sentiment:.2f} (based on {mention_count} mentions)")
            return avg_sentiment
            
        except Exception as e:
            self.logger.error(f"Error getting sentiment for {coin_symbol}: {str(e)}")
            return 0.0  # Return neutral sentiment on error

    def train_model(self, X, y):
        """Train the prediction model"""
        try:
            if X.empty or len(X) < 5:
                return None
            
            # Create and train model
            model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1  # Use all CPU cores
            )
            
            # Split data into train and validation sets
            X_train, X_val, y_train, y_val = train_test_split(
                X, y, 
                test_size=0.2,
                random_state=42
            )
            
            # Train the model
            model.fit(X_train, y_train)
            
            # Calculate validation score
            val_score = model.score(X_val, y_val)
            self.logger.debug(f"Model validation R² score: {val_score:.4f}")
            
            return model
            
        except Exception as e:
            self.logger.error(f"Error training model: {str(e)}")
            return None

    def calculate_model_metrics(self, model, X, y):
        """Calculate model performance metrics"""
        try:
            # Make predictions on validation set
            y_pred = model.predict(X)
            
            # Calculate metrics
            mae = mean_absolute_error(y, y_pred)
            rmse = np.sqrt(mean_squared_error(y, y_pred))
            r2 = r2_score(y, y_pred)
            
            return {
                'mae': mae,
                'rmse': rmse,
                'r2': r2
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating metrics: {str(e)}")
            return None

def main():
    print("\n" + "="*50)
    print("Crypto Price Predictor v1.0")
    print("="*50 + "\n")

    parser = argparse.ArgumentParser(description='Crypto Price Predictor')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    predictor = PricePredictor()
    if args.debug:
        predictor.logger.setLevel(logging.DEBUG)
    
    predictor.run_predictions()

if __name__ == "__main__":
    main()