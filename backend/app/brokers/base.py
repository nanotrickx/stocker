import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional

class BaseBroker(ABC):
    @abstractmethod
    async def login(self, credentials: Dict[str, Any]) -> bool:
        """Authenticate with the broker using credentials."""
        pass

    @abstractmethod
    async def get_profile(self) -> Dict[str, Any]:
        """Fetch unified user profile, margins, and available funds."""
        pass

    @abstractmethod
    async def get_live_quotes(self, symbols: List[str]) -> Dict[str, Any]:
        """Fetch current LTP (Last Traded Price) and OHLC for symbols."""
        pass

    @abstractmethod
    async def place_order(self, strategy_id: str, symbol: str, transaction_type: str, 
                            quantity: int, option_type: Optional[str] = None, 
                            strike_price: Optional[float] = None, expiry: Optional[str] = None,
                            price: Optional[float] = None, instance_id: Optional[int] = None) -> Dict[str, Any]:
        """Place an order and return unified trade information."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        pass

    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch unified open positions."""
        pass

    @abstractmethod
    async def get_ltp(self, symbol: str) -> float:
        """Fetch unified Last Traded Price (LTP) for a symbol."""
        pass
