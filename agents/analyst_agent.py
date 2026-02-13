import asyncio
import random
from datetime import datetime
from typing import Optional
import logging

from .base_agent import BaseAgent
from core.schemas import Signal, SignalType, News
from core.message_bus import MessageBus

logger = logging.getLogger(__name__)


class AnalystAgent(BaseAgent):
    def __init__(
        self,
        agent_id: str,
        message_bus: MessageBus,
        symbols: list[str],
        log_level: str = "INFO"
    ):
        super().__init__(agent_id, message_bus, log_level)
        self.symbols = symbols
        self.news_cache: list[News] = []
        self.signal_count = 0
    
    async def _setup_subscriptions(self) -> None:
        await self.subscribe("market_data", self._on_market_update)
        await self.subscribe("news_feed", self._on_news)
    
    async def _run(self) -> None:
        while self._running:
            await asyncio.sleep(1)
    
    async def _on_market_update(self, message: dict) -> None:
        if message.get("type") != "market_update":
            return
        
        symbol = message.get("symbol")
        if symbol not in self.symbols:
            return
        
        close_price = message.get("close")
        open_price = message.get("open")
        
        if not close_price or not open_price:
            return
        
        price_change = (close_price - open_price) / open_price
        
        if random.random() < 0.3:
            await self._generate_signal(symbol, price_change, message.get("timestamp"))
    
    async def _on_news(self, message: dict) -> None:
        if message.get("type") != "news_item":
            return
        
        try:
            news = News(**message.get("data", {}))
            self.news_cache.append(news)
            
            if news.sentiment_score is not None:
                await self._generate_signal_from_news(news)
        
        except Exception as e:
            self.logger.error(f"Failed to process news: {e}")
    
    async def _generate_signal(
        self, 
        symbol: str, 
        price_change: float,
        timestamp: Optional[str] = None
    ) -> None:
        if abs(price_change) < 0.01:
            return
        
        if price_change > 0.02:
            signal_type = SignalType.BULLISH
            confidence = min(0.9, 0.5 + abs(price_change) * 10)
            reasoning = f"Strong upward momentum: {price_change*100:.2f}%"
        elif price_change < -0.02:
            signal_type = SignalType.BEARISH
            confidence = min(0.9, 0.5 + abs(price_change) * 10)
            reasoning = f"Downward pressure: {price_change*100:.2f}%"
        else:
            signal_type = SignalType.NEUTRAL
            confidence = 0.3
            reasoning = f"Minimal movement: {price_change*100:.2f}%"
        
        self.signal_count += 1
        signal = Signal(
            id=f"{self.agent_id}_signal_{self.signal_count}",
            timestamp=datetime.fromisoformat(timestamp) if timestamp else datetime.utcnow(),
            agent_id=self.agent_id,
            symbol=symbol,
            signal_type=signal_type,
            confidence=confidence,
            reasoning=reasoning
        )
        
        await self.publish(
            "signals",
            {
                "type": "signal",
                "signal_id": signal.id,
                "timestamp": signal.timestamp.isoformat(),
                "agent_id": signal.agent_id,
                "symbol": signal.symbol,
                "signal_type": signal.signal_type.value,
                "confidence": signal.confidence,
                "reasoning": signal.reasoning
            }
        )
        
        self.logger.info(
            f"Generated signal",
            signal_id=signal.id,
            symbol=symbol,
            type=signal_type.value,
            confidence=f"{confidence:.2f}"
        )
    
    async def _generate_signal_from_news(self, news: News) -> None:
        if news.sentiment_score is None:
            return
        
        if news.sentiment_score > 0.3:
            signal_type = SignalType.BULLISH
            confidence = min(0.85, 0.5 + news.sentiment_score * 0.5)
        elif news.sentiment_score < -0.3:
            signal_type = SignalType.BEARISH
            confidence = min(0.85, 0.5 + abs(news.sentiment_score) * 0.5)
        else:
            return
        
        self.signal_count += 1
        signal = Signal(
            id=f"{self.agent_id}_signal_{self.signal_count}",
            timestamp=datetime.utcnow(),
            agent_id=self.agent_id,
            symbol=news.symbol,
            signal_type=signal_type,
            confidence=confidence,
            reasoning=f"News sentiment: {news.headline[:50]}..."
        )
        
        await self.publish(
            "signals",
            {
                "type": "signal",
                "signal_id": signal.id,
                "timestamp": signal.timestamp.isoformat(),
                "agent_id": signal.agent_id,
                "symbol": signal.symbol,
                "signal_type": signal.signal_type.value,
                "confidence": signal.confidence,
                "reasoning": signal.reasoning
            }
        )
        
        self.logger.info(
            f"Generated news-based signal",
            signal_id=signal.id,
            symbol=news.symbol,
            type=signal_type.value
        )