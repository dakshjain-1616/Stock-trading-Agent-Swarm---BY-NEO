import asyncio
import sys
from pathlib import Path
from datetime import datetime
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.message_bus import LocalMessageBus, RedisMessageBus
from core.market_environment import MarketEnvironment
from core.logger import setup_logging
from data.data_loader import DataLoader
from agents import AnalystAgent, TraderAgent, RiskManagerAgent, ReporterAgent

logger = logging.getLogger(__name__)


class TradingSimulation:
    def __init__(
        self,
        symbols: list[str],
        start_date: str,
        end_date: str,
        initial_cash: float = 1000000.0,
        use_redis: bool = False
    ):
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.initial_cash = initial_cash
        self.use_redis = use_redis
        
        self.message_bus = None
        self.market_env = None
        self.agents = []
    
    async def initialize(self) -> None:
        setup_logging(log_level="INFO", log_dir="./logs")
        
        logger.info("=" * 60)
        logger.info("Initializing Trading Simulation Swarm")
        logger.info("=" * 60)
        
        if self.use_redis:
            self.message_bus = RedisMessageBus()
            await self.message_bus.connect()
        else:
            self.message_bus = LocalMessageBus()
            await self.message_bus.start()
        
        logger.info(f"Message bus initialized: {type(self.message_bus).__name__}")
        
        loader = DataLoader()
        historical_data = loader.load_all_historical_data()
        
        if not historical_data:
            logger.info("No cached data found, downloading...")
            historical_data = loader.download_historical_data(
                symbols=self.symbols,
                start_date=self.start_date,
                end_date=self.end_date
            )
        
        logger.info(f"Loaded historical data for {len(historical_data)} symbols")
        
        self.market_env = MarketEnvironment(
            message_bus=self.message_bus,
            historical_data=historical_data
        )
        
        await self._create_agents()
        
        logger.info(f"Created {len(self.agents)} agents total")
    
    async def _create_agents(self) -> None:
        symbols_per_analyst = len(self.symbols) // 3 + 1
        
        for i in range(3):
            start_idx = i * symbols_per_analyst
            end_idx = min((i + 1) * symbols_per_analyst, len(self.symbols))
            analyst_symbols = self.symbols[start_idx:end_idx]
            
            analyst = AnalystAgent(
                agent_id=f"analyst_{i+1}",
                message_bus=self.message_bus,
                symbols=analyst_symbols
            )
            self.agents.append(analyst)
            logger.info(f"Created analyst_{i+1} - monitoring {len(analyst_symbols)} symbols")
        
        symbols_per_trader = len(self.symbols) // 4 + 1
        
        for i in range(4):
            start_idx = i * symbols_per_trader
            end_idx = min((i + 1) * symbols_per_trader, len(self.symbols))
            trader_symbols = self.symbols[start_idx:end_idx]
            
            trader = TraderAgent(
                agent_id=f"trader_{i+1}",
                message_bus=self.message_bus,
                symbols=trader_symbols,
                initial_cash=self.initial_cash / 4
            )
            self.agents.append(trader)
            logger.info(f"Created trader_{i+1} - cash: ${self.initial_cash/4:,.0f}")
        
        for i in range(2):
            risk_manager = RiskManagerAgent(
                agent_id=f"risk_manager_{i+1}",
                message_bus=self.message_bus,
                initial_portfolio_value=self.initial_cash
            )
            self.agents.append(risk_manager)
            logger.info(f"Created risk_manager_{i+1}")
        
        reporter = ReporterAgent(
            agent_id="reporter_1",
            message_bus=self.message_bus
        )
        self.agents.append(reporter)
        logger.info(f"Created reporter_1")
        
        await self.message_bus.subscribe("approved_orders", self._on_approved_order)
    
    async def _on_approved_order(self, message: dict) -> None:
        if message.get("type") != "order_approved":
            return
        
        from core.schemas import Order, OrderSide, OrderStatus
        
        order = Order(
            id=message.get("order_id"),
            timestamp=datetime.fromisoformat(message.get("timestamp")),
            trader_id=message.get("trader_id"),
            symbol=message.get("symbol"),
            side=OrderSide[message.get("side")],
            quantity=message.get("quantity"),
            price=message.get("price"),
            status=OrderStatus.APPROVED
        )
        
        await self.market_env.submit_order(order)
    
    async def run(self) -> None:
        logger.info("=" * 60)
        logger.info("Starting all agents")
        logger.info("=" * 60)
        
        for agent in self.agents:
            await agent.start()
        
        logger.info("All 10 agents are now ACTIVE")
        
        logger.info(f"\nRunning simulation: {self.start_date} to {self.end_date}")
        logger.info(f"Total trading days: {len(self.market_env.timeline)}\n")
        
        total_days = len(self.market_env.timeline)
        
        for day_idx, trading_day in enumerate(self.market_env.timeline):
            await self.market_env.advance_time(trading_day)
            
            await asyncio.sleep(0.1)
            
            await self.market_env.execute_pending_orders()
            
            if day_idx % 10 == 0:
                current_prices = self.market_env.get_all_current_prices()
                
                portfolio_value = 0.0
                for agent in self.agents:
                    if isinstance(agent, TraderAgent):
                        portfolio_value += agent.get_portfolio_value()
                
                await self.message_bus.publish(
                    "portfolio_update",
                    {
                        "type": "portfolio_snapshot",
                        "data": {
                            "date": str(trading_day),
                            "total_value": portfolio_value,
                            "realized_pnl": 0.0,
                            "unrealized_pnl": 0.0
                        }
                    }
                )
            
            if day_idx % 50 == 0 or day_idx == total_days - 1:
                progress_pct = ((day_idx + 1) / total_days) * 100
                logger.info(
                    f"Progress: Day {day_idx+1}/{total_days} ({progress_pct:.1f}%) - {trading_day}"
                )
        
        logger.info("\n" + "=" * 60)
        logger.info("Simulation complete - Generating final report")
        logger.info("=" * 60)
        
        await asyncio.sleep(1)
        
        reporter = next(a for a in self.agents if isinstance(a, ReporterAgent))
        report = await reporter.generate_daily_report(str(self.market_env.timeline[-1]))
        
        logger.info("\n" + "=" * 60)
        logger.info("FINAL REPORT SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total Portfolio Value: ${report['summary']['total_portfolio_value']:,.2f}")
        logger.info(f"Total P&L:            ${report['summary']['total_pnl']:,.2f}")
        logger.info(f"  - Realized P&L:     ${report['summary']['realized_pnl']:,.2f}")
        logger.info(f"  - Unrealized P&L:   ${report['summary']['unrealized_pnl']:,.2f}")
        logger.info(f"\nTotal Trades:         {report['summary']['total_trades']}")
        logger.info(f"  - Buy Orders:       {report['summary']['buy_orders']}")
        logger.info(f"  - Sell Orders:      {report['summary']['sell_orders']}")
        logger.info(f"\nApproved Orders:      {report['risk_metrics']['approved_orders']}")
        logger.info(f"Rejected Orders:      {report['risk_metrics']['rejected_orders']} ({report['risk_metrics']['rejected_orders_pct']:.1f}%)")
        logger.info(f"Stop Losses:          {report['risk_metrics']['stop_losses_triggered']}")
        logger.info(f"Max Drawdown:         {report['risk_metrics']['max_drawdown']*100:.2f}%")
        logger.info("=" * 60)
        
        await self.shutdown()
    
    async def shutdown(self) -> None:
        logger.info("\nShutting down agents...")
        
        for agent in self.agents:
            await agent.stop()
        
        if self.message_bus:
            await self.message_bus.close()
        
        logger.info("Simulation shutdown complete")


async def main():
    symbols = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
        "META", "NVDA", "JPM", "V", "JNJ"
    ]
    
    sim = TradingSimulation(
        symbols=symbols,
        start_date="2023-01-01",
        end_date="2024-01-01",
        initial_cash=1000000.0,
        use_redis=False
    )
    
    await sim.initialize()
    await sim.run()


if __name__ == "__main__":
    asyncio.run(main())