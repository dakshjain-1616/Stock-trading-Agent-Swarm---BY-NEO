from abc import ABC, abstractmethod
from typing import Any, Optional, Callable, Awaitable
import asyncio
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MessageBus(ABC):
    @abstractmethod
    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        pass
    
    @abstractmethod
    async def subscribe(
        self, 
        channel: str, 
        callback: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        pass
    
    @abstractmethod
    async def close(self) -> None:
        pass


class LocalMessageBus(MessageBus):
    def __init__(self):
        self.channels: dict[str, list[Callable]] = {}
        self.queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._process_messages())
            logger.info("LocalMessageBus started")
    
    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        if not isinstance(message, dict):
            raise ValueError("Message must be a dictionary")
        
        message_with_meta = {
            "channel": channel,
            "data": message,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.queue.put(message_with_meta)
        logger.debug(f"Published to {channel}: {message.get('type', 'unknown')}")
    
    async def subscribe(
        self, 
        channel: str, 
        callback: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        if channel not in self.channels:
            self.channels[channel] = []
        self.channels[channel].append(callback)
        logger.info(f"Subscribed to channel: {channel}")
    
    async def _process_messages(self) -> None:
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self.queue.get(), 
                    timeout=0.1
                )
                channel = message["channel"]
                data = message["data"]
                
                if channel in self.channels:
                    tasks = [
                        callback(data) 
                        for callback in self.channels[channel]
                    ]
                    await asyncio.gather(*tasks, return_exceptions=True)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
    
    async def close(self) -> None:
        self._running = False
        if self._task:
            await self._task
        logger.info("LocalMessageBus closed")


class RedisMessageBus(MessageBus):
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client: Optional[Any] = None
        self.pubsub: Optional[Any] = None
        self.subscribers: dict[str, list[Callable]] = {}
        self._tasks: list[asyncio.Task] = []
    
    async def connect(self) -> None:
        try:
            import redis.asyncio as aioredis
            self.redis_client = aioredis.from_url(
                self.redis_url,
                decode_responses=True
            )
            await self.redis_client.ping()
            self.pubsub = self.redis_client.pubsub()
            logger.info(f"Connected to Redis: {self.redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        if not self.redis_client:
            raise RuntimeError("Redis client not connected")
        
        message_json = json.dumps(message, default=str)
        await self.redis_client.publish(channel, message_json)
        logger.debug(f"Published to Redis {channel}")
    
    async def subscribe(
        self, 
        channel: str, 
        callback: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        if channel not in self.subscribers:
            self.subscribers[channel] = []
            await self.pubsub.subscribe(channel)
            task = asyncio.create_task(self._listen(channel))
            self._tasks.append(task)
        
        self.subscribers[channel].append(callback)
        logger.info(f"Subscribed to Redis channel: {channel}")
    
    async def _listen(self, channel: str) -> None:
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    for callback in self.subscribers.get(channel, []):
                        await callback(data)
                except Exception as e:
                    logger.error(f"Error in subscriber callback: {e}")
    
    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        
        if self.pubsub:
            await self.pubsub.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("RedisMessageBus closed")