# Cryptocurrency Exchange Bot

A Python-based cryptocurrency exchange bot that provides a unified interface for interacting with different cryptocurrency exchanges. The bot is built with asynchronous operations in mind and provides a robust foundation for implementing exchange-specific functionality.

## Features

- Abstract base class for exchange implementations
- Asynchronous operations for better performance
- Comprehensive error handling and logging
- Type hints for better code maintainability
- Support for multiple exchange implementations
- Balance checking functionality
- Order creation and management
- Symbol information retrieval
- **Multi-Exchange Support**:
  - YoBit (Centralized Exchange)
  - Uniswap (Decentralized Exchange)
- **Advanced DEX Trading Features**:
  - Smart gas price strategies (slow, medium, fast, aggressive)
  - Automatic transaction recovery and retry mechanisms
  - EIP-1559 transaction support
  - Secure encrypted private key management
  - Support for 25+ popular ERC-20 tokens

## Prerequisites

- Python 3.7 or higher
- pip (Python package installer)
- Virtual environment (recommended)
- Telegram API credentials (for signal monitoring)
- YoBit API credentials (for CEX trading)
- An Infura API key (for DEX trading)
- Ethereum wallet with private key (for DEX trading)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/BrianElionDev/BuyBot.git
cd telegram-bot
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Linux/Mac
# or
.\venv\Scripts\activate  # On Windows
```

3. Install the required dependencies:
```bash
pip install -r requirements.txt
```

4. Run the program
```bash
 python3 main.py ```

## Configuration

1. Set up your environment configuration by copying the example file:

```bash
cp example.env .env
```

2. Edit the `.env` file with your configuration details:

```properties
# For Telegram
TELEGRAM_API_ID=your_telegram_api_id
TELEGRAM_API_HASH=your_telegram_api_hash
TELEGRAM_PHONE=your_phone_number
# ... other Telegram settings

# For YoBit (CEX)
YOBIT_API_KEY=your_yobit_api_key
YOBIT_API_SECRET=your_yobit_api_secret

# For Uniswap (DEX) - New!
INFURA_PROJECT_ID=your_infura_project_id
ETHEREUM_NETWORK=mainnet  # or sepolia/goerli for testing
WALLET_ADDRESS=your_ethereum_wallet_address  # Public address
WALLET_PRIVATE_KEY=your_wallet_private_key  # Keep secure!
```

3. Configure exchange preferences in `.env`:

```properties
# Choose your preferred exchange type
PREFERRED_EXCHANGE_TYPE=cex  # or "dex" for Uniswap
```

For detailed instructions on setting up DEX trading with Uniswap, see [UNISWAP_INTEGRATION.md](UNISWAP_INTEGRATION.md).

## Trading Modes

The bot now supports two trading modes:

1. **CEX Trading (Default)**: Uses YoBit exchange to execute trades via API calls
2. **DEX Trading (New)**: Uses Uniswap on Ethereum blockchain to execute on-chain trades

You can switch between modes by changing the `PREFERRED_EXCHANGE_TYPE` setting or by updating the telegram_monitor.py implementation to determine the appropriate exchange based on the signal.

## Project Structure

```
telegram-bot/
├── exchanges/
│   ├── __init__.py
│   └── base_exchange.py
├── requirements.txt
└── README.md
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
