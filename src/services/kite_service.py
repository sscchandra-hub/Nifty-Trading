"""
KiteConnect API service wrapper with error handling and retry logic.
"""
import time
from typing import Dict, List, Optional
from kiteconnect import KiteConnect
from kiteconnect.exceptions import KiteException
import pandas as pd

from src.config.settings import APIConfig, TradingConfig
from src.utils.exceptions import (
    KiteConnectionError,
    KiteAuthenticationError,
    RateLimitError,
    InstrumentNotFoundError
)
from src.utils.logging_config import get_logger

logger = get_logger('trading_system.api.kite')


class KiteService:
    """
    Wrapper for KiteConnect API with error handling and retry logic.
    """

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Initialize Kite service.

        Args:
            api_key: Kite API key (defaults to config)
            api_secret: Kite API secret (defaults to config)
        """
        self.api_key = api_key or APIConfig.KITE_API_KEY
        self.api_secret = api_secret or APIConfig.KITE_API_SECRET

        if not self.api_key or not self.api_secret:
            raise KiteAuthenticationError("API key and secret must be provided")

        self.kite = KiteConnect(api_key=self.api_key)
        self._access_token: Optional[str] = None
        self._instruments_cache: Optional[pd.DataFrame] = None

        logger.info("KiteService initialized")

    @property
    def is_authenticated(self) -> bool:
        """Check if service is authenticated"""
        return self._access_token is not None

    def authenticate(self, request_token: str) -> str:
        """
        Authenticate with request token.

        Args:
            request_token: Request token from Kite login

        Returns:
            Access token

        Raises:
            KiteAuthenticationError: If authentication fails
        """
        try:
            data = self.kite.generate_session(request_token, api_secret=self.api_secret)
            self._access_token = data["access_token"]
            self.kite.set_access_token(self._access_token)

            logger.info("Successfully authenticated with Kite")
            return self._access_token

        except KiteException as e:
            logger.error(f"Authentication failed: {e}")
            raise KiteAuthenticationError(f"Failed to authenticate: {e}")

    def set_access_token(self, access_token: str):
        """
        Set access token directly (for cached tokens).

        Args:
            access_token: Previously generated access token
        """
        self._access_token = access_token
        self.kite.set_access_token(access_token)
        logger.info("Access token set")

    def get_quote(
        self,
        instruments: List[str],
        max_retries: int = None
    ) -> Dict:
        """
        Get quotes for instruments with retry logic.

        Args:
            instruments: List of instrument tokens or symbols
            max_retries: Maximum retry attempts (defaults to config)

        Returns:
            Dictionary of quotes

        Raises:
            KiteConnectionError: If request fails after retries
            RateLimitError: If rate limit exceeded
        """
        max_retries = max_retries or TradingConfig.MAX_RETRIES
        retry_delay = 1  # Start with 1 second

        for attempt in range(max_retries):
            try:
                quotes = self.kite.quote(instruments)
                return quotes

            except KiteException as e:
                if "rate limit" in str(e).lower():
                    raise RateLimitError(f"Rate limit exceeded: {e}", retry_after=60)

                if attempt < max_retries - 1:
                    logger.warning(
                        f"Quote request failed (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Quote request failed after {max_retries} attempts")
                    raise KiteConnectionError(f"Failed to get quotes: {e}")

            except Exception as e:
                logger.error(f"Unexpected error getting quotes: {e}")
                raise KiteConnectionError(f"Unexpected error: {e}")

    def get_instruments(
        self,
        exchange: Optional[str] = None,
        force_refresh: bool = False
    ) -> pd.DataFrame:
        """
        Get instruments list with caching.

        Args:
            exchange: Filter by exchange (e.g., 'NFO', 'NSE')
            force_refresh: Force refresh from API

        Returns:
            DataFrame of instruments

        Raises:
            KiteConnectionError: If request fails
        """
        # Return cached if available and not forcing refresh
        if self._instruments_cache is not None and not force_refresh:
            if exchange:
                return self._instruments_cache[
                    self._instruments_cache['exchange'] == exchange
                ].copy()
            return self._instruments_cache.copy()

        try:
            logger.info("Fetching instruments from Kite API...")
            instruments = self.kite.instruments(exchange)
            df = pd.DataFrame(instruments)

            # Cache all instruments
            if exchange is None:
                self._instruments_cache = df

            logger.info(f"Fetched {len(df)} instruments" + (f" from {exchange}" if exchange else ""))
            return df

        except KiteException as e:
            logger.error(f"Failed to fetch instruments: {e}")
            raise KiteConnectionError(f"Failed to fetch instruments: {e}")

    def find_instrument(
        self,
        tradingsymbol: str,
        exchange: str = "NFO"
    ) -> Optional[Dict]:
        """
        Find instrument by trading symbol.

        Args:
            tradingsymbol: Trading symbol (e.g., 'NIFTY23DEC19250CE')
            exchange: Exchange (default: NFO)

        Returns:
            Instrument dict or None if not found

        Raises:
            InstrumentNotFoundError: If instrument not found
        """
        instruments = self.get_instruments(exchange)
        result = instruments[instruments['tradingsymbol'] == tradingsymbol]

        if result.empty:
            logger.warning(f"Instrument not found: {tradingsymbol} on {exchange}")
            raise InstrumentNotFoundError(f"{tradingsymbol} on {exchange}")

        return result.iloc[0].to_dict()

    def get_ltp(self, instruments: List[str]) -> Dict[str, float]:
        """
        Get Last Traded Price for instruments.

        Args:
            instruments: List of instrument identifiers

        Returns:
            Dictionary mapping instrument to LTP
        """
        quotes = self.get_quote(instruments)
        return {
            key: data.get('last_price', 0)
            for key, data in quotes.items()
        }

    def get_ohlc(self, instruments: List[str]) -> Dict:
        """
        Get OHLC data for instruments.

        Args:
            instruments: List of instrument identifiers

        Returns:
            Dictionary of OHLC data
        """
        try:
            return self.kite.ohlc(instruments)
        except KiteException as e:
            logger.error(f"Failed to get OHLC: {e}")
            raise KiteConnectionError(f"Failed to get OHLC: {e}")

    def batch_quote(
        self,
        instruments: List[str],
        batch_size: int = None
    ) -> Dict:
        """
        Get quotes in batches to handle large lists.

        Args:
            instruments: List of instrument identifiers
            batch_size: Size of each batch (defaults to config)

        Returns:
            Combined dictionary of all quotes
        """
        batch_size = batch_size or TradingConfig.QUOTE_BATCH_SIZE
        all_quotes = {}

        # Split into batches
        for i in range(0, len(instruments), batch_size):
            batch = instruments[i:i + batch_size]
            quotes = self.get_quote(batch)
            all_quotes.update(quotes)

            # Small delay between batches to avoid rate limiting
            if i + batch_size < len(instruments):
                time.sleep(0.1)

        logger.debug(f"Fetched quotes for {len(all_quotes)} instruments in batches")
        return all_quotes

    def get_profile(self) -> Dict:
        """
        Get user profile.

        Returns:
            Profile dictionary

        Raises:
            KiteAuthenticationError: If not authenticated
        """
        if not self.is_authenticated:
            raise KiteAuthenticationError("Not authenticated")

        try:
            return self.kite.profile()
        except KiteException as e:
            logger.error(f"Failed to get profile: {e}")
            raise KiteConnectionError(f"Failed to get profile: {e}")

    def get_margins(self) -> Dict:
        """
        Get account margins.

        Returns:
            Margins dictionary
        """
        try:
            return self.kite.margins()
        except KiteException as e:
            logger.error(f"Failed to get margins: {e}")
            raise KiteConnectionError(f"Failed to get margins: {e}")


# Singleton instance
_kite_service_instance: Optional[KiteService] = None


def get_kite_service() -> KiteService:
    """
    Get singleton KiteService instance.

    Returns:
        KiteService instance
    """
    global _kite_service_instance

    if _kite_service_instance is None:
        _kite_service_instance = KiteService()

    return _kite_service_instance


def initialize_kite_service(api_key: str = None, api_secret: str = None) -> KiteService:
    """
    Initialize or reinitialize KiteService.

    Args:
        api_key: Kite API key
        api_secret: Kite API secret

    Returns:
        KiteService instance
    """
    global _kite_service_instance
    _kite_service_instance = KiteService(api_key, api_secret)
    return _kite_service_instance
