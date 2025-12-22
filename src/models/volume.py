"""
Volume analysis data models.
"""
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
from typing import Dict, Any


@dataclass
class VolumeSpike:
    """Single volume spike event"""
    timestamp: datetime
    strike: int
    option_type: str  # CE or PE
    volume: int
    avg_volume: float
    spike_ratio: float
    is_atm: bool
    distance_from_atm: int
    alert_level: str  # STRONG/MODERATE/NORMAL

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'timestamp': self.timestamp,
            'strike': self.strike,
            'option_type': self.option_type,
            'volume': self.volume,
            'avg_volume': self.avg_volume,
            'spike_ratio': self.spike_ratio,
            'is_atm': self.is_atm,
            'distance_from_atm': self.distance_from_atm,
            'alert_level': self.alert_level
        }


@dataclass
class VolumeState:
    """Track volume analysis state"""
    spike_queue: deque = field(default_factory=lambda: deque(maxlen=50))
    ce_pe_history: deque = field(default_factory=lambda: deque(maxlen=60))  # 10 minutes
    timeline_data: deque = field(default_factory=lambda: deque(maxlen=180))  # 30 minutes
    intensity_history: deque = field(default_factory=lambda: deque(maxlen=180))  # 30 minutes
    volume_baseline: float = 0.0
    last_atm_strike: int = 0

    def reset(self):
        """Reset all state"""
        self.spike_queue.clear()
        self.ce_pe_history.clear()
        self.timeline_data.clear()
        self.intensity_history.clear()
        self.volume_baseline = 0.0
        self.last_atm_strike = 0


@dataclass
class CEPEData:
    """Call/Put flow data point"""
    timestamp: datetime
    ce_volume: int
    pe_volume: int

    @property
    def total_volume(self) -> int:
        """Total volume"""
        return self.ce_volume + self.pe_volume

    @property
    def ce_percentage(self) -> float:
        """CE as percentage of total"""
        if self.total_volume == 0:
            return 50.0
        return (self.ce_volume / self.total_volume) * 100

    @property
    def pe_percentage(self) -> float:
        """PE as percentage of total"""
        return 100.0 - self.ce_percentage

    @property
    def net_flow(self) -> int:
        """Net flow (CE - PE)"""
        return self.ce_volume - self.pe_volume
