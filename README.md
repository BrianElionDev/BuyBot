# Rubicon Trading Bot

A sophisticated, enterprise-grade cryptocurrency trading bot built with Python that provides real-time trade execution, position management, and automated trading strategies across multiple exchanges. The system features a microservices architecture with comprehensive monitoring, automated maintenance, and advanced trading capabilities.

## 🚀 Key Features

### **Multi-Exchange Trading**
- **Binance Futures**: Full futures trading with position management and risk controls
- **KuCoin Futures**: Advanced order types and automated position sizing
- **Real-time Execution**: WebSocket-based real-time price feeds and order execution
- **Position Management**: Automated entry, exit, stop-loss, and take-profit management

### **Advanced Trading Engine**
- **Discord Signal Processing**: Real-time trade signal processing from Discord channels
- **AI-Powered Parsing**: Intelligent signal parsing with structured trade data extraction
- **Risk Management**: Automated position sizing, stop-loss placement, and risk controls
- **Multi-Strategy Support**: Support for various trading strategies and signal types

### **Active Futures Synchronization**
- **Real-time Monitoring**: Continuous monitoring of active futures positions
- **Automatic Closure**: Immediate position closure when futures indicate closure
- **Smart Matching**: Advanced algorithm matching active futures to local trades
- **Confidence Scoring**: Multi-factor matching with confidence thresholds

### **Enterprise Infrastructure**
- **Microservices Architecture**: Modular design with separate services for different functions
- **Database Integration**: Supabase-based data persistence with real-time subscriptions
- **Docker Deployment**: Containerized deployment with Docker Compose
- **API Endpoints**: RESTful APIs for external integrations and monitoring
- **Comprehensive Logging**: Structured logging with multiple log levels and formats

### **Automated Maintenance**
- **Transaction History**: Automated filling of historical transaction data
- **PnL Backfilling**: Automated profit/loss calculation and backfilling
- **Price Synchronization**: Real-time and historical price data synchronization
- **Orphaned Orders Cleanup**: Automated detection and cleanup of orphaned orders
- **Balance Synchronization**: Real-time balance tracking across exchanges
- **Stop-Loss Auditing**: Automated auditing of stop-loss orders for compliance

## 📋 Prerequisites

### **System Requirements**
- **Python 3.8 or higher** (3.9+ recommended for optimal performance)
- **Docker & Docker Compose** (for containerized deployment)
- **Git** (for version control)
- **Linux/macOS/Windows** (Linux recommended for production)

### **API Credentials Required**
- **Discord Bot Token** (for signal processing)
- **Binance API Credentials**:
  - API Key with futures trading permissions
  - API Secret
  - Enable futures trading permissions
- **KuCoin API Credentials**:
  - API Key with futures trading permissions
  - API Secret
  - API Passphrase
- **Supabase Credentials**:
  - Project URL
  - Service Role Key (for database operations)

### **Optional Dependencies**
- **Redis** (for enhanced caching and session management)
- **PostgreSQL** (alternative to Supabase for self-hosted deployments)
- **Nginx** (for reverse proxy and load balancing)

## 🛠️ Installation

### **Quick Start (Docker)**
```bash
# Clone the repository
git clone <repository-url>
cd rubicon-trading-bot

# Copy environment configuration
cp example.env .env

# Edit .env with your credentials
nano .env  # or your preferred editor

# Start all services
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f discord-bot
```

### **Manual Installation (Development)**
```bash
# Clone the repository
git clone <repository-url>
cd rubicon-trading-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp example.env .env
# Edit .env with your credentials

# Run the Discord bot service
python -m discord_bot.main
```

### **Production Deployment**
```bash
# Build and deploy with Docker
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Or use the deployment script
./deploy.sh
```

## ⚙️ Configuration

### **Environment Variables (.env)**
```properties
# Discord Bot Configuration
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_GUILD_ID=your_guild_id

# Binance Exchange
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
BINANCE_TESTNET=false

# KuCoin Exchange
KUCOIN_API_KEY=your_kucoin_api_key
KUCOIN_API_SECRET=your_kucoin_api_secret
KUCOIN_API_PASSPHRASE=your_kucoin_passphrase

# Database (Supabase)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# Trading Configuration
TARGET_TRADERS=@Trader1,@Trader2
RISK_PERCENTAGE=2.0
MAX_POSITION_SIZE=1000.0

# Logging
LOG_LEVEL=INFO
LOG_FILE_PATH=/var/log/rubicon

# Scheduler Intervals (seconds)
DAILY_SYNC_INTERVAL=86400
ACTIVE_FUTURES_SYNC_INTERVAL=300
```

### **Exchange-Specific Setup**

