#!/bin/bash
"""
Auto Balance Fetcher Runner Script

Simple shell script to run the auto balance fetcher.
"""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

echo -e "${BLUE}🚀 Balance Update Runner${NC}"
echo "=================================="

# Function to run a command and check its exit status
run_command() {
    local cmd="$1"
    local description="$2"
    
    echo -e "${YELLOW}Running: $description${NC}"
    echo "Command: $cmd"
    echo "----------------------------------------"
    
    if eval "$cmd"; then
        echo -e "${GREEN}✅ $description completed successfully${NC}"
        return 0
    else
        echo -e "${RED}❌ $description failed${NC}"
        return 1
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --test             Run tests only"
    echo "  --daemon           Run as daemon service"
    echo "  --once             Run once and exit"
    echo "  --show-stored      Show currently stored balances"
    echo "  --dry-run          Show what would be updated without storing"
    echo "  --interval SECONDS Set update interval for daemon mode (default: 300)"
    echo "  --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --once                    # Run balance update once"
    echo "  $0 --test                    # Run tests"
    echo "  $0 --daemon                  # Run as daemon service"
    echo "  $0 --daemon --interval 600   # Run daemon with 10-minute intervals"
}

# Parse command line arguments
TEST_ONLY=false
DAEMON_MODE=false
ONCE_MODE=false
SHOW_STORED=false
DRY_RUN=false
INTERVAL=300

while [[ $# -gt 0 ]]; do
    case $1 in
        --test)
            TEST_ONLY=true
            shift
            ;;
        --daemon)
            DAEMON_MODE=true
            shift
            ;;
        --once)
            ONCE_MODE=true
            shift
            ;;
        --show-stored)
            SHOW_STORED=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_usage
            exit 1
            ;;
    esac
done

# Change to project root directory
cd "$PROJECT_ROOT" || {
    echo -e "${RED}❌ Failed to change to project root directory${NC}"
    exit 1
}

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 is not installed or not in PATH${NC}"
    exit 1
fi

# Check if required Python packages are available
echo -e "${YELLOW}Checking Python dependencies...${NC}"
python3 -c "import asyncio, aiohttp, supabase" 2>/dev/null || {
    echo -e "${RED}❌ Required Python packages not found. Please install requirements.txt${NC}"
    echo "Run: pip install -r requirements.txt"
    exit 1
}

# Run tests
if [ "$TEST_ONLY" = true ]; then
    echo -e "${BLUE}🧪 Running Auto Balance Fetcher Tests${NC}"
    echo "=========================================="
    
    run_command "python3 scripts/account_management/balance_scripts/test_auto_fetch.py" "Auto Balance Fetcher Tests"
    exit $?
fi

# Prepare command arguments
ARGS=""
if [ "$ONCE_MODE" = true ]; then
    ARGS="$ARGS --once"
fi

if [ "$DAEMON_MODE" = true ]; then
    ARGS="$ARGS --daemon"
    ARGS="$ARGS --interval $INTERVAL"
fi

if [ "$SHOW_STORED" = true ]; then
    ARGS="$ARGS --show-stored"
fi

if [ "$DRY_RUN" = true ]; then
    ARGS="$ARGS --dry-run"
fi

# Run auto balance fetcher
echo -e "${BLUE}🔄 Running Auto Balance Fetcher${NC}"
echo "================================="

run_command "python3 scripts/account_management/balance_scripts/auto_fetch_balances.py $ARGS" "Auto Balance Fetcher"

echo -e "${GREEN}🎉 Balance update process completed${NC}"
