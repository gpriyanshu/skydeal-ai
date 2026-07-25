# SkyDeal AI

SkyDeal AI is an intelligent flight deal monitoring system built using Python 3.13, Clean Architecture, and SOLID principles. It periodically scans flight prices, maintains historical statistical baselines (averages, lowest/highest prices), and alerts users via Telegram or Email whenever an exceptional flight deal (e.g. discount >= 20% or drops below historical lowest) is detected.

---

## 🏗️ Architecture

The project follows **Clean Architecture (Hexagonal Architecture)** guidelines:
1. **Domain (Core)**: Pure business models (`entities.py`), custom exceptions (`exceptions.py`), and repository/provider contracts (`interfaces.py`). Totally independent of frameworks, databases, or delivery channels.
2. **Use Cases (Orchestration)**: Implements business transactions:
   - `ScanFlightsUseCase`: Coordinates scanning loops.
   - `DealEngine`: Analyzes price variances using Exponential Moving Averages (EMA) to categorize deals (Normal, Good, Great, Super Deal).
   - `NotifyUsersUseCase`: Checks subscriber preferences (budget, airports, stops, cabin, etc.), enforces duplicate checks and route cooldowns, and dispatches alerts.
   - `ManageUsersUseCase`: Enrolls subscribers and configures their preferences.
3. **Adapters (Interface Mappings)**: Mappings from inner core to outer world:
   - **Database**: SQLite adapter mapping tables with WAL mode enabled.
   - **Providers**: Pluggable providers (`FlightProvider` plugin interface). Includes `MockFlightProvider` for testing and `SkyscannerFlightProvider` as an extension point for real Skyscanner integration.
   - **Notifications**: Telegram bot client (HTML cards with exponential retry backoff) and SMTP Email client.
   - **Scheduler**: Periodically schedules scans via APScheduler.
4. **Infrastructure (Frameworks & Configs)**: Bootstrap configurations, dependency injection containers, and runner engines.

---

## 📁 Folder Structure

```
FlightPulseAI/
├── .github/workflows/
│   └── ci.yml             # GitHub Actions CI pipeline
├── data/                  # Local SQLite database storage directory
├── src/
│   ├── config.py          # Configuration manager loaded via Pydantic
│   ├── main.py            # Entrypoint bootstrap & FastMCP tools setup
│   ├── domain/            # Core models and interface agreements
│   │   ├── entities.py
│   │   ├── exceptions.py
│   │   └── interfaces.py
│   ├── use_cases/         # Core business logic workflows
│   │   ├── detect_deals.py
│   │   ├── manage_users.py
│   │   ├── notify_users.py
│   │   └── scan_flights.py
│   ├── adapters/          # Interface adapters (DB, Senders, Scheduler)
│   │   ├── database/
│   │   ├── notifications/
│   │   ├── providers/
│   │   └── scheduler/
│   └── infrastructure/    # App DI container config
│       └── di_container.py
├── tests/                 # Unit & integration testing suites
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

## ⚙️ Configuration (.env)

Create a `.env` file at the root to configure the application:

```ini
ENV=development
LOG_LEVEL=INFO
DB_PATH=data/skydeal.db
SCAN_INTERVAL_HOURS=1
FLIGHT_PROVIDER=mock

# Telegram (Primary alerts)
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_DEFAULT_CHAT_ID=your-chat-id
TELEGRAM_COOLDOWN_SECONDS=3600

# TravelPayouts Scanning Limits & Filters
TRAVELPAYOUTS_PAGE_SIZE=300
ALLOWED_DESTINATION_COUNTRIES=Thailand,Vietnam,Singapore,Malaysia,Indonesia,Japan,South Korea,United Arab Emirates,Germany,France,Italy
MAX_DAYS_AHEAD=120
COUNTRY_MAX_BUDGETS=Thailand:11000,Vietnam:13000,Malaysia:12000,Singapore:12000,Indonesia:12000,United Arab Emirates:12000,Japan:20000,South Korea:20000,Germany:20000,France:20000,Italy:20000

# SMTP (Secondary alerts)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
```

### Advanced Filtering Parameters
* `ALLOWED_DESTINATION_COUNTRIES`: A comma-separated list of destination countries allowed for deals scanning. If empty, all countries are allowed.
* `MAX_DAYS_AHEAD`: Limits scanning window to flights departing within the specified number of days in the future.
* `COUNTRY_MAX_BUDGETS`: Comma-separated country budget caps in the format `CountryName:BudgetPrice`. Flights costing more than their country's budget cap are automatically filtered out.
* `MAX_DEALS_PER_SCAN`: The maximum number of premium flight deals included in the summary alert message.


---

## 🚀 Getting Started

### Prerequisites
Make sure [uv](https://github.com/astral-sh/uv) is installed.

### Installing Dependencies
Synchronize your virtual environment:
```bash
uv sync --all-groups
```

### Running Locally
To run the background scheduler worker (which runs an initial scan on startup):
```bash
uv run python -m src.main
```

### Running the FastMCP Server
To run SkyDeal AI as a Model Context Protocol (MCP) server for Claude Desktop or Cursor:
```bash
uv run fastmcp dev src/main.py
```

Exposed MCP tools:
- `run_manual_scan()`: Triggers flight scanning on-demand.
- `get_recent_deals(limit)`: Fetches a list of the latest detected flight deals.
- `register_alert_subscriber(chat_id, budget, origin)`: Instantly registers a new alert subscriber.

---

## 🧪 Testing

Run formatting, lint checks, and the Pytest test suite:

```bash
# Linting & Formatting Check
uv run ruff check .
uv run ruff format --check .

# Type check
uv run mypy src

# Run tests
uv run pytest
```

---

## 🐳 Docker Deployment

Build and run in Docker:
```bash
docker-compose up --build -d
```
All flight price data, user configurations, and alert histories are persisted in the named Docker volume `skydeal-data` mapping to `/app/data` inside the container.
