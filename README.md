# 📈 Stock Trading Agent Swarm

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Built by NEO](https://img.shields.io/badge/built%20by-NEO-black.svg)](vscode:extension/NeoResearchInc.heyneo)

> ⚠️ **Disclaimer:** This is a simulation project for educational and research purposes only. It does **not** constitute financial advice. Stock trading involves significant risk — past simulated performance is not indicative of real-world results. Always consult a qualified financial advisor before making investment decisions.

---

This repository was built by **<a href="vscode:extension/NeoResearchInc.heyneo" style="color:#1a7fd4;">NEO</a>**, an autonomous ML agent capable of end-to-end software development — from architecture design to deployment.

---

## Overview

A distributed multi-agent swarm for stock trading simulation, featuring 10 specialized agents that coordinate via an asynchronous message bus. The system backtests across 250 trading days on S&P 500 data.

**Simulation results on $1M capital:**
- Total Return: **+4.62%** ($46,155 profit)
- 86 trades executed, 86.9% order approval rate
- 26 risky orders blocked, 20 stop-losses triggered
- Max drawdown: 0.46%

---

## Architecture

```
3 Analyst Agents    → Generate BUY/SELL signals (SMA crossovers, volume trends)
4 Trader Agents     → Execute trades, manage $250K portfolios each
2 Risk Managers     → Validate orders, enforce stop-loss rules
1 Reporter Agent    → Aggregate P&L and generate reports
```

All agents communicate via an in-memory pub/sub message bus. Risk validation happens in two layers: pre-trade (order approval) and post-trade (stop-loss monitoring).

**Stack:** Python 3.12, Pydantic, yfinance, Docker

---

## Quick Start

```bash
# Clone and install
git clone <repository-url> && cd StocktradingBot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Fetch data
python -c "
from data.data_loader import DataLoader
loader = DataLoader()
tickers = loader.fetch_sp500_tickers(limit=10)
loader.download_historical_data(tickers, '2023-01-01', '2024-01-01')
"

# Run simulation
python src/main.py
```

**Docker:**
```bash
docker-compose up --build
```

**Configuration** (`.env`):
```
INITIAL_CASH=250000
MAX_POSITION_SIZE=0.5
STOP_LOSS_PERCENT=0.10
DATA_START_DATE=2023-01-01
DATA_END_DATE=2024-01-01
```

---

## Project Structure

```
StocktradingBot/
├── agents/          # Analyst, Trader, RiskManager, Reporter
├── core/            # MessageBus, MarketEnvironment, Portfolio, Schemas
├── data/            # DataLoader + historical CSVs
├── src/main.py      # Simulation entry point
├── reports/         # JSON/CSV outputs
└── logs/            # Per-agent isolated logs
```

---

## Extending This Project

This codebase is designed to be modular. Some directions to build further:

- **New agent types** — extend `base_agent.py` to add sentiment analysts, ML-based traders, or news-feed agents
- **Live trading** — swap `MarketEnvironment` for a real broker API (Alpaca, IBKR) with minimal changes to agent logic
- **ML models** — replace SMA crossover logic in `analyst_agent.py` with LSTM or RL-based signal generation
- **Scale out** — the message bus interface is Redis-compatible; swap the in-memory bus to go distributed
- **More markets** — the architecture is symbol-agnostic; point it at crypto or forex data feeds

---

## Testing & Logs

```bash
pytest tests/ -v
pytest tests/ --cov=agents --cov=core --cov-report=html
```

Logs are agent-isolated under `logs/`. Reports output to `reports/daily_pnl.json` and `reports/trades_history.csv`.

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built autonomously by <a href="vscode:extension/NeoResearchInc.heyneo" style="color:#1a7fd4;">NEO</a> — an ML agent that designed, coded, and deployed this system end-to-end. More of NEO's work: [Medical Report Analysis Pipeline](https://github.com/dakshjain-1616/Medical-Report-Analysis-Pipeline-by-Neo).*