#### **Binance Configuration**
1. Create API key at [Binance API Management](https://www.binance.com/en/my/settings/api-management)
2. Enable **"Enable Futures"** permission
3. Set IP restrictions if needed for security

#### **KuCoin Configuration**
1. Create API key at [KuCoin API Management](https://www.kucoin.com/account/api)
2. Enable **"Futures Trading"** permission
3. Generate and securely store API passphrase

#### **Discord Bot Setup**
1. Create Discord application at [Discord Developer Portal](https://discord.com/developers/applications)
2. Generate bot token and copy to `.env`
3. Invite bot to your server with appropriate permissions

## 🏗️ Architecture

### **Microservices Architecture**

The Rubicon Trading Bot follows a modular microservices design:

```
rubicon-trading-bot/
├── 📁 src/                          # Core business logic
│   ├── 📁 bot/                      # Trading engines
│   │   ├── 📁 binance_trading_engine.py
│   │   ├── 📁 kucoin_trading_engine.py
│   │   └── 📁 trading_engine.py
│   ├── 📁 core/                     # Core services
│   │   ├── 📁 position_manager.py
│   │   └── 📁 risk_manager.py
│   ├── 📁 database/                 # Data layer
│   │   ├── 📁 core/
│   │   ├── 📁 models/
│   │   ├── 📁 repositories/
│   │   └── 📁 migrations/
│   ├── 📁 exchange/                 # Exchange integrations
│   │   ├── 📁 binance/
│   │   └── 📁 kucoin/
│   ├── 📁 services/                 # Business services
│   │   ├── 📁 active_futures_sync_service.py
│   │   ├── 📁 position_close_service.py
│   │   └── 📁 trade_service.py
│   └── 📁 utils/                    # Utilities
│
├── 📁 discord_bot/                  # Discord integration service
│   ├── 📁 endpoints/               # API endpoints
│   ├── 📁 utils/                   # Discord utilities
│   └── 📁 main.py
│
├── 📁 scripts/                     # Maintenance scripts
│   ├── 📁 maintenance/             # Automated maintenance
│   ├── 📁 account_management/      # Account management
│   └── 📁 testing/                 # Test utilities
│
├── 📁 tests/                       # Test suite
├── 📁 config/                      # Configuration files
├── 📁 logs/                        # Log files
├── 📁 docs/                        # Documentation
├── 📁 docker-compose.yml           # Docker orchestration
├── 📁 Dockerfile                   # Container definition
├── 📁 requirements.txt             # Python dependencies
├── 📁 nginx.conf                   # Reverse proxy config
└── 📁 main.py                      # Main entry point
```

### **Service Communication**

- **Discord Bot Service**: Handles real-time signal processing and API endpoints
- **Active Futures Sync**: Monitors and synchronizes futures positions
- **Trading Engines**: Execute trades across multiple exchanges
- **Database Layer**: Manages data persistence and real-time subscriptions
- **Maintenance Services**: Automated cleanup and synchronization tasks

### **Data Flow**

1. **Signal Reception**: Discord signals received via webhooks
2. **Signal Processing**: AI-powered parsing and validation
3. **Trade Execution**: Position opening via exchange APIs
4. **Position Monitoring**: Real-time tracking and risk management
5. **Active Futures Sync**: Continuous monitoring of futures positions
6. **Automated Closure**: Immediate closure when futures indicate exit

## 🔧 API Endpoints

### **Discord Service API**
- `GET /` - Service health check
- `GET /health` - Detailed health status
- `GET /websocket/status` - WebSocket connection status
- `POST /api/v1/discord/signal` - Receive trade signals
- `POST /api/v1/discord/signal/update` - Update existing trades
- `POST /scheduler/*` - Manual maintenance triggers

### **Service Management**
- `POST /scheduler/test-transaction-history` - Manual transaction sync
- `POST /scheduler/test-daily-sync` - Manual daily synchronization
- `POST /scheduler/test-orphaned-orders-cleanup` - Manual cleanup
- `GET /scheduler/status` - Scheduler status and intervals

## 🧪 Testing

### **Test Categories**
- **Unit Tests**: Individual component testing
- **Integration Tests**: Service interaction testing
- **End-to-End Tests**: Complete workflow testing
- **Performance Tests**: Load and stress testing

### **Running Tests**
```bash
# Run all tests
pytest tests/

# Run specific test category
pytest tests/test_active_futures_sync.py

# Run with coverage
pytest --cov=src tests/

# Run integration tests
pytest tests/test_integration.py -v
```

## 🚀 Deployment

### **Docker Deployment**
```bash
# Development environment
docker-compose up -d

# Production environment
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Scale services
docker-compose up -d --scale discord-bot=2
```

### **Production Considerations**
- **Load Balancing**: Nginx reverse proxy configuration
- **Monitoring**: Health checks and metrics collection
- **Security**: API key rotation and access controls
- **Backup**: Database backup strategies
- **Logging**: Centralized log aggregation

## 🤝 Contributing

### **Development Workflow**
1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Make** your changes with proper tests
4. **Commit** your changes (`git commit -m 'Add amazing feature'`)
5. **Push** to the branch (`git push origin feature/amazing-feature`)
6. **Open** a Pull Request

### **Code Standards**
- **Type Hints**: All functions should have proper type annotations
- **Documentation**: Comprehensive docstrings for all public methods
- **Testing**: Test coverage > 90% for new features
- **Error Handling**: Proper exception handling with logging
- **Code Style**: Follow PEP 8 and use black for formatting

### **Development Setup**
```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Set up pre-commit hooks
pre-commit install

# Run linting
flake8 src/ discord_bot/

# Format code
black src/ discord_bot/

# Sort imports
isort src/ discord_bot/
```

## 📊 Monitoring & Maintenance

### **Automated Tasks**
- **Active Futures Sync**: Every 5 minutes
- **Daily Sync**: Every 24 hours
- **Transaction History**: Every 1 hour
- **PnL Backfill**: Every 1 hour
- **Stop-Loss Audit**: Every 30 minutes
- **Orphaned Orders Cleanup**: Every 2 hours
- **Balance Sync**: Every 5 minutes

### **Health Monitoring**
- **Service Status**: Real-time health checks
- **Database Connectivity**: Connection pool monitoring
- **Exchange API Status**: API rate limit tracking
- **Performance Metrics**: Response times and throughput
- **Error Rates**: Exception tracking and alerting

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For support and questions:
- **Documentation**: Check the `/docs` folder
- **Issues**: Use GitHub Issues for bug reports
- **Discussions**: Use GitHub Discussions for questions
- **Logs**: Check application logs for troubleshooting
