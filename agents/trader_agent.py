import asyncio
import random
from datetime import datetime
from typing import Optional, Dict
import logging

from .base_agent import BaseAgent
from core.schemas import Order, OrderSide, OrderStatus, SignalType
from core.message_bus import MessageBus

logger = logging.getLogger(__name__)


class TraderAgent(BaseAgent):
    def __init__(
        self,
        agent_id: str,
        message_bus: MessageBus,
        symbols: list[str],
        initial_cash: float = 100000.0,
        max_position_value: float = 20000.0,
        log_level: str = "INFO"
    ):
        super().__init__(agent_id, message_bus, log_level)
        self.symbols = symbols
        self.cash = initial_cash
        self.max_position_value = max_position_value
        
        self.positions: Dict[str, int] = {symbol: 0 for symbol in symbols}
        self.current_prices: Dict[str, float] = {}
        
        self.pending_orders: list[Order] = []
        self.order_count = 0
    
    async def _setup_subscriptions(self) -> None:
        await self.subscribe("signals", self._on_signal)
        await self.subscribe("market_data", self._on_market_update)
        await self.subscribe("risk_decisions", self._on_risk_decision)
        await self.subscribe("trades", self._on_trade_executed)
    
    async def _run(self) -> None:
        while self._running:
            await asyncio.sleep(1)
    
    async def _on_market_update(self, message: dict) -> None:
        if message.get("type") != "market_update":
            return
        
        symbol = message.get("symbol")
        close_price = message.get("close")
        
        if symbol and close_price:
            self.current_prices[symbol] = close_price
    
    async def _on_signal(self, message: dict) -> None:
        if message.get("type") != "signal":
            return
        
        symbol = message.get("symbol")
        if symbol not in self.symbols:
            return
        
        signal_type = message.get("signal_type")
        confidence = message.get("confidence", 0.0)
        signal_id = message.get("signal_id")
        
        if confidence < 0.6:
            self.logger.debug(f"Ignoring low confidence signal", confidence=confidence)
            return
        
        if symbol not in self.current_prices:
            self.logger.warning(f"No price data for {symbol}, cannot trade")
            return
        
        current_price = self.current_prices[symbol]
        current_position = self.positions.get(symbol, 0)
        
        if signal_type == "BULLISH" and confidence > 0.65:
            position_value = current_position * current_price
            if position_value < self.max_position_value:
                await self._place_buy_order(symbol, current_price, signal_id)
        
        elif signal_type == "BEARISH" and confidence > 0.65:
            if current_position > 0:
                await self._place_sell_order(symbol, current_price, signal_id)
    
    async def _place_buy_order(
        self, 
        symbol: str, 
        current_price: float,
        signal_id: Optional[str] = None
    ) -> None:
        available_capital = min(self.cash * 0.1, self.max_position_value * 0.3)
        
        if available_capital < current_price:
            self.logger.debug(f"Insufficient cash for {symbol}")
            return
        
        quantity = int(available_capital / current_price)
        if quantity < 1:
            return
        
        self.order_count += 1
        order = Order(
            id=f"{self.agent_id}_order_{self.order_count}",
            timestamp=datetime.utcnow(),
            trader_id=self.agent_id,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            price=current_price * 1.01,
            status=OrderStatus.PENDING,
            signal_id=signal_id
        )
        
        self.pending_orders.append(order)
        
        await self.publish(
            "orders",
            {
                "type": "order_request",
                "order_id": order.id,
                "timestamp": order.timestamp.isoformat(),
                "trader_id": order.trader_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "price": order.price,
                "signal_id": signal_id
            }
        )
        
        self.logger.info(
            f"Placed BUY order",
            order_id=order.id,
            symbol=symbol,
            quantity=quantity,
            price=f"{current_price:.2f}"
        )
    
    async def _place_sell_order(
        self, 
        symbol: str, 
        current_price: float,
        signal_id: Optional[str] = None
    ) -> None:
        current_position = self.positions.get(symbol, 0)
        if current_position <= 0:
            return
        
        quantity = max(1, int(current_position * 0.5))
        
        self.order_count += 1
        order = Order(
            id=f"{self.agent_id}_order_{self.order_count}",
            timestamp=datetime.utcnow(),
            trader_id=self.agent_id,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            price=current_price * 0.99,
            status=OrderStatus.PENDING,
            signal_id=signal_id
        )
        
        self.pending_orders.append(order)
        
        await self.publish(
            "orders",
            {
                "type": "order_request",
                "order_id": order.id,
                "timestamp": order.timestamp.isoformat(),
                "trader_id": order.trader_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "price": order.price,
                "signal_id": signal_id
            }
        )
        
        self.logger.info(
            f"Placed SELL order",
            order_id=order.id,
            symbol=symbol,
            quantity=quantity,
            price=f"{current_price:.2f}"
        )
    
    async def _on_risk_decision(self, message: dict) -> None:
        if message.get("type") != "risk_decision":
            return
        
        order_id = message.get("order_id")
        approved = message.get("approved", False)
        
        matching_order = next(
            (o for o in self.pending_orders if o.id == order_id),
            None
        )
        
        if not matching_order:
            return
        
        if approved:
            matching_order.status = OrderStatus.APPROVED
            
            await self.publish(
                "approved_orders",
                {
                    "type": "order_approved",
                    "order_id": matching_order.id,
                    "trader_id": matching_order.trader_id,
                    "symbol": matching_order.symbol,
                    "side": matching_order.side.value,
                    "quantity": matching_order.quantity,
                    "price": matching_order.price,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
            self.logger.info(f"Order approved", order_id=order_id)
        else:
            matching_order.status = OrderStatus.REJECTED
            matching_order.rejection_reason = message.get("reason", "Unknown")
            self.pending_orders.remove(matching_order)
            
            self.logger.warning(
                f"Order rejected",
                order_id=order_id,
                reason=matching_order.rejection_reason
            )
    
    async def _on_trade_executed(self, message: dict) -> None:
        if message.get("type") != "trade_executed":
            return
        
        order_id = message.get("order_id")
        
        matching_order = next(
            (o for o in self.pending_orders if o.id == order_id),
            None
        )
        
        if not matching_order:
            return
        
        symbol = message.get("symbol")
        side = message.get("side")
        quantity = message.get("quantity")
        execution_price = message.get("execution_price")
        commission = message.get("commission", 0.0)
        
        if side == "BUY":
            self.positions[symbol] = self.positions.get(symbol, 0) + quantity
            self.cash -= (execution_price * quantity + commission)
        elif side == "SELL":
            self.positions[symbol] = self.positions.get(symbol, 0) - quantity
            self.cash += (execution_price * quantity - commission)
        
        self.pending_orders.remove(matching_order)
        
        self.logger.info(
            f"Trade executed",
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=f"{execution_price:.2f}",
            new_cash=f"{self.cash:.2f}",
            new_position=self.positions[symbol]
        )
    
    def get_portfolio_value(self) -> float:
        positions_value = sum(
            qty * self.current_prices.get(symbol, 0)
            for symbol, qty in self.positions.items()
        )
        return self.cash + positions_value