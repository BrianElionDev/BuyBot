import asyncio
import logging
import os
import time
from typing import Optional, Dict, Any, List, Tuple, Union, Callable
from web3.types import TxParams
from concurrent.futures import ThreadPoolExecutor
from web3 import Web3
from web3.middleware.geth_poa import geth_poa_middleware
from web3.exceptions import TransactionNotFound, ContractLogicError, TimeExhausted
from config import settings as config
from src.exchange.transaction_manager import TransactionManager

logger = logging.getLogger(__name__)

# Simplified Uniswap V2 Router ABI (only the functions we need)
UNISWAP_ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactETHForTokens",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForETH",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# Simplified ERC20 ABI for approvals and balance checks
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    }
]

class UniswapExchange:
    """
    Handles interaction with Uniswap via Infura for DEX trading operations.
    This class encapsulates all Ethereum blockchain interactions via web3.py.
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Initialize the Uniswap exchange with Infura connection and wallet."""
        if not config.INFURA_PROJECT_ID or not config.WALLET_PRIVATE_KEY:
            raise ValueError("INFURA_PROJECT_ID and WALLET_PRIVATE_KEY must be set in configuration")

        # Initialize Web3 with Infura
        self.w3 = Web3(Web3.HTTPProvider(config.INFURA_URL))
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to Ethereum node via Infura: {config.INFURA_URL}")

        # Add PoA middleware for testnets
        if config.ETHEREUM_NETWORK.lower() not in ["mainnet"]:
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)

        # Set up wallet and contract
        if not config.WALLET_ADDRESS:
            raise ValueError("WALLET_ADDRESS must be set in configuration")
        self.wallet_address = Web3.to_checksum_address(config.WALLET_ADDRESS)
        self.private_key = config.WALLET_PRIVATE_KEY
        self.router_address = Web3.to_checksum_address(config.UNISWAP_ROUTER_ADDRESS)
        self.router_contract = self.w3.eth.contract(
            address=self.router_address,
            abi=UNISWAP_ROUTER_ABI
        )

        # For async operations
        self.loop = loop if loop else asyncio.get_event_loop()

        # Initialize transaction manager for error recovery
        self.tx_manager = TransactionManager(
            self.w3,
            max_retries=int(os.getenv("TX_MAX_RETRIES", "3")),
            retry_delay=int(os.getenv("TX_RETRY_DELAY", "5"))
        )

        # ThreadPoolExecutor for blocking calls
        self.executor = ThreadPoolExecutor(max_workers=5)

        logger.info(f"UniswapExchange initialized for wallet {self.wallet_address[:6]}...{self.wallet_address[-4:]} on {config.ETHEREUM_NETWORK}")
        logger.info(f"Connected to Infura: {self.w3.is_connected()}")

    def _get_token_contract(self, token_address: str):
        """Get a contract interface for an ERC20 token."""
        return self.w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_ABI
        )

    async def _run_in_executor(self, func, *args, **kwargs):
        """Run a synchronous web3 call in the executor to avoid blocking."""
        return await self.loop.run_in_executor(
            None,
            lambda: func(*args, **kwargs)
        )

    async def get_token_decimals(self, token_address: str) -> int:
        """Get the number of decimals for a token."""
        token_contract = self._get_token_contract(token_address)
        try:
            return await self._run_in_executor(token_contract.functions.decimals().call)
        except Exception as e:
            logger.error(f"Error getting decimals for token {token_address}: {e}")
            return 18  # Default to 18 decimals as fallback

    async def get_eth_balance(self) -> float:
        """Get ETH balance of the wallet in ether units."""
        try:
            balance_wei = await self._run_in_executor(
                self.w3.eth.get_balance,
                self.wallet_address
            )
            return float(self.w3.from_wei(balance_wei, 'ether'))
        except Exception as e:
            logger.error(f"Error getting ETH balance: {e}")
            return 0.0

    async def get_token_balance(self, token_address: str) -> float:
        """Get token balance of the wallet in token units."""
        token_contract = self._get_token_contract(token_address)
        try:
            decimals = await self.get_token_decimals(token_address)
            balance_atomic = await self._run_in_executor(
                token_contract.functions.balanceOf(self.wallet_address).call
            )
            return float(balance_atomic / (10**decimals))
        except Exception as e:
            logger.error(f"Error getting balance for token {token_address}: {e}")
            return 0.0

    async def get_token_price(self, token_address: str, in_usd: bool = True) -> Optional[float]:
        """
        Get token price in USD or ETH.

        Args:
            token_address: Address of the token
            in_usd: If True, get price in USD (via USDC), else in ETH

        Returns:
            Float price or None if error
        """
        quote_token = config.USDC_ADDRESS if in_usd else config.WETH_ADDRESS

        try:
            # Get price for 1 full token
            token_decimals = await self.get_token_decimals(token_address)
            one_token = 10**token_decimals

            path = [Web3.to_checksum_address(token_address), Web3.to_checksum_address(quote_token)]

            amounts_out = await self._run_in_executor(
                self.router_contract.functions.getAmountsOut(one_token, path).call
            )

            quote_token_decimals = await self.get_token_decimals(quote_token)
            price = amounts_out[1] / (10**quote_token_decimals)

            logger.info(f"Token {token_address} price: {price} {'USD' if in_usd else 'ETH'}")
            return price
        except Exception as e:
            logger.error(f"Error getting token price for {token_address}: {e}")
            return None

    async def estimate_gas_price(self) -> Union[int, Dict[str, int]]:
        """
        Get appropriate gas price based on network conditions and chosen strategy.

        Returns:
            Either a single gas price value (for legacy transactions) or
            a dict with maxFeePerGas and maxPriorityFeePerGas (for EIP-1559)
        """
        try:
            # If a specific gas price is set, use that directly
            if config.DEFAULT_GAS_PRICE_GWEI.lower() != 'auto':
                gas_price_wei = self.w3.to_wei(float(config.DEFAULT_GAS_PRICE_GWEI), 'gwei')
                if config.USE_EIP1559:
                    return {
                        'maxFeePerGas': gas_price_wei,
                        'maxPriorityFeePerGas': self.w3.to_wei(1, 'gwei')  # Minimum priority fee
                    }
                return gas_price_wei

            # Get current network gas prices
            base_fee = await self._get_base_fee()

            # Apply strategy-based adjustments
            strategy = config.GAS_STRATEGY.lower()
            adjustment = float(config.GAS_PRICE_ADJUSTMENT)

            # Strategy multipliers
            strategy_multipliers = {
                'slow': 0.9,      # Below average - for non-urgent transactions
                'medium': 1.0,    # Average - default
                'fast': 1.2,      # Above average - for timely execution
                'aggressive': 1.5  # High priority - for urgent transactions
            }

            multiplier = strategy_multipliers.get(strategy, 1.0) * adjustment

            if config.USE_EIP1559:
                return await self._get_eip1559_fees(base_fee, multiplier)
            else:
                # Legacy transaction pricing
                gas_price = int(base_fee * multiplier)
                return gas_price
        except Exception as e:
            logger.error(f"Error estimating gas price, using default: {e}")
            # Fallback to a reasonable gas price
            if config.USE_EIP1559:
                return {
                    'maxFeePerGas': self.w3.to_wei(30, 'gwei'),
                    'maxPriorityFeePerGas': self.w3.to_wei(1, 'gwei')
                }
            return self.w3.to_wei(20, 'gwei')  # Fallback to 20 gwei

    async def _get_base_fee(self) -> int:
        """Get the current base fee from the network."""
        try:
            # Get the latest block
            latest_block = await self._run_in_executor(self.w3.eth.get_block, 'latest')

            # For EIP-1559 compatible networks, use baseFeePerGas
            if hasattr(latest_block, 'baseFeePerGas'):
                return latest_block.baseFeePerGas

            # For non-EIP-1559 networks, fall back to gas_price
            return await self._run_in_executor(self.w3.eth.gas_price)
        except Exception as e:
            logger.error(f"Error getting base fee: {e}")
            return self.w3.to_wei(15, 'gwei')  # Reasonable fallback

    async def _get_eip1559_fees(self, base_fee: int, multiplier: float = 1.0) -> Dict[str, int]:
        """
        Calculate appropriate maxFeePerGas and maxPriorityFeePerGas for EIP-1559 transactions.

        Args:
            base_fee: Current base fee in wei
            multiplier: Strategy-based multiplier

        Returns:
            Dict with maxFeePerGas and maxPriorityFeePerGas
        """
        try:
            # Get max priority fee per gas from custom settings or network
            if config.MAX_PRIORITY_FEE.lower() == "auto":
                # Get fee history to estimate an appropriate priority fee
                fee_history = await self._run_in_executor(
                    self.w3.eth.fee_history,
                    5,  # Get data from last 5 blocks
                    'latest',
                    [10]  # 10th percentile of priority fees
                )

                # Calculate average priority fee from fee history
                priority_fees = [reward[0] for reward in fee_history['reward'] if reward]
                if priority_fees:
                    priority_fee = sum(priority_fees) // len(priority_fees)
                else:
                    # Default if we can't calculate
                    priority_fee = self.w3.to_wei(1.5, 'gwei')
            else:
                priority_fee = self.w3.to_wei(float(config.MAX_PRIORITY_FEE), 'gwei')

            # Apply strategy multiplier to priority fee
            priority_fee = int(priority_fee * multiplier)

            # Calculate max fee (base fee + priority fee with buffer)
            if config.MAX_FEE_PER_GAS.lower() == "auto":
                # 2x base fee should provide enough buffer for base fee increases
                max_fee = int(base_fee * 2 * multiplier) + priority_fee
            else:
                max_fee = self.w3.to_wei(float(config.MAX_FEE_PER_GAS), 'gwei')

            return {
                'maxFeePerGas': max_fee,
                'maxPriorityFeePerGas': priority_fee
            }
        except Exception as e:
            logger.error(f"Error calculating EIP-1559 fees: {e}")
            # Fallback values
            return {
                'maxFeePerGas': self.w3.to_wei(30, 'gwei'),
                'maxPriorityFeePerGas': self.w3.to_wei(1, 'gwei')
            }

    async def approve_token(self, token_address: str, amount: int = 0) -> bool:
        """
        Approve the Uniswap router to spend tokens.

        Args:
            token_address: Address of the token to approve
            amount: Amount to approve, or None for unlimited approval

        Returns:
            True if approval was successful, False otherwise
        """
        token_contract = self._get_token_contract(token_address)

        try:
            # Check current allowance
            current_allowance = await self._run_in_executor(
                token_contract.functions.allowance(self.wallet_address, self.router_address).call
            )

            # If amount specified and already approved enough, return True
            if amount and current_allowance >= amount:
                logger.info(f"Token {token_address} already has sufficient allowance: {current_allowance}")
                return True

            # For unlimited approval, use max uint256
            if amount is None:
                amount = 2**256 - 1

            logger.info(f"Approving {amount} of token {token_address} for Uniswap router")

            # Build the approval transaction
            tx_params = {
                'from': self.wallet_address,
                'nonce': await self._run_in_executor(
                    self.w3.eth.get_transaction_count,
                    self.wallet_address,
                    'pending'
                ),
                'chainId': await self._run_in_executor(self.w3.eth.chain_id)
            }

            # Add gas parameters based on transaction type (legacy or EIP-1559)
            gas_params = await self.estimate_gas_price()
            if isinstance(gas_params, dict):
                # EIP-1559 transaction
                tx_params.update(gas_params)
            else:
                # Legacy transaction
                tx_params['gasPrice'] = gas_params

            # Try to estimate gas for the approval
            try:
                gas_estimate = await self._run_in_executor(
                    token_contract.functions.approve(self.router_address, amount).estimate_gas,
                    {'from': self.wallet_address}
                )
                tx_params['gas'] = int(gas_estimate * 1.2)  # Add 20% buffer
            except Exception as e:
                logger.warning(f"Could not estimate gas for approval: {e}. Using default gas limit.")
                tx_params['gas'] = 100000  # Standard gas limit for approvals

            # Build, sign and send the transaction
            approve_tx = token_contract.functions.approve(
                self.router_address,
                amount
            ).build_transaction(TxParams(**tx_params))

            signed_tx = await self._run_in_executor(
                self.w3.eth.account.sign_transaction,
                approve_tx,
                self.private_key
            )

            tx_hash = await self._run_in_executor(
                self.w3.eth.send_raw_transaction,
                signed_tx.rawTransaction
            )

            logger.info(f"Approval transaction sent. TX hash: {tx_hash.hex()}")

            # Wait for receipt
            receipt = await self._run_in_executor(
                self.w3.eth.wait_for_transaction_receipt,
                tx_hash,
                timeout=180
            )

            if receipt.status == 1:
                logger.info(f"Token approval successful! Gas used: {receipt.gasUsed}")
                return True
            else:
                logger.error(f"Token approval failed! TX: {tx_hash.hex()}")
                return False

        except Exception as e:
            logger.error(f"Error approving token {token_address}: {e}")
            return False

    async def get_swap_quote(
        self,
        sell_token_address: str,
        buy_token_address: str,
        amount_in_atomic: int
    ) -> Optional[int]:
        """
        Get quote for swap (estimate how much buy_token will be received).

        Args:
            sell_token_address: Address of token to sell
            buy_token_address: Address of token to buy
            amount_in_atomic: Amount of sell_token in its smallest unit

        Returns:
            Expected amount of buy_token in its smallest unit, or None on error
        """
        path = [
            Web3.to_checksum_address(sell_token_address),
            Web3.to_checksum_address(buy_token_address)
        ]

        # For token-to-token swaps when neither is ETH/WETH, we may need to route through WETH
        if (sell_token_address.lower() != config.WETH_ADDRESS.lower() and
            buy_token_address.lower() != config.WETH_ADDRESS.lower()):
            path = [
                Web3.to_checksum_address(sell_token_address),
                Web3.to_checksum_address(config.WETH_ADDRESS),
                Web3.to_checksum_address(buy_token_address)
            ]

        try:
            amounts_out = await self._run_in_executor(
                self.router_contract.functions.getAmountsOut(amount_in_atomic, path).call
            )

            # The last element is the expected output amount
            expected_amount_out = amounts_out[-1]

            logger.info(f"Swap quote: {amount_in_atomic} of {sell_token_address} -> {expected_amount_out} of {buy_token_address}")
            return expected_amount_out

        except Exception as e:
            logger.error(f"Error getting swap quote: {e}")
            return None

    async def execute_swap(
        self,
        sell_token_address: str,
        buy_token_address: str,
        amount_in_atomic: int,
        slippage_percentage: float = 0
    ) -> bool:
        """
        Execute a swap on Uniswap.

        Args:
            sell_token_address: Address of token to sell
            buy_token_address: Address of token to buy
            amount_in_atomic: Amount of sell_token in its smallest unit
            slippage_percentage: Optional custom slippage percentage (overrides config)

        Returns:
            True if swap was successful, False otherwise
        """
        slippage_percentage = slippage_percentage if slippage_percentage is not None else config.DEX_SLIPPAGE_PERCENTAGE

        # Determine what kind of swap we're doing
        is_selling_eth = sell_token_address.lower() == config.WETH_ADDRESS.lower()
        is_buying_eth = buy_token_address.lower() == config.WETH_ADDRESS.lower()

        # Create path based on token pair
        path = [
            Web3.to_checksum_address(sell_token_address),
            Web3.to_checksum_address(buy_token_address)
        ]

        # For token-to-token swaps when neither is ETH/WETH, route through WETH
        if not is_selling_eth and not is_buying_eth:
            path = [
                Web3.to_checksum_address(sell_token_address),
                Web3.to_checksum_address(config.WETH_ADDRESS),
                Web3.to_checksum_address(buy_token_address)
            ]

        # Get expected output amount
        expected_output_atomic = await self.get_swap_quote(sell_token_address, buy_token_address, amount_in_atomic)
        if not expected_output_atomic:
            logger.error("Failed to get swap quote")
            return False

        # Calculate minimum output with slippage
        min_output_atomic = int(expected_output_atomic * (1 - (slippage_percentage / 100)))

        logger.info(f"Swap parameters: Selling {amount_in_atomic} of {sell_token_address}")
        logger.info(f"Expected output: {expected_output_atomic} of {buy_token_address}")
        logger.info(f"Minimum output with {slippage_percentage}% slippage: {min_output_atomic}")

        # Set transaction deadline (10 minutes from now)
        deadline = int(time.time()) + 600  # 10 minutes

        try:
            # If selling an ERC20 token, approve it first
            if not is_selling_eth:
                logger.info(f"Approving {sell_token_address} for swap")
                approved = await self.approve_token(sell_token_address, amount_in_atomic)
                if not approved:
                    logger.error(f"Failed to approve {sell_token_address} for swap")
                    return False
                # Wait a bit for approval to be confirmed
                await asyncio.sleep(5)

            # Prepare transaction parameters
            tx_params = {
                'from': self.wallet_address,
                'nonce': await self._run_in_executor(
                    self.w3.eth.get_transaction_count,
                    self.wallet_address,
                    'pending'
                ),
                'chainId': await self._run_in_executor(self.w3.eth.chain_id)
            }

            # Add gas parameters based on transaction type (legacy or EIP-1559)
            gas_params = await self.estimate_gas_price()
            if isinstance(gas_params, dict):
                # EIP-1559 transaction
                tx_params.update(gas_params)
            else:
                # Legacy transaction
                tx_params['gasPrice'] = gas_params

            # Add value if selling ETH
            if is_selling_eth:
                tx_params['value'] = amount_in_atomic

            # Build the swap transaction based on type
            if is_selling_eth:
                # ETH -> Token
                swap_function = self.router_contract.functions.swapExactETHForTokens(
                    min_output_atomic,
                    path,
                    self.wallet_address,
                    deadline
                )
                logger.info("Using swapExactETHForTokens")
            elif is_buying_eth:
                # Token -> ETH
                swap_function = self.router_contract.functions.swapExactTokensForETH(
                    amount_in_atomic,
                    min_output_atomic,
                    path,
                    self.wallet_address,
                    deadline
                )
                logger.info("Using swapExactTokensForETH")
            else:
                # Token -> Token
                swap_function = self.router_contract.functions.swapExactTokensForTokens(
                    amount_in_atomic,
                    min_output_atomic,
                    path,
                    self.wallet_address,
                    deadline
                )
                logger.info("Using swapExactTokensForTokens")

            # Estimate gas
            try:
                gas_estimate = await self._run_in_executor(
                    swap_function.estimate_gas,
                    tx_params
                )
                tx_params['gas'] = int(gas_estimate * 1.2)  # Add 20% buffer

                # Ensure gas is within limits
                if tx_params['gas'] > config.MAX_GAS_LIMIT:
                    logger.warning(f"Estimated gas {tx_params['gas']} exceeds MAX_GAS_LIMIT. Capping at {config.MAX_GAS_LIMIT}.")
                    tx_params['gas'] = config.MAX_GAS_LIMIT

            except Exception as e:
                logger.warning(f"Could not estimate gas: {e}. Using default gas limit.")
                tx_params['gas'] = 300000  # Conservative default

            swap_tx = swap_function.build_transaction(TxParams(**tx_params))  # type: ignore

            # Sign and send transaction
            signed_tx = await self._run_in_executor(
                self.w3.eth.account.sign_transaction,
                swap_tx,
                self.private_key
            )

            tx_hash = await self._run_in_executor(
                self.w3.eth.send_raw_transaction,
                signed_tx.rawTransaction
            )

            logger.info(f"Swap transaction sent. TX hash: {tx_hash.hex()}")

            # Wait for transaction to be mined
            receipt = await self._run_in_executor(
                self.w3.eth.wait_for_transaction_receipt,
                tx_hash,
                timeout=300  # 5 minutes timeout
            )

            if receipt.status == 1:
                logger.info(f"Swap successful! Gas used: {receipt.gasUsed}")
                return True
            else:
                logger.error(f"Swap failed! TX: {tx_hash.hex()}")
                return False

        except TransactionNotFound as e:
            logger.error(f"Transaction not found: {e}")
            return False
        except ContractLogicError as e:
            logger.error(f"Contract error in swap: {e}")
            return False
        except Exception as e:
            logger.error(f"Error executing swap: {e}")
            return False

    async def close(self):
        """Close any resources (nothing to do for Web3)."""
        logger.info("Closing UniswapExchange resources")
