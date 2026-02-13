import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import logging

from .base_agent import BaseAgent
from core.message_bus import MessageBus

logger = logging.getLogger(__name__)


class ReporterAgent(BaseAgent):
    def __init__(
        self,
        agent_id: str,
        message_bus: MessageBus,
        reports_dir: Path = Path("./reports"),
        log_level: str = "INFO"
    ):
        super().__init__(agent_id, message_bus, log_level)
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        self.trades: List[dict] = []
        self.stop_losses: List[dict] = []
        self.risk_decisions: List[dict] = []
        self.portfolio_snapshots: List[dict] = []
        
        self.daily_stats: Dict[str, any] = {
            "total_trades": 0,
            "buy_orders": 0,
            "sell_orders": 0,
            "approved_orders": 0,
            "rejected_orders": 0,
            "stop_losses_triggered": 0
        }
    
    async def _setup_subscriptions(self) -> None:
        await self.subscribe("trades", self._on_trade)
        await self.subscribe("risk_decisions", self._on_risk_decision)
        await self.subscribe("stop_loss_alerts", self._on_stop_loss)
        await self.subscribe("portfolio_update", self._on_portfolio_update)
    
    async def _run(self) -> None:
        while self._running:
            await asyncio.sleep(1)
    
    async def _on_trade(self, message: dict) -> None:
        if message.get("type") != "trade_executed":
            return
        
        self.trades.append({
            "trade_id": message.get("trade_id"),
            "order_id": message.get("order_id"),
            "timestamp": message.get("timestamp"),
            "symbol": message.get("symbol"),
            "side": message.get("side"),
            "quantity": message.get("quantity"),
            "execution_price": message.get("execution_price"),
            "commission": message.get("commission"),
            "trader_id": message.get("trader_id")
        })
        
        self.daily_stats["total_trades"] += 1
        
        if message.get("side") == "BUY":
            self.daily_stats["buy_orders"] += 1
        elif message.get("side") == "SELL":
            self.daily_stats["sell_orders"] += 1
        
        self.logger.debug(f"Trade recorded: {message.get('trade_id')}")
    
    async def _on_risk_decision(self, message: dict) -> None:
        if message.get("type") != "risk_decision":
            return
        
        self.risk_decisions.append({
            "order_id": message.get("order_id"),
            "approved": message.get("approved"),
            "reason": message.get("reason"),
            "timestamp": message.get("timestamp")
        })
        
        if message.get("approved"):
            self.daily_stats["approved_orders"] += 1
        else:
            self.daily_stats["rejected_orders"] += 1
    
    async def _on_stop_loss(self, message: dict) -> None:
        if message.get("type") != "stop_loss":
            return
        
        self.stop_losses.append({
            "trader_id": message.get("trader_id"),
            "symbol": message.get("symbol"),
            "quantity": message.get("quantity"),
            "avg_cost": message.get("avg_cost"),
            "current_price": message.get("current_price"),
            "loss_percent": message.get("loss_percent"),
            "timestamp": message.get("timestamp")
        })
        
        self.daily_stats["stop_losses_triggered"] += 1
        
        self.logger.info(f"Stop loss recorded for {message.get('symbol')}")
    
    async def _on_portfolio_update(self, message: dict) -> None:
        if message.get("type") != "portfolio_snapshot":
            return
        
        self.portfolio_snapshots.append(message.get("data", {}))
    
    async def generate_daily_report(self, simulation_date: str) -> dict:
        total_value = 0.0
        realized_pnl = 0.0
        unrealized_pnl = 0.0
        
        if self.portfolio_snapshots:
            latest_snapshot = self.portfolio_snapshots[-1]
            total_value = latest_snapshot.get("total_value", 0.0)
            realized_pnl = latest_snapshot.get("realized_pnl", 0.0)
            unrealized_pnl = latest_snapshot.get("unrealized_pnl", 0.0)
        
        rejected_orders_pct = 0.0
        total_orders = self.daily_stats["approved_orders"] + self.daily_stats["rejected_orders"]
        if total_orders > 0:
            rejected_orders_pct = (self.daily_stats["rejected_orders"] / total_orders) * 100
        
        max_drawdown = self._calculate_max_drawdown()
        
        report = {
            "date": simulation_date,
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total_portfolio_value": total_value,
                "realized_pnl": realized_pnl,
                "unrealized_pnl": unrealized_pnl,
                "total_pnl": realized_pnl + unrealized_pnl,
                "total_trades": self.daily_stats["total_trades"],
                "buy_orders": self.daily_stats["buy_orders"],
                "sell_orders": self.daily_stats["sell_orders"]
            },
            "risk_metrics": {
                "approved_orders": self.daily_stats["approved_orders"],
                "rejected_orders": self.daily_stats["rejected_orders"],
                "rejected_orders_pct": rejected_orders_pct,
                "stop_losses_triggered": self.daily_stats["stop_losses_triggered"],
                "max_drawdown": max_drawdown
            },
            "trades": self.trades,
            "stop_losses": self.stop_losses,
            "rejected_orders": [
                dec for dec in self.risk_decisions if not dec.get("approved")
            ]
        }
        
        report_path = self.reports_dir / "daily_pnl.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.logger.info(f"Daily report generated: {report_path}")
        
        csv_report_path = self.reports_dir / "trades_history.csv"
        await self._generate_csv_report(csv_report_path)
        
        return report
    
    def _calculate_max_drawdown(self) -> float:
        if len(self.portfolio_snapshots) < 2:
            return 0.0
        
        values = [snap.get("total_value", 0) for snap in self.portfolio_snapshots]
        peak = values[0]
        max_dd = 0.0
        
        for value in values:
            if value > peak:
                peak = value
            dd = (peak - value) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        return max_dd
    
    async def _generate_csv_report(self, csv_path: Path) -> None:
        if not self.trades:
            return
        
        import csv
        
        with open(csv_path, 'w', newline='') as f:
            if self.trades:
                fieldnames = self.trades[0].keys()
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.trades)
        
        self.logger.info(f"CSV report generated: {csv_path}")