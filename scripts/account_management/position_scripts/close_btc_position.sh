#!/bin/bash

# BTC Position Closure Script Wrapper
# This script sets the PYTHONPATH and runs the close_all_positions.py script with --btc-only flag

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Get the project root (3 levels up from this script)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Set PYTHONPATH to include the project root
export PYTHONPATH="$PROJECT_ROOT"

# Change to project root directory
cd "$PROJECT_ROOT"

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Run the BTC position closure script
python scripts/account_management/position_scripts/close_all_positions.py --btc-only

# Deactivate virtual environment if it was activated
if [ -n "$VIRTUAL_ENV" ]; then
    deactivate
fi
