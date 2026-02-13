from datetime import datetime, timedelta
from typing import Optional, Dict
import pandas as pd
from collections import defaultdict
import asyncio
import logging

from .schemas import Order, Trade, OrderStatus, OrderSide, MarketData
from .message_bus import MessageBus

logger = logging.getLogger(__name__)


class MarketEnvironment:
    def __init__(
        self,
        message_bus: MessageBus,
        historical_data: Dict[str, pd.DataFrame],
        commission_rate: float = 0.001
    ):
        self.message_bus = message_bus
        self.historical_data = historical_data
        self.commission_rate = commission_rate
        
        self.current_time: Optional[datetime] = None
        self.current_prices: Dict[str, float] = {}
        
        self.pending_orders: list[Order] = []
        self.executed_trades: list[Trade] = []
        
        self._prepare_market_data()
    
    def _prepare_market_data(self) -> None:
        self.timeline = []
        
        all_dates = set()
        for symbol, df in self.historical_data.items():
            all_dates.update(df['timestamp'].dt.date.unique())
        
        self.timeline = sorted(list(all_dates))
        
        self.data_by_date: Dict[datetime.date, Dict[str, MarketData]] = defaultdict(dict)
        
        for symbol, df in self.historical_data.items():
            df['date'] = df['timestamp'].dt.date
            for _, row in df.iterrows():
                market_data = MarketData(
                    timestamp=row['timestamp'],
                    symbol=symbol,
                    open=row['Open'],
                    high=row['High'],
                    low=row['Low'],
                    close=row['Close'],
                    volume=int(row['Volume'])
                )
                self.data_by_date[row['date']][symbol] = market_data
        
        logger.info(f"Market prepared: {len(self.timeline)} trading days, {len(self.historical_data)} symbols")
    
    async def advance_time(self, target_date: datetime.date) -> None:
        if target_date not in self.data_by_date:
            logger.warning(f"No market data for {target_date}")
            return
        
        self.current_time = datetime.combine(target_date, datetime.min.time())
        
        day_data = self.data_by_date[target_date]
        for symbol, market_data in day_data.items():
            self.current_prices[symbol] = market_data.close
            
            await self.message_bus.publish(
                "market_data",
                {
                    "type": "market_update",
                    "timestamp": market_data.timestamp.isoformat(),
                    "symbol": symbol,
                    "open": market_data.open,
                    "high": market_data.high,
                    "low": market_data.low,
                    "close": market_data.close,
                    "volume": market_data.volume
                }
            )
        
        logger.info(f"Market advanced to {target_date}, {len(day_data)} symbols updated")
    
    async def submit_order(self, order: Order) -> None:
        if order.status != OrderStatus.APPROVED:
            logger.warning(f"Rejecting non-approved order {order.id}")
            return
        
        self.pending_orders.append(order)
        logger.debug(f"Order {order.id} queued for execution")
    
    async def execute_pending_orders(self) -> None:
        executed_count = 0
        
        for order in self.pending_orders[:]:
            if order.symbol not in self.current_prices:
                logger.warning(f"No price data for {order.symbol}, skipping order {order.id}")
                continue
            
            execution_price = self.current_prices[order.symbol]
            
            if order.price is not None:
                if order.side == OrderSide.BUY and execution_price > order.price:
                    continue
                if order.side == OrderSide.SELL and execution_price < order.price:
                    continue
            
            commission = execution_price * order.quantity * self.commission_rate
            
            trade = Trade(
                id=f"trade_{order.id}",
                timestamp=self.current_time,
                order_id=order.id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                execution_price=execution_price,
                commission=commission,
                trader_id=order.trader_id
            )
            
            self.executed_trades.append(trade)
            self.pending_orders.remove(order)
            
            await self.message_bus.publish(
                "trades",
                {
                    "type": "trade_executed",
                    "trade_id": trade.id,
                    "order_id": trade.order_id,
                    "symbol": trade.symbol,
                    "side": trade.side.value,
                    "quantity": trade.quantity,
                    "execution_price": trade.execution_price,
                    "commission": trade.commission,
                    "timestamp": trade.timestamp.isoformat(),
                    "trader_id": trade.trader_id
                }
            )
            
            executed_count += 1
            logger.info(f"Executed trade {trade.id}: {trade.side.value} {trade.quantity} {trade.symbol} @ {trade.execution_price:.2f}")
        
        if executed_count > 0:
            logger.info(f"Executed {executed_count} orders")
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        return self.current_prices.get(symbol)
    
    def get_all_current_prices(self) -> Dict[str, float]:
        return self.current_prices.copy()