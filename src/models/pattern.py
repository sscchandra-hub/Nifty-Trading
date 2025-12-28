"""
Pattern detection data models.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class PatternType(Enum):
    """Pattern types for detection"""
    SIDEWAYS_SURGE = "sideways_surge"
    REVERSAL = "reversal"
    ACCELERATION = "acceleration"
    BREAKOUT = "breakout"
    CONSOLIDATION = "consolidation"
    DIVERGENCE = "divergence"
    MOMENTUM_SHIFT = "momentum_shift"
    VOLUME_SPIKE = "volume_spike"


class Direction(Enum):
    """Market direction"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class PatternMatch:
    """A single pattern match from historical data"""
    timestamp: datetime
    pattern_type: PatternType
    similarity_score: float
    outcome: Optional[Direction] = None
    price_change: Optional[float] = None
    success: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'pattern_type': self.pattern_type.value,
            'similarity_score': self.similarity_score,
            'outcome': self.outcome.value if self.outcome else None,
            'price_change': self.price_change,
            'success': self.success
        }


@dataclass
class PatternSignal:
    """Trading signal generated from pattern detection"""
    timestamp: datetime
    index_name: str
    pattern_type: PatternType
    direction: Direction
    confidence: float
    success_rate: float
    match_count: int
    historical_matches: List[PatternMatch]

    # Entry details
    entry_price: float
    atm_strike: int
    recommended_strike: int
    option_type: str  # CE or PE

    # Context
    spot_price: float
    ce_flow: float
    pe_flow: float
    net_flow: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'index_name': self.index_name,
            'pattern_type': self.pattern_type.value,
            'direction': self.direction.value,
            'confidence': self.confidence,
            'success_rate': self.success_rate,
            'match_count': self.match_count,
            'entry_price': self.entry_price,
            'atm_strike': self.atm_strike,
            'recommended_strike': self.recommended_strike,
            'option_type': self.option_type,
            'spot_price': self.spot_price,
            'ce_flow': self.ce_flow,
            'pe_flow': self.pe_flow,
            'net_flow': self.net_flow
        }

    @property
    def is_strong_signal(self) -> bool:
        """Check if this is a strong signal"""
        return (
            self.confidence >= 0.8
            and self.success_rate >= 0.7
            and self.match_count >= 5
        )

    @property
    def is_valid_signal(self) -> bool:
        """Check if signal meets minimum requirements"""
        return (
            self.confidence >= 0.6
            and self.success_rate >= 0.6
            and self.match_count >= 3
        )


@dataclass
class OIData:
    """Open Interest data for an option"""
    strike: int
    option_type: str  # CE or PE
    oi: int
    oi_change: int
    volume: int
    price: float
    iv: Optional[float] = None

    @property
    def oi_volume_ratio(self) -> float:
        """OI to volume ratio"""
        if self.volume == 0:
            return 0
        return self.oi / self.volume

    def is_liquid(self, min_oi: int, min_volume: int) -> bool:
        """Check if option is liquid"""
        return self.oi >= min_oi and self.volume >= min_volume
