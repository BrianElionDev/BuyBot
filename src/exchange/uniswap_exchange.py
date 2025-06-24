import asyncio
import logging
import os
import time
from typing import Optional, Dict, Any, List, Tuple, Union, Callable
from web3.types import TxParams
from concurrent.futures import ThreadPoolExecutor
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
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
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForTokensSupportingFeeOnTransferTokens",
        "outputs": [],
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
            self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

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
            return self.w3.eth.gas_price
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

    async def approve_token(self, token_address: str, amount: int = 0) -> Tuple[bool, Optional[str]]:
        """
        Approve a token for spending by the Uniswap router.

        Args:
            token_address: The address of the ERC20 token to approve.
            amount: The amount to approve, in atomic units. Defaults to infinite.

        Returns:
            A tuple (bool, Optional[str]) indicating success and an optional failure reason.
        """
        token_address_cs = Web3.to_checksum_address(token_address)
        token_contract = self._get_token_contract(token_address_cs)

        # Use a very large number for "infinite" approval if amount is not specified
        approve_amount = amount if amount > 0 else 2**256 - 1
        logger.info(f"Approving {approve_amount} of {token_address_cs} for router {self.router_address}")

        try:
            # Check current allowance
            allowance = await self._run_in_executor(
                token_contract.functions.allowance(self.wallet_address, self.router_address).call
            )

            if allowance >= approve_amount:
                logger.info("Sufficient allowance already exists.")
                return True, None

            # Prepare the transaction
            tx_params: Dict[str, Any] = {
                'from': self.wallet_address,
                'nonce': await self._run_in_executor(
                    self.w3.eth.get_transaction_count,
                    self.wallet_address,
                    'pending'
                ),
                'chainId': self.w3.eth.chain_id
            }

            gas_params = await self.estimate_gas_price()
            if isinstance(gas_params, dict):
                tx_params.update(gas_params)
            else:
                tx_params['gasPrice'] = gas_params

            approve_function = token_contract.functions.approve(self.router_address, approve_amount)

            # Estimate gas
            try:
                gas_estimate = await self._run_in_executor(approve_function.estimate_gas, tx_params)
                tx_params['gas'] = int(gas_estimate * 1.2)
            except Exception as e:
                logger.warning(f"Could not estimate gas for approval: {e}. Using default.")
                tx_params['gas'] = 100000

            # Build, sign, and send the transaction using the transaction manager
            tx_hash, error_reason = await self.tx_manager.send_transaction(
                approve_function,
                tx_params,
                self.private_key,
                self.estimate_gas_price,
                self._run_in_executor,
            )

            if tx_hash and not error_reason:
                logger.info(f"Approval transaction successful with hash: {tx_hash}")
                return True, None
            else:
                logger.error(f"Approval transaction failed: {error_reason}")
                return False, error_reason

        except ContractLogicError as e:
            reason = f"Contract logic error during approval: {e}"
            logger.error(reason)
            return False, reason
        except Exception as e:
            reason = f"An unexpected error occurred during token approval: {e}"
            logger.error(reason)
            return False, reason

    async def execute_swap(
        self,
        sell_token_address: str,
        buy_token_address: str,
        amount_in_atomic: int,
        slippage_percentage: float = 0
    ) -> Tuple[bool, Optional[str]]:
        """
        Execute a swap on Uniswap V2.

        Args:
            sell_token_address: Address of the token being sold.
            buy_token_address: Address of the token being bought.
            amount_in_atomic: The amount of `sell_token` to swap, in its smallest unit.
            slippage_percentage: The allowed slippage percentage.

        Returns:
            A tuple of (bool, Optional[str]) indicating success and an optional failure reason.
        """
        logger.info(
            f"Executing swap: {amount_in_atomic} of {sell_token_address} for {buy_token_address} "
            f"with {slippage_percentage}% slippage"
        )

        # Standardize addresses
        sell_token_address = Web3.to_checksum_address(sell_token_address)
        buy_token_address = Web3.to_checksum_address(buy_token_address)
        is_selling_eth = sell_token_address.lower() == config.WETH_ADDRESS.lower()
        is_buying_eth = buy_token_address.lower() == config.WETH_ADDRESS.lower()

        # Build path and get quote, trying direct path first, then routing through WETH for token-to-token
        path = [sell_token_address, buy_token_address]

        try:
            logger.info(f"Attempting to get swap quote for direct path: {path}")
            amounts_out = await self._run_in_executor(
                self.router_contract.functions.getAmountsOut(amount_in_atomic, path).call
            )
            expected_output_atomic = amounts_out[-1]

        except Exception as e:
            logger.warning(f"Direct swap quote failed: {e}. This is often due to a lack of a direct liquidity pool. Checking for a WETH route.")
            # If direct fails and it's a token-to-token swap, try routing through WETH
            if not is_selling_eth and not is_buying_eth:
                path = [sell_token_address, Web3.to_checksum_address(config.WETH_ADDRESS), buy_token_address]
                logger.info(f"Attempting to get swap quote for WETH-routed path: {path}")
                try:
                    amounts_out = await self._run_in_executor(
                        self.router_contract.functions.getAmountsOut(amount_in_atomic, path).call
                    )
                    expected_output_atomic = amounts_out[-1]
                except Exception as e_routed:
                    reason = f"Failed to get swap quote, even via WETH: {e_routed}"
                    logger.error(reason)
                    return False, reason
            else:
                reason = f"Failed to get swap quote from Uniswap: {e}"
                logger.error(reason)
                return False, reason

        # Calculate minimum output with slippage
        min_output_atomic = int(expected_output_atomic * (1 - slippage_percentage / 100))

        logger.info(f"Expected output: {expected_output_atomic} of {buy_token_address}")
        logger.info(f"Minimum output with {slippage_percentage}% slippage: {min_output_atomic}")

        # Set transaction deadline (10 minutes from now)
        deadline = int(time.time()) + 600  # 10 minutes

        try:
            # If selling an ERC20 token, approve it first
            if not is_selling_eth:
                logger.info(f"Approving {sell_token_address} for swap")
                approved, reason = await self.approve_token(sell_token_address, amount_in_atomic)
                if not approved:
                    logger.error(f"Failed to approve {sell_token_address} for swap: {reason}")
                    return False, f"Approval failed: {reason}"
                # Wait a bit for approval to be confirmed
                await asyncio.sleep(5)

            # Prepare transaction parameters
            tx_params: Dict[str, Any] = {
                'from': self.wallet_address,
                'nonce': await self._run_in_executor(
                    self.w3.eth.get_transaction_count,
                    self.wallet_address,
                    'pending'
                ),
                'chainId': self.w3.eth.chain_id
            }

            # Add gas parameters
            gas_params = await self.estimate_gas_price()
            if isinstance(gas_params, dict):
                tx_params.update(gas_params)
            else:
                tx_params['gasPrice'] = gas_params

            # Add value if selling ETH
            if is_selling_eth:
                tx_params['value'] = amount_in_atomic

            # Build the swap transaction based on type
            swap_function: Callable
            if is_selling_eth:
                swap_function = self.router_contract.functions.swapExactETHForTokens(
                    min_output_atomic, path, self.wallet_address, deadline
                )
                logger.info("Using swapExactETHForTokens")
            elif is_buying_eth:
                swap_function = self.router_contract.functions.swapExactTokensForETH(
                    amount_in_atomic, min_output_atomic, path, self.wallet_address, deadline
                )
                logger.info("Using swapExactTokensForETH")
            else:
                swap_function = self.router_contract.functions.swapExactTokensForTokens(
                    amount_in_atomic, min_output_atomic, path, self.wallet_address, deadline
                )
                logger.info("Using swapExactTokensForTokens")

            # Estimate gas
            try:
                gas_estimate = await self._run_in_executor(swap_function.estimate_gas, tx_params)
                tx_params['gas'] = int(gas_estimate * 1.2)

                if tx_params['gas'] > config.MAX_GAS_LIMIT:
                    logger.warning(f"Estimated gas {tx_params['gas']} exceeds MAX_GAS_LIMIT. Capping at {config.MAX_GAS_LIMIT}.")
                    tx_params['gas'] = config.MAX_GAS_LIMIT
            except Exception as e:
                logger.warning(f"Could not estimate gas for {swap_function.fn_name}: {e}.")
                # For token-to-token, try the fee-on-transfer version as a fallback
                if not is_selling_eth and not is_buying_eth:
                    logger.info("Attempting gas estimation with swapExactTokensForTokensSupportingFeeOnTransferTokens.")
                    try:
                        swap_function = self.router_contract.functions.swapExactTokensForTokensSupportingFeeOnTransferTokens(
                            amount_in_atomic, min_output_atomic, path, self.wallet_address, deadline
                        )
                        logger.info("Using swapExactTokensForTokensSupportingFeeOnTransferTokens")
                        gas_estimate = await self._run_in_executor(swap_function.estimate_gas, tx_params)
                        tx_params['gas'] = int(gas_estimate * 1.2)
                    except Exception as e_fee:
                        logger.error(f"Gas estimation failed for both standard and fee-on-transfer swaps: {e_fee}. Using default.")
                        tx_params['gas'] = 300000
                else:
                    logger.warning("Using default gas limit.")
                    tx_params['gas'] = 300000

            # Send transaction using the transaction manager for retries
            tx_hash, error_reason = await self.tx_manager.send_transaction(
                swap_function,
                tx_params,
                self.private_key,
                self.estimate_gas_price,
                self._run_in_executor,
            )

            if tx_hash and not error_reason:
                logger.info(f"Swap transaction successful with hash: {tx_hash}")
                return True, None
            else:
                logger.error(f"Swap transaction failed: {error_reason}")
                return False, error_reason

        except ContractLogicError as e:
            reason = f"Swap failed due to contract logic: {e}"
            logger.error(reason)
            return False, reason
        except Exception as e:
            reason = f"An unexpected error occurred during swap: {e}"
            logger.error(reason, exc_info=True)
            return False, reason

    async def close(self):
        """Clean up resources, like the thread pool executor."""
        logger.info("Closing UniswapExchange resources")
