#!/bin/bash

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create necessary directories
mkdir -p logs

# Copy environment file if it doesn't exist
if [ ! -f ".env" ] && [ -f "example.env" ]; then
    echo "Creating .env file from template..."
    cp example.env .env
    echo "Please update .env with your configuration"
fi

# Ask if user wants to set up secure key management
read -p "Do you want to set up secure key management for DEX trading? (y/n): " setup_keys
if [ "$setup_keys" = "y" ]; then
    echo "Setting up secure key management..."
    python scripts/initialize_key_manager.py
fi

# Ask if user wants to test DEX integration on testnet
read -p "Do you want to test the DEX integration on Ethereum testnet? (y/n): " test_dex
if [ "$test_dex" = "y" ]; then
    # Temporarily modify .env to use testnet
    if [ -f ".env" ]; then
        sed -i 's/ETHEREUM_NETWORK="mainnet"/ETHEREUM_NETWORK="sepolia"/' .env
        echo "Running DEX integration test on Sepolia testnet..."
        python tests/test_ethereum_testnet.py
        # Restore mainnet setting
        sed -i 's/ETHEREUM_NETWORK="sepolia"/ETHEREUM_NETWORK="mainnet"/' .env
    else
        echo "Skipping testnet test - .env file not found"
    fi
fi

echo "Setup complete! Don't forget to:"
echo "1. Update .env with your configuration"
echo "2. Ensure you have funds in your wallet for trading"
echo "3. Activate the virtual environment with: source venv/bin/activate"
echo ""
echo "For DEX trading documentation, see UNISWAP_INTEGRATION.md"