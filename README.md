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

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
