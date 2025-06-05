import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE")
TARGET_GROUP_ID = int(os.getenv("TARGET_GROUP_ID", "0"))
NOTIFICATION_GROUP_ID = int(os.getenv("NOTIFICATION_GROUP_ID", "0"))

# YoBit
YOBIT_API_KEY = os.getenv("YOBIT_API_KEY")
YOBIT_API_SECRET = os.getenv("YOBIT_API_SECRET")

# Infura & Web3
INFURA_PROJECT_ID = os.getenv("INFURA_PROJECT_ID")
ETHEREUM_NETWORK = os.getenv("ETHEREUM_NETWORK", "mainnet")
INFURA_URL = f"https://{ETHEREUM_NETWORK}.infura.io/v3/{INFURA_PROJECT_ID}" if INFURA_PROJECT_ID else None
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY")

# Uniswap Configuration
UNISWAP_ROUTER_ADDRESS = os.getenv("UNISWAP_ROUTER_ADDRESS", "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D")  # V2 Router
WETH_ADDRESS = os.getenv("WETH_ADDRESS", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")  # Mainnet WETH
USDC_ADDRESS = os.getenv("USDC_ADDRESS", "0xA0b86991c6218b36c1d19D4a2e9Eb0ce3606eb48")  # Mainnet USDC

# Token Address Mapping (for DEX operations)
TOKEN_ADDRESS_MAP = {
    # Base assets
    "ETH": WETH_ADDRESS,
    "WETH": WETH_ADDRESS,
    "USDC": USDC_ADDRESS,

    # Stablecoins
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # Tether USD
    "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",  # Dai Stablecoin
    "TUSD": "0x0000000000085d4780B73119b644AE5ecd22b376",  # TrueUSD
    "BUSD": "0x4Fabb145d64652a948d72533023f6E7A623C7C53",  # Binance USD

    # DeFi tokens
    "UNI": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",  # Uniswap
    "AAVE": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",  # Aave
    "COMP": "0xc00e94Cb662C3520282E6f5717214004A7f26888",  # Compound
    "MKR": "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2",  # Maker
    "SNX": "0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6F",  # Synthetix
    "SUSHI": "0x6B3595068778DD592e39A122f4f5a5cF09C90fE2",  # SushiSwap

    # Layer 2 and Scaling Solutions
    "MATIC": "0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0",  # Polygon/Matic
    "LRC": "0xBBbbCA6A901c926F240b89EacB641d8Aec7AEafD",  # Loopring
    "OMG": "0xd26114cd6EE289AccF82350c8d8487fedB8A0C07",  # OMG Network

    # Large Market Cap Tokens
    "LINK": "0x514910771AF9Ca656af840dff83E8264EcF986CA",  # Chainlink
    "SHIB": "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE",  # Shiba Inu
    "GRT": "0xc944E90C64B2c07662A292be6244BDf05Cda44a7",  # The Graph
    "CRV": "0xD533a949740bb3306d119CC777fa900bA034cd52",  # Curve DAO Token
    "1INCH": "0x111111111117dC0aa78b770fA6A738034120C302",  # 1inch

    # Gaming & Metaverse
    "AXS": "0xBB0E17EF65F82Ab018d8EDd776e8DD940327B28b",  # Axie Infinity
    "MANA": "0x0F5D2fB29fb7d3CFeE444a200298f468908cC942",  # Decentraland
    "SAND": "0x3845badAde8e6dFF049820680d1F14bD3903a5d0",  # The Sandbox
    "ENJ": "0xF629cBd94d3791C9250152BD8dfBDF380E2a3B9c"   # Enjin Coin
}

# DEX Trading Parameters
DEX_SLIPPAGE_PERCENTAGE = float(os.getenv("DEX_SLIPPAGE_PERCENTAGE", "1.0"))
DEFAULT_GAS_PRICE_GWEI = os.getenv("DEFAULT_GAS_PRICE_GWEI", "auto")  # 'auto' or specific value
MAX_GAS_LIMIT = int(os.getenv("MAX_GAS_LIMIT", "500000"))
PREFERRED_EXCHANGE_TYPE = os.getenv("PREFERRED_EXCHANGE_TYPE", "cex")  # 'cex', 'dex', or 'auto'

# Advanced Gas Strategy Parameters
GAS_STRATEGY = os.getenv("GAS_STRATEGY", "medium")  # 'slow', 'medium', 'fast', 'aggressive'
GAS_PRICE_ADJUSTMENT = float(os.getenv("GAS_PRICE_ADJUSTMENT", "1.1"))  # Multiplier for base gas price
MAX_FEE_PER_GAS = os.getenv("MAX_FEE_PER_GAS", "auto")  # For EIP-1559 transactions
MAX_PRIORITY_FEE = os.getenv("MAX_PRIORITY_FEE", "auto")  # For EIP-1559 transactions
USE_EIP1559 = os.getenv("USE_EIP1559", "true").lower() == "true"  # Whether to use EIP-1559 transactions

# Transaction Error Recovery
TX_MAX_RETRIES = int(os.getenv("TX_MAX_RETRIES", "3"))  # Maximum number of retry attempts
TX_RETRY_DELAY = int(os.getenv("TX_RETRY_DELAY", "5"))  # Base delay between retries (seconds)

# Trading
RISK_PERCENTAGE = float(os.getenv("RISK_PERCENTAGE", "2.0"))
MIN_TRADE_AMOUNT = float(os.getenv("MIN_TRADE_AMOUNT", "10.0"))
MAX_TRADE_AMOUNT = float(os.getenv("MAX_TRADE_AMOUNT", "100.0"))
PRICE_THRESHOLD = float(os.getenv("PRICE_THRESHOLD", "5.0"))  # % price difference
SLIPPAGE_PERCENTAGE = float(os.getenv("SLIPPAGE_PERCENTAGE", "20.0"))  # % slippage tolerance
TRADE_COOLDOWN = int(os.getenv("TRADE_COOLDOWN", "300"))  # seconds

# Setup logging
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('logs/trading_bot.log')
        ]
    )
    logging.getLogger('telethon').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)