from typing import Dict, Optional
from datetime import datetime
import logging

from .schemas import Trade, OrderSide, Position

logger = logging.getLogger(__name__)


class Portfolio:
    def __init__(self, initial_cash: float = 1000000.0):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: Dict[str, Position] = {}
        self.realized_pnl = 0.0
        self.trades_history: list[Trade] = []
        
        logger.info(f"Portfolio initialized with ${initial_cash:,.2f}")
    
    def update_price(self, symbol: str, current_price: float) -> None:
        if symbol in self.positions:
            self.positions[symbol].update_price(current_price)
    
    def update_all_prices(self, prices: Dict[str, float]) -> None:
        for symbol, price in prices.items():
            self.update_price(symbol, price)
    
    def execute_trade(self, trade: Trade) -> bool:
        try:
            if trade.side == OrderSide.BUY:
                return self._execute_buy(trade)
            elif trade.side == OrderSide.SELL:
                return self._execute_sell(trade)
            return False
        except Exception as e:
            logger.error(f"Failed to execute trade {trade.id}: {e}")
            return False
    
    def _execute_buy(self, trade: Trade) -> bool:
        total_cost = (trade.execution_price * trade.quantity) + trade.commission
        
        if total_cost > self.cash:
            logger.warning(f"Insufficient cash for BUY: need ${total_cost:.2f}, have ${self.cash:.2f}")
            return False
        
        self.cash -= total_cost
        
        if trade.symbol in self.positions:
            position = self.positions[trade.symbol]
            total_cost_basis = (position.avg_cost * position.quantity) + (trade.execution_price * trade.quantity)
            position.quantity += trade.quantity
            position.avg_cost = total_cost_basis / position.quantity
            position.current_price = trade.execution_price
            position.unrealized_pnl = (position.current_price - position.avg_cost) * position.quantity
        else:
            self.positions[trade.symbol] = Position(
                symbol=trade.symbol,
                quantity=trade.quantity,
                avg_cost=trade.execution_price,
                current_price=trade.execution_price,
                unrealized_pnl=0.0
            )
        
        self.trades_history.append(trade)
        
        logger.info(
            f"BUY executed: {trade.quantity} {trade.symbol} @ ${trade.execution_price:.2f}, "
            f"New cash: ${self.cash:.2f}"
        )
        return True
    
    def _execute_sell(self, trade: Trade) -> bool:
        if trade.symbol not in self.positions:
            logger.warning(f"No position to sell for {trade.symbol}")
            return False
        
        position = self.positions[trade.symbol]
        
        if trade.quantity > position.quantity:
            logger.warning(
                f"Insufficient shares to sell: trying {trade.quantity}, have {position.quantity}"
            )
            return False
        
        proceeds = (trade.execution_price * trade.quantity) - trade.commission
        self.cash += proceeds
        
        pnl = (trade.execution_price - position.avg_cost) * trade.quantity
        self.realized_pnl += pnl
        
        position.quantity -= trade.quantity
        
        if position.quantity == 0:
            del self.positions[trade.symbol]
        else:
            position.current_price = trade.execution_price
            position.unrealized_pnl = (position.current_price - position.avg_cost) * position.quantity
        
        self.trades_history.append(trade)
        
        logger.info(
            f"SELL executed: {trade.quantity} {trade.symbol} @ ${trade.execution_price:.2f}, "
            f"PnL: ${pnl:.2f}, New cash: ${self.cash:.2f}"
        )
        return True
    
    def get_total_value(self, current_prices: Optional[Dict[str, float]] = None) -> float:
        if current_prices:
            self.update_all_prices(current_prices)
        
        positions_value = sum(
            pos.quantity * pos.current_price
            for pos in self.positions.values()
        )
        
        return self.cash + positions_value
    
    def get_unrealized_pnl(self) -> float:
        return sum(pos.unrealized_pnl for pos in self.positions.values())
    
    def get_total_pnl(self) -> float:
        return self.realized_pnl + self.get_unrealized_pnl()
    
    def get_summary(self) -> dict:
        total_value = self.get_total_value()
        
        return {
            "cash": self.cash,
            "positions_count": len(self.positions),
            "positions_value": sum(p.quantity * p.current_price for p in self.positions.values()),
            "total_value": total_value,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.get_unrealized_pnl(),
            "total_pnl": self.get_total_pnl(),
            "total_return_pct": ((total_value - self.initial_cash) / self.initial_cash) * 100,
            "trades_count": len(self.trades_history)
        }