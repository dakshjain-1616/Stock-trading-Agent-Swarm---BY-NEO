import asyncio
from datetime import datetime
from typing import Dict
import logging

from .base_agent import BaseAgent
from core.schemas import OrderSide
from core.message_bus import MessageBus

logger = logging.getLogger(__name__)


class RiskManagerAgent(BaseAgent):
    def __init__(
        self,
        agent_id: str,
        message_bus: MessageBus,
        initial_portfolio_value: float = 1000000.0,
        max_position_size: float = 50000.0,
        stop_loss_percent: float = 0.05,
        max_portfolio_risk: float = 0.20,
        log_level: str = "INFO"
    ):
        super().__init__(agent_id, message_bus, log_level)
        self.initial_portfolio_value = initial_portfolio_value
        self.max_position_size = max_position_size
        self.stop_loss_percent = stop_loss_percent
        self.max_portfolio_risk = max_portfolio_risk
        
        self.current_positions: Dict[str, Dict] = {}
        self.current_prices: Dict[str, float] = {}
        self.trader_cash: Dict[str, float] = {}
        
        self.approved_count = 0
        self.rejected_count = 0
    
    async def _setup_subscriptions(self) -> None:
        await self.subscribe("orders", self._on_order_request)
        await self.subscribe("market_data", self._on_market_update)
        await self.subscribe("trades", self._on_trade_executed)
    
    async def _run(self) -> None:
        while self._running:
            await self._check_stop_losses()
            await asyncio.sleep(2)
    
    async def _on_market_update(self, message: dict) -> None:
        if message.get("type") != "market_update":
            return
        
        symbol = message.get("symbol")
        close_price = message.get("close")
        
        if symbol and close_price:
            self.current_prices[symbol] = close_price
    
    async def _on_order_request(self, message: dict) -> None:
        if message.get("type") != "order_request":
            return
        
        order_id = message.get("order_id")
        trader_id = message.get("trader_id")
        symbol = message.get("symbol")
        side = message.get("side")
        quantity = message.get("quantity")
        price = message.get("price")
        
        approved, reason = await self._validate_order(
            trader_id, symbol, side, quantity, price
        )
        
        if approved:
            self.approved_count += 1
            self.logger.info(
                f"Order APPROVED",
                order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=quantity
            )
        else:
            self.rejected_count += 1
            self.logger.warning(
                f"Order REJECTED",
                order_id=order_id,
                symbol=symbol,
                reason=reason
            )
        
        await self.publish(
            "risk_decisions",
            {
                "type": "risk_decision",
                "order_id": order_id,
                "approved": approved,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    async def _validate_order(
        self,
        trader_id: str,
        symbol: str,
        side: str,
        quantity: int,
        price: float
    ) -> tuple[bool, str]:
        if symbol not in self.current_prices:
            return False, "No market data available for symbol"
        
        current_price = self.current_prices[symbol]
        order_value = quantity * current_price
        
        if order_value > self.max_position_size:
            return False, f"Order value ${order_value:.2f} exceeds max position size ${self.max_position_size:.2f}"
        
        trader_cash = self.trader_cash.get(trader_id, self.initial_portfolio_value / 4)
        
        if side == "BUY":
            if order_value > trader_cash:
                return False, f"Insufficient cash: need ${order_value:.2f}, have ${trader_cash:.2f}"
        
        elif side == "SELL":
            trader_key = f"{trader_id}_{symbol}"
            current_position = self.current_positions.get(trader_key, {}).get("quantity", 0)
            
            if quantity > current_position:
                return False, f"Insufficient shares: trying to sell {quantity}, have {current_position}"
        
        total_exposure = sum(
            pos.get("quantity", 0) * self.current_prices.get(pos.get("symbol", ""), 0)
            for pos in self.current_positions.values()
        )
        
        max_allowed_exposure = self.initial_portfolio_value * self.max_portfolio_risk
        
        if side == "BUY" and (total_exposure + order_value) > max_allowed_exposure:
            return False, f"Portfolio risk limit exceeded: ${total_exposure + order_value:.2f} > ${max_allowed_exposure:.2f}"
        
        return True, "Order approved"
    
    async def _on_trade_executed(self, message: dict) -> None:
        if message.get("type") != "trade_executed":
            return
        
        trader_id = message.get("trader_id")
        symbol = message.get("symbol")
        side = message.get("side")
        quantity = message.get("quantity")
        execution_price = message.get("execution_price")
        commission = message.get("commission", 0.0)
        
        trader_key = f"{trader_id}_{symbol}"
        
        if trader_key not in self.current_positions:
            self.current_positions[trader_key] = {
                "trader_id": trader_id,
                "symbol": symbol,
                "quantity": 0,
                "avg_cost": 0.0
            }
        
        position = self.current_positions[trader_key]
        
        if side == "BUY":
            total_cost = (position["quantity"] * position["avg_cost"]) + (quantity * execution_price)
            position["quantity"] += quantity
            position["avg_cost"] = total_cost / position["quantity"] if position["quantity"] > 0 else 0
            
            current_cash = self.trader_cash.get(trader_id, self.initial_portfolio_value / 4)
            self.trader_cash[trader_id] = current_cash - (execution_price * quantity + commission)
        
        elif side == "SELL":
            position["quantity"] -= quantity
            if position["quantity"] <= 0:
                del self.current_positions[trader_key]
            
            current_cash = self.trader_cash.get(trader_id, self.initial_portfolio_value / 4)
            self.trader_cash[trader_id] = current_cash + (execution_price * quantity - commission)
        
        self.logger.debug(
            f"Position updated",
            trader_id=trader_id,
            symbol=symbol,
            side=side,
            new_quantity=position.get("quantity", 0) if trader_key in self.current_positions else 0
        )
    
    async def _check_stop_losses(self) -> None:
        for trader_key, position in list(self.current_positions.items()):
            symbol = position["symbol"]
            quantity = position["quantity"]
            avg_cost = position["avg_cost"]
            
            if symbol not in self.current_prices or quantity <= 0:
                continue
            
            current_price = self.current_prices[symbol]
            loss_percent = (avg_cost - current_price) / avg_cost
            
            if loss_percent > self.stop_loss_percent:
                trader_id = position["trader_id"]
                
                self.logger.warning(
                    f"STOP LOSS triggered",
                    symbol=symbol,
                    trader_id=trader_id,
                    loss_percent=f"{loss_percent*100:.2f}%",
                    avg_cost=f"{avg_cost:.2f}",
                    current_price=f"{current_price:.2f}"
                )
                
                await self.publish(
                    "stop_loss_alerts",
                    {
                        "type": "stop_loss",
                        "trader_id": trader_id,
                        "symbol": symbol,
                        "quantity": quantity,
                        "avg_cost": avg_cost,
                        "current_price": current_price,
                        "loss_percent": loss_percent,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )