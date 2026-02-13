import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DataLoader:
    def __init__(self, data_dir: Path = Path("./data")):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.historical_dir = self.data_dir / "historical"
        self.historical_dir.mkdir(parents=True, exist_ok=True)
    
    def fetch_sp500_tickers(self, limit: Optional[int] = None) -> list[str]:
        try:
            sp500_table = pd.read_html(
                'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            )[0]
            tickers = sp500_table['Symbol'].tolist()
            
            if limit:
                tickers = tickers[:limit]
            
            logger.info(f"Fetched {len(tickers)} S&P 500 tickers")
            return tickers
        
        except Exception as e:
            logger.error(f"Failed to fetch S&P 500 tickers: {e}")
            return ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
    
    def download_historical_data(
        self,
        symbols: list[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        interval: str = "1d"
    ) -> dict[str, pd.DataFrame]:
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"Downloading data for {len(symbols)} symbols from {start_date} to {end_date}")
        
        data = {}
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(
                    start=start_date,
                    end=end_date,
                    interval=interval
                )
                
                if not df.empty:
                    df.index.name = 'timestamp'
                    df.reset_index(inplace=True)
                    df['symbol'] = symbol
                    
                    file_path = self.historical_dir / f"{symbol}.csv"
                    df.to_csv(file_path, index=False)
                    
                    data[symbol] = df
                    logger.info(f"Downloaded {len(df)} rows for {symbol}")
                else:
                    logger.warning(f"No data retrieved for {symbol}")
            
            except Exception as e:
                logger.error(f"Failed to download {symbol}: {e}")
        
        return data
    
    def load_historical_data(self, symbol: str) -> Optional[pd.DataFrame]:
        file_path = self.historical_dir / f"{symbol}.csv"
        
        if not file_path.exists():
            logger.warning(f"No historical data found for {symbol}")
            return None
        
        try:
            df = pd.read_csv(file_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            logger.info(f"Loaded {len(df)} rows for {symbol}")
            return df
        
        except Exception as e:
            logger.error(f"Failed to load data for {symbol}: {e}")
            return None
    
    def load_all_historical_data(self) -> dict[str, pd.DataFrame]:
        data = {}
        
        for file_path in self.historical_dir.glob("*.csv"):
            symbol = file_path.stem
            df = self.load_historical_data(symbol)
            if df is not None:
                data[symbol] = df
        
        logger.info(f"Loaded data for {len(data)} symbols")
        return data