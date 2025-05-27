from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

class BaseExchange(ABC):
  """
  Abstract Base Class for cryptocurrency exchange interactions.
  It defines the common interface that all exchange implementations must adhere to
  """

  def __init__(self):
    self.logger = logging.getLogger(self.__class__.__name__)

  @abstractmethod
  async def get_balance(self) -> Optional[Dict[str, float]]:
    """"
    Asynchronously get all balances for all currencies
    Returns a dictionary where the keys are currency symbols and values.
    Returns none on failure
    """
    try:
      # This is an abstract method that should be implemented by child classes
      raise NotImplementedError("get_balance() must be implemented by child classes")
    except Exception as e:
      self.logger.error(f"Error getting balance: {str(e)}")
      return None


  async def create_order(self, pair: str, order_type: str, amount: float, price: float) -> Optional[Dict[str, Any]]:
    """
    Asynchronously creates a buy or sell order on the exchange.
    Args:
      pair (str): The trading pair (e.g. 'btc_usd')
      order_type (str): The type of order ('buy' or 'sell').
      amount 'float'): The amount of the base to buy/sell.
      price (float): The price at which to place the order.

    Returns:
      Optional[Dict[str, Any]]: A dictionary containing the order details if successful, None
    """
    try:
      # Validate input parameters
      if not isinstance(pair, str) or not pair:
        raise ValueError("Invalid trading pair")
      if order_type not in ['buy', 'sell']:
        raise ValueError("Order type must be either 'buy' or 'sell'")
      if not isinstance(amount, (int, float)) or amount <= 0:
        raise ValueError("Amount must be a positive number")
      if not isinstance(price, (int, float)) or price <= 0:
        raise ValueError("Price must be a positive number")

      # This is an abstract method that should be implemented by child classes
      raise NotImplementedError("create_order() must be implemented by child classes")
    except Exception as e:
      self.logger.error(f"Error creating order: {str(e)}")
      return None

  async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
    """
    Asynchronous retrieves information about a specific trading symbol/pair.
    This can include minimum trade amounts, precision, etc.
    Returns None on Failure
    """
    try:
      # Validate input parameter
      if not isinstance(symbol, str) or not symbol:
        raise ValueError("Invalid trading symbol")

      # This is an abstract method that should be implemented by child classes
      raise NotImplementedError("get_symbol_info() must be implemented by child classes")
    except Exception as e:
      self.logger.error(f"Error getting symbol info: {str(e)}")
      return None