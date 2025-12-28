"""
Trading engine state management.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List
import threading
import pandas as pd
from kiteconnect import KiteConnect


@dataclass
class EngineState:
    """Main trading engine state"""

    # API
    kite: Optional[KiteConnect] = None

    # Threading
    polling_thread: Optional[threading.Thread] = None
    stop_flag: bool = False
    polling_active: bool = False

    # Instruments data
    ins_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    token_meta: pd.DataFrame = field(default_factory=pd.DataFrame)
    subscribe_tokens: List[int] = field(default_factory=list)

    # Tracked symbols
    indices_with_fo: List[str] = field(default_factory=list)
    stocks_with_fo: List[str] = field(default_factory=list)

    # Timing
    last_poll_time: Optional[datetime] = None
    chart_update_counter: int = 0

    # Cached data
    cached_prev_close: Dict[str, float] = field(default_factory=dict)
    first_15min_range: Dict[str, Dict] = field(default_factory=dict)
    range_status: Dict[str, str] = field(default_factory=dict)
    futures_volume_history: Dict[str, List] = field(default_factory=dict)

    # Pattern detection
    pattern_enabled: bool = True
    last_pattern_alert: Dict[str, datetime] = field(default_factory=dict)
    last_stock_alert: Dict[str, datetime] = field(default_factory=dict)

    # Nifty futures
    nifty_fut_token: Optional[int] = None
    nifty_fut_symbol: str = ""
    nifty_fut_expiry: str = ""

    def reset_daily_data(self):
        """Reset data that should be cleared on new trading day"""
        self.cached_prev_close.clear()
        self.first_15min_range.clear()
        self.range_status.clear()
        self.futures_volume_history.clear()
        self.chart_update_counter = 0

    def is_initialized(self) -> bool:
        """Check if engine is properly initialized"""
        return (
            self.kite is not None
            and not self.ins_df.empty
            and not self.token_meta.empty
            and len(self.subscribe_tokens) > 0
        )

    def get_index_metadata(self, index_name: str) -> pd.DataFrame:
        """Get metadata for a specific index"""
        if self.token_meta.empty:
            return pd.DataFrame()

        return self.token_meta[
            (self.token_meta.get("index_name") == index_name)
            | (self.token_meta.get("name") == index_name)
        ].copy()


@dataclass
class FuturesContract:
    """Futures contract information"""
    token: int
    symbol: str
    expiry: str
    name: str
    lot_size: int = 1

    @classmethod
    def from_dataframe_row(cls, row: pd.Series) -> 'FuturesContract':
        """Create from pandas Series (DataFrame row)"""
        return cls(
            token=int(row['instrument_token']),
            symbol=row['tradingsymbol'],
            expiry=row['expiry'],
            name=row['name'],
            lot_size=int(row.get('lot_size', 1))
        )


@dataclass
class OptionsChain:
    """Options chain for a specific expiry"""
    underlying: str
    expiry: str
    strikes: List[int] = field(default_factory=list)
    calls: Dict[int, int] = field(default_factory=dict)  # strike -> token
    puts: Dict[int, int] = field(default_factory=dict)  # strike -> token

    def get_atm_strikes(self, spot_price: float, count: int = 5) -> List[int]:
        """Get N strikes around ATM"""
        if not self.strikes:
            return []

        # Find closest strike
        atm_strike = min(self.strikes, key=lambda s: abs(s - spot_price))
        atm_index = self.strikes.index(atm_strike)

        # Get strikes around ATM
        half = count // 2
        start = max(0, atm_index - half)
        end = min(len(self.strikes), atm_index + half + 1)

        return self.strikes[start:end]


@dataclass
class MarketQuote:
    """Market quote for an instrument"""
    token: int
    last_price: float
    volume: int
    oi: Optional[int] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    change: Optional[float] = None
    change_percent: Optional[float] = None

    @property
    def bid_ask_spread(self) -> Optional[float]:
        """Calculate bid-ask spread percentage"""
        if self.bid and self.ask and self.bid > 0:
            return ((self.ask - self.bid) / self.bid) * 100
        return None

    @classmethod
    def from_kite_quote(cls, token: int, quote: Dict) -> 'MarketQuote':
        """Create from Kite Connect quote dictionary"""
        return cls(
            token=token,
            last_price=quote.get('last_price', 0),
            volume=quote.get('volume', 0),
            oi=quote.get('oi'),
            bid=quote.get('depth', {}).get('buy', [{}])[0].get('price') if quote.get('depth') else None,
            ask=quote.get('depth', {}).get('sell', [{}])[0].get('price') if quote.get('depth') else None,
            change=quote.get('net_change'),
            change_percent=quote.get('change')
        )
