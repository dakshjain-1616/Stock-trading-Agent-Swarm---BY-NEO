from datetime import datetime
from typing import Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"


class SignalType(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class News(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    id: str = Field(..., description="Unique news identifier")
    timestamp: datetime = Field(..., description="News publish time")
    symbol: str = Field(..., description="Stock ticker symbol")
    headline: str = Field(..., description="News headline")
    content: Optional[str] = Field(None, description="Full news content")
    source: str = Field(..., description="News source name")
    sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0)


class Signal(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    id: str = Field(..., description="Unique signal identifier")
    timestamp: datetime = Field(..., description="Signal generation time")
    agent_id: str = Field(..., description="Analyst agent identifier")
    symbol: str = Field(..., description="Stock ticker symbol")
    signal_type: SignalType = Field(..., description="Signal type")
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: Optional[str] = Field(None, description="Signal rationale")


class Order(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    id: str = Field(..., description="Unique order identifier")
    timestamp: datetime = Field(..., description="Order creation time")
    trader_id: str = Field(..., description="Trader agent identifier")
    symbol: str = Field(..., description="Stock ticker symbol")
    side: OrderSide = Field(..., description="Buy or Sell")
    quantity: int = Field(..., gt=0, description="Number of shares")
    price: Optional[float] = Field(None, gt=0, description="Limit price")
    status: OrderStatus = Field(default=OrderStatus.PENDING)
    signal_id: Optional[str] = Field(None, description="Originating signal ID")
    rejection_reason: Optional[str] = Field(None)


class Trade(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    id: str = Field(..., description="Unique trade identifier")
    timestamp: datetime = Field(..., description="Execution time")
    order_id: str = Field(..., description="Original order ID")
    symbol: str = Field(..., description="Stock ticker symbol")
    side: OrderSide = Field(..., description="Buy or Sell")
    quantity: int = Field(..., gt=0)
    execution_price: float = Field(..., gt=0)
    commission: float = Field(default=0.0, ge=0)
    trader_id: str = Field(..., description="Trader agent identifier")


class Position(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    symbol: str = Field(..., description="Stock ticker symbol")
    quantity: int = Field(..., description="Current shares held")
    avg_cost: float = Field(..., gt=0, description="Average purchase price")
    current_price: float = Field(..., gt=0)
    unrealized_pnl: float = Field(...)
    
    def update_price(self, new_price: float) -> None:
        self.current_price = new_price
        self.unrealized_pnl = (new_price - self.avg_cost) * self.quantity


class PortfolioState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    cash: float = Field(..., ge=0)
    positions: dict[str, Position] = Field(default_factory=dict)
    total_value: float = Field(...)
    realized_pnl: float = Field(default=0.0)
    
    def calculate_total_value(self) -> float:
        positions_value = sum(
            pos.quantity * pos.current_price 
            for pos in self.positions.values()
        )
        return self.cash + positions_value


class MarketData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    timestamp: datetime = Field(...)
    symbol: str = Field(...)
    open: float = Field(..., gt=0)
    high: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    volume: int = Field(..., ge=0)