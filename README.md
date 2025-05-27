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

## Prerequisites

- Python 3.7 or higher
- pip (Python package installer)
- Virtual environment (recommended)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
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

## Project Structure

```
telegram-bot/
├── exchanges/
│   ├── __init__.py
│   └── base_exchange.py
├── requirements.txt
└── README.md
```

## Usage

The `BaseExchange` class provides an abstract interface for implementing exchange-specific functionality. Here's a basic example of how to use it:

```python
from exchanges.base_exchange import BaseExchange

class MyExchange(BaseExchange):
    async def get_balance(self):
        # Implement exchange-specific balance checking
        pass

    async def create_order(self, pair, order_type, amount, price):
        # Implement exchange-specific order creation
        pass

    async def get_symbol_info(self, symbol):
        # Implement exchange-specific symbol info retrieval
        pass
```

## Available Methods

### get_balance()
- Asynchronously retrieves all balances for all currencies
- Returns a dictionary with currency symbols as keys and balance amounts as values
- Returns None on failure

### create_order(pair, order_type, amount, price)
- Creates a buy or sell order on the exchange
- Parameters:
  - pair (str): Trading pair (e.g., 'btc_usd')
  - order_type (str): 'buy' or 'sell'
  - amount (float): Amount to trade
  - price (float): Price for the order
- Returns order details dictionary or None on failure

### get_symbol_info(symbol)
- Retrieves information about a specific trading symbol/pair
- Returns symbol information dictionary or None on failure

## Error Handling

The base implementation includes comprehensive error handling:
- Input validation for all parameters
- Exception catching and logging
- Graceful failure handling with None returns

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
