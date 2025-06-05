#!/usr/bin/env python3
"""
Transaction manager for Ethereum blockchain transactions.
Provides retry mechanisms, transaction monitoring, and error recovery.
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable, Union, Tuple
from web3 import Web3
from web3.exceptions import TransactionNotFound, TimeExhausted

logger = logging.getLogger(__name__)

class TransactionManager:
    """Manages Ethereum blockchain transactions with retry and error recovery."""

    def __init__(self, w3: Web3, max_retries: int = 3, retry_delay: int = 5):
        """
        Initialize the transaction manager.

        Args:
            w3: Web3 instance
            max_retries: Maximum number of retry attempts
            retry_delay: Base delay between retries in seconds
        """
        self.w3 = w3
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def execute_with_retry(
        self,
        transaction_func: Callable,
        transaction_args: Dict[str, Any],
        private_key: str,
        gas_price_func: Callable,
        run_in_executor: Callable,
        handle_nonce: bool = True
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Execute a transaction with automatic retry logic.

        Args:
            transaction_func: Function that builds the transaction
            transaction_args: Arguments for the transaction
            private_key: Private key to sign the transaction
            gas_price_func: Function to estimate gas price
            run_in_executor: Function to run blocking calls in executor
            handle_nonce: Whether to handle nonce increments between retries

        Returns:
            Tuple of (success, transaction_hash, receipt)
        """
        attempt = 0
        tx_hash = None
        tx_receipt = None
        last_error = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                # If this isn't the first attempt, wait with exponential backoff
                if attempt > 1:
                    backoff_time = self.retry_delay * (2 ** (attempt - 1))
                    logger.info(f"Retry attempt {attempt}/{self.max_retries} after {backoff_time} seconds")
                    await asyncio.sleep(backoff_time)

                # Update nonce for retry attempts
                if handle_nonce and attempt > 1:
                    transaction_args['nonce'] = await run_in_executor(
                        self.w3.eth.get_transaction_count,
                        transaction_args['from'],
                        'pending'
                    )

                # Update gas price for retry attempts
                if attempt > 1:
                    gas_params = await gas_price_func()
                    # Handle both legacy and EIP-1559 transactions
                    if isinstance(gas_params, dict):
                        transaction_args.update(gas_params)
                    else:
                        transaction_args['gasPrice'] = int(gas_params * 1.1 ** (attempt - 1))  # Increase by 10% each retry

                # Build and sign the transaction
                transaction = transaction_func(transaction_args)
                signed_tx = await run_in_executor(
                    self.w3.eth.account.sign_transaction,
                    transaction,
                    private_key
                )

                # Send the transaction
                tx_hash = await run_in_executor(
                    self.w3.eth.send_raw_transaction,
                    signed_tx.rawTransaction
                )

                logger.info(f"Transaction sent (attempt {attempt}). TX hash: {tx_hash.hex()}")

                # Wait for transaction to be mined
                tx_receipt = await self._wait_for_transaction(tx_hash, run_in_executor)

                if tx_receipt['status'] == 1:
                    logger.info(f"Transaction successful! Gas used: {tx_receipt.get('gasUsed')}")
                    return True, tx_hash.hex(), tx_receipt
                else:
                    logger.error(f"Transaction failed with status 0. TX hash: {tx_hash.hex()}")
                    last_error = f"Transaction reverted. TX hash: {tx_hash.hex()}"
                    # Don't retry failed transactions - if status is 0, the contract reverted
                    return False, tx_hash.hex(), tx_receipt

            except TransactionNotFound as e:
                logger.warning(f"Transaction not found (attempt {attempt}): {e}")
                last_error = str(e)
                # This could mean the transaction was dropped, so we retry
                continue

            except TimeExhausted as e:
                logger.warning(f"Transaction timeout (attempt {attempt}): {e}")
                last_error = str(e)
                # If transaction timed out but was submitted, check status
                if tx_hash:
                    try:
                        tx_receipt = await self._check_transaction_status(tx_hash, run_in_executor)
                        if tx_receipt:
                            if tx_receipt['status'] == 1:
                                logger.info(f"Transaction was actually successful! Gas used: {tx_receipt.get('gasUsed')}")
                                return True, tx_hash.hex(), tx_receipt
                    except Exception:
                        pass  # Continue with retry if checking fails
                continue

            except Exception as e:
                logger.error(f"Transaction error (attempt {attempt}): {e}")
                last_error = str(e)

                # Check if error is about nonce being too low
                if "nonce too low" in str(e).lower():
                    if handle_nonce:
                        logger.info("Nonce too low, will update on next retry")
                        continue
                    else:
                        logger.error("Nonce too low and handle_nonce is disabled")
                        return False, None, None

                # Check if error is about insufficient funds
                if "insufficient funds" in str(e).lower():
                    logger.error("Insufficient funds for transaction")
                    return False, None, None  # Don't retry

                # Continue with retry for other errors
                continue

        # If we get here, all retry attempts have failed
        logger.error(f"All {self.max_retries} transaction attempts failed. Last error: {last_error}")
        return False, tx_hash.hex() if tx_hash else None, tx_receipt

    async def _wait_for_transaction(self, tx_hash, run_in_executor) -> Dict[str, Any]:
        """Wait for transaction to be mined with tiered timeout strategy."""
        try:
            # First try with a shorter timeout
            return await run_in_executor(
                self.w3.eth.wait_for_transaction_receipt,
                tx_hash,
                timeout=60  # 1 minute initial timeout
            )
        except TimeExhausted:
            logger.info("Initial wait timed out, checking transaction status...")
            # If timeout, check if transaction is still pending
            return await self._check_transaction_status(tx_hash, run_in_executor)

    async def _check_transaction_status(self, tx_hash, run_in_executor) -> Optional[Dict[str, Any]]:
        """
        Check the status of a transaction that timed out.
        Implements a polling strategy with increasing intervals.
        """
        logger.info(f"Checking status of transaction {tx_hash.hex()}...")

        # Check transaction status with increasing polling intervals
        polling_intervals = [30, 60, 120]  # 30s, 1min, 2min
        max_check_time = 600  # 10 minutes total
        start_time = time.time()

        for interval in polling_intervals:
            try:
                receipt = await run_in_executor(
                    self.w3.eth.get_transaction_receipt,
                    tx_hash
                )

                if receipt:
                    logger.info(f"Transaction found: status={receipt.status}")
                    return receipt

            except Exception as e:
                logger.warning(f"Error checking transaction: {e}")

            # Check if we've exceeded the maximum check time
            if time.time() - start_time > max_check_time:
                logger.error(f"Exceeded maximum check time for transaction {tx_hash.hex()}")
                break

            # Wait before next check
            logger.info(f"Transaction not yet mined, waiting {interval} seconds...")
            await asyncio.sleep(interval)

        # If we get here, transaction status could not be determined
        logger.error(f"Could not determine status of transaction {tx_hash.hex()}")
        raise TimeExhausted(f"Transaction {tx_hash.hex()} status could not be determined")

    async def get_optimal_gas_parameters(
        self,
        transaction_func: Callable,
        transaction_args: Dict[str, Any],
        run_in_executor: Callable
    ) -> Dict[str, Any]:
        """
        Determine optimal gas parameters for a transaction.

        Args:
            transaction_func: Function that builds the transaction
            transaction_args: Arguments for the transaction
            run_in_executor: Function to run blocking calls in executor

        Returns:
            Dict with gas parameters
        """
        try:
            # Copy transaction args to avoid modifying the original
            test_args = transaction_args.copy()

            # Remove any existing gas parameters
            for param in ['gas', 'gasPrice', 'maxFeePerGas', 'maxPriorityFeePerGas']:
                if param in test_args:
                    del test_args[param]

            # Estimate gas
            gas_estimate = await run_in_executor(
                transaction_func(test_args).estimate_gas,
                {'from': test_args['from']}
            )

            # Add 20% buffer
            return {'gas': int(gas_estimate * 1.2)}
        except Exception as e:
            logger.warning(f"Error estimating optimal gas: {e}")
            # Return conservative default
            return {'gas': 300000}
