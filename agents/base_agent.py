from abc import ABC, abstractmethod
from typing import Optional
import asyncio
import logging
from datetime import datetime

from core.message_bus import MessageBus
from core.logger import StructuredLogger

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    def __init__(
        self,
        agent_id: str,
        message_bus: MessageBus,
        log_level: str = "INFO"
    ):
        self.agent_id = agent_id
        self.message_bus = message_bus
        self.logger = StructuredLogger(agent_id, log_level)
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        if self._running:
            self.logger.warning("Agent already running")
            return
        
        self._running = True
        await self._setup_subscriptions()
        self._task = asyncio.create_task(self._run())
        self.logger.info(f"Agent {self.agent_id} started")
    
    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.logger.info(f"Agent {self.agent_id} stopped")
    
    @abstractmethod
    async def _setup_subscriptions(self) -> None:
        pass
    
    @abstractmethod
    async def _run(self) -> None:
        pass
    
    async def publish(self, channel: str, message: dict) -> None:
        try:
            await self.message_bus.publish(channel, message)
        except Exception as e:
            self.logger.error(f"Failed to publish message: {e}", channel=channel)
    
    async def subscribe(self, channel: str, callback) -> None:
        try:
            await self.message_bus.subscribe(channel, callback)
        except Exception as e:
            self.logger.error(f"Failed to subscribe to channel: {e}", channel=channel)