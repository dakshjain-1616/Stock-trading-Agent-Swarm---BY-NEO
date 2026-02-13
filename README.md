# Stock Trading Simulation Swarm

A production-grade multi-agent stock trading simulation system with 10 autonomous agents organized into specialized roles.

## Architecture Overview

### Agent Types
- **3 Analyst Agents**: Analyze market data and news feeds, emit trading signals
- **4 Trader Agents**: Execute trades based on analyst signals
- **2 Risk Manager Agents**: Enforce risk constraints and approve/reject orders
- **1 Reporter Agent**: Generate daily P&L reports and performance metrics

### Core Components
- **MessageBus**: Asynchronous pub/sub communication (Local or Redis)
- **MarketEnvironment**: Historical data replay and order matching engine
- **Portfolio**: Position tracking and P&L calculation
- **Schemas**: Pydantic models for data validation

## Setup Instructions

### Local Development

1. **Create virtual environment**:
```bash
python3 -m venv venv
source venv/bin/activate
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Download historical data**:
```bash
python -c "
from data.data_loader import DataLoader
loader = DataLoader()
tickers = loader.fetch_sp500_tickers(limit=10)
loader.download_historical_data(tickers, '2023-01-01', '2024-01-01')
"
```

4. **Run simulation**:
```bash
python src/main.py
```

### Docker Deployment

1. **Build and run with Docker Compose**:
```bash
docker-compose up --build
```

2. **View logs**:
```bash
docker-compose logs -f orchestrator
```

3. **Stop simulation**:
```bash
docker-compose down
```

## Configuration

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

Key parameters:
- `INITIAL_CASH`: Starting portfolio value
- `MAX_POSITION_SIZE`: Maximum position size per trade
- `STOP_LOSS_PERCENT`: Stop loss threshold
- `MESSAGE_BUS_TYPE`: local or redis

## Output Reports

After simulation completes:

- **JSON Report**: `reports/daily_pnl.json`
  - Total P&L (realized + unrealized)
  - Trade history with timestamps
  - Risk metrics (drawdown, rejected orders)
  
- **CSV Report**: `reports/trades_history.csv`
  - Detailed trade execution log

## Project Structure

```
```
StocktradingBot/
├── agents/               # Agent implementations
│   ├── analyst_agent.py
│   ├── trader_agent.py
│   ├── risk_manager_agent.py
│   └── reporter_agent.py
├── core/                 # Core infrastructure
│   ├── schemas.py
│   ├── message_bus.py
│   ├── market_environment.py
│   ├── portfolio.py
│   └── logger.py
├── data/                 # Data loading and storage
│   └── data_loader.py
├── src/                  # Main orchestration
│   └── main.py
├── config/               # Configuration files
├── tests/                # Unit tests
├── logs/                 # Runtime logs
├── reports/              # Generated reports
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```
```

## Testing

Run unit tests:
```bash
pytest tests/
```

## Monitoring

- Agent logs: `logs/` directory
- Trade execution: Real-time in stdout
- Portfolio snapshots: Every 10 trading days
- Final report: `reports/daily_pnl.json`

## Performance Metrics

The simulation tracks:
- Total P&L (realized + unrealized)
- Total trades executed
- Order approval/rejection rates
- Stop losses triggered
- Maximum drawdown
- Portfolio value over time