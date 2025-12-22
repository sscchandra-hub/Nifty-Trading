# app.py - LIVE MOMENTUM TRADING SYSTEM - PHASE 1 COMPLETE
# ✅ K/M Number Formatting - Applied throughout dashboard
# ✅ Individual Index Momentum Trackers (5 separate sections)
# ✅ Interactive Nifty Charts (CE & PE Flow vs Spot Price)
# ✅ Historical Data Capture (CSV files per index per day)
# ✅ Real-time Delta Metrics (1min, 5min changes)
# ✅ Flow Acceleration Indicators
# ✅ Live Alerts & Entry Signals with Strike Prices
# ✅ Momentum Direction Tracking
# ✅ Actionable Trading Signals
# ✅ Range Breakout Strategy with Volume Confirmation

import os, json, time, threading, pickle, requests, csv
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from collections import deque
from typing import List, Dict, Optional, Tuple
import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from kiteconnect import KiteConnect
import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

# =========================
# CHART DEBUG LOGGING
# =========================
import logging

# Create debug log file for charts only
DEBUG_LOG_DIR = Path("data/debug")
DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_LOG_FILE = DEBUG_LOG_DIR / "charts_debug.log"

# Configure chart debug logger
chart_logger = logging.getLogger('chart_debug')
chart_logger.setLevel(logging.DEBUG)

# File handler
file_handler = logging.FileHandler(DEBUG_LOG_FILE, mode='a')
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s - %(message)s')
file_handler.setFormatter(file_formatter)

# Remove any existing handlers and add new one
chart_logger.handlers = []
chart_logger.addHandler(file_handler)
chart_logger.propagate = False

def log_chart_debug(message):
    """Log chart-specific debug messages to file only"""
    chart_logger.debug(message)
    # Windows-safe console output (no emojis to avoid encoding errors)
    try:
        safe_msg = message.encode('ascii', 'ignore').decode('ascii')
        print(f"[CHART]: {safe_msg}")
    except:
        print(f"[CHART]: {message}")


# Hybrid Pattern Matching + OI Integration (REQUIREMENT 3)
try:
    import sys
    sys.path.insert(0, '/mnt/user-data/outputs')
    from pattern_integration import run_pattern_detection, get_pattern_status
    PATTERNS_AVAILABLE = True
    print("✅ Hybrid pattern matching loaded (Patterns + OI)")
except Exception as e:
    PATTERNS_AVAILABLE = False
    print(f"⚠️ Pattern matching not available: {e}")


# =========================
# VOLUME CHARTS MODULE (REQUIREMENT 4)
# Integrated from volume_charts.py
# =========================

# =========================
# DATA STRUCTURES
# =========================


# ============================================================================
# SINGLETON THREAD PROTECTION - PREVENTS MULTIPLE POLLING THREADS
# ============================================================================
import atexit
_POLLING_LOCK_FILE = Path('.cache/polling.lock')
_POLLING_STARTED = False

def cleanup_lock():
    try:
        if _POLLING_LOCK_FILE.exists():
            _POLLING_LOCK_FILE.unlink()
    except:
        pass

atexit.register(cleanup_lock)
# ============================================================================

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
    
    def to_dict(self):
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

# ✅ FIX: Use session_state for volume_state (shared between polling thread and dashboard)
if 'volume_state' not in st.session_state:
    # Try to load from cache first
    volume_cache_file = Path('.cache/volume_state.pkl')
    if volume_cache_file.exists():
        try:
            with open(volume_cache_file, 'rb') as f:
                st.session_state.volume_state = pickle.load(f)
            print(f"✅ Loaded volume state from cache (ce_pe_history: {len(st.session_state.volume_state.ce_pe_history)} points)")
        except Exception as e:
            print(f"⚠️ Error loading volume cache: {e}")
            st.session_state.volume_state = VolumeState()
    else:
        st.session_state.volume_state = VolumeState()
volume_state = st.session_state.volume_state

# Initialize futures data in session state
if 'nifty_futures_data' not in st.session_state:
    st.session_state.nifty_futures_data = None

# =========================
# HELPER FUNCTIONS
# =========================

def format_number(num):
    """Format number in K/M notation"""
    if num is None:
        return "—"
    abs_num = abs(num)
    if abs_num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    elif abs_num >= 1_000:
        return f"{num/1_000:.1f}K"
    else:
        return f"{num:.0f}"

def calculate_atm_strike(spot_price: float, index_name: str) -> tuple:
    """Calculate ATM strike based on index name and spot price"""
    step_map = {
        "BANKNIFTY": 100, "NIFTY": 50, "FINNIFTY": 50, "MIDCPNIFTY": 25, "SENSEX": 100,
        # New indices (using reasonable defaults, adjust if needed)
        "NIFTY MIDCAP 50": 50, "NIFTY AUTO": 50, "NIFTY PHARMA": 50, 
        "NIFTY METAL": 50, "NIFTY ENERGY": 50, "NIFTY FMCG": 50,
        "NIFTY REALTY": 25, "NIFTY PSU BANK": 25, "NIFTY INFRA": 50, "NIFTY OIL & GAS": 50
    }
    step = step_map.get(index_name, 50)
    atm_strike = round(spot_price / step) * step
    return atm_strike, step

def get_alert_level(spike_ratio: float) -> Tuple[str, str, str]:
    """
    Get alert level based on spike ratio
    Returns: (level, emoji, color)
    """
    if spike_ratio >= 5.0:
        return "STRONG", "🔥", "#ff0000"
    elif spike_ratio >= 3.0:
        return "STRONG", "🔥", "#ff4444"
    elif spike_ratio >= 2.0:
        return "MODERATE", "🟡", "#ffaa00"
    else:
        return "NORMAL", "🟢", "#00aa00"

def get_strike_label(strike: int, atm_strike: int) -> str:
    """Get label for strike (ATM/OTM/ITM)"""
    diff = strike - atm_strike
    if diff == 0:
        return "ATM"
    elif abs(diff) >= 150:
        return f"Far {'OTM' if diff > 0 else 'ITM'}"
    elif diff > 0:
        return "OTM"
    else:
        return "ITM"

# =========================
# DATA COLLECTION
# =========================

def update_volume_data(kite, ins_df, index_name: str, spot_price: float, 
                       all_quotes: dict, token_meta: pd.DataFrame):
    """
    Update volume data from current poll
    
    Args:
        kite: KiteConnect instance
        ins_df: Instruments DataFrame
        index_name: Index name (NIFTY)
        spot_price: Current spot price
        all_quotes: All quotes from current poll
        token_meta: Token metadata DataFrame
    """
    try:
        log_chart_debug(f"update_volume_data START - index={index_name}, spot={spot_price:.2f}")
        
        # Calculate ATM strike (user's function returns tuple: atm_strike, step)
        atm_strike, step = calculate_atm_strike(spot_price, index_name)
        volume_state.last_atm_strike = atm_strike
        
        log_chart_debug(f"ATM strike = {atm_strike}, step = {step}")
        
        # Get ATM ± 2 strikes
        strikes_to_check = [
            atm_strike - 2*step,
            atm_strike - step,
            atm_strike,
            atm_strike + step,
            atm_strike + 2*step
        ]
        
        log_chart_debug(f"Strikes to check = {strikes_to_check}")
        
        # Collect volume data for each strike
        current_volumes = {}
        total_ce_volume = 0
        total_pe_volume = 0
        
        for strike in strikes_to_check:
            for option_type in ['CE', 'PE']:
                # Find option in token_meta
                option_data = token_meta[
                    (token_meta.get("index_name") == index_name) &
                    (token_meta.get("strike") == strike) &
                    (token_meta.get("type") == option_type)
                ]
                
                if option_data.empty:
                    continue
                
                token = int(option_data.iloc[0]["instrument_token"])
                token_str = str(token)
                
                if token_str in all_quotes:
                    volume = all_quotes[token_str].get("volume", 0)
                    current_volumes[(strike, option_type)] = volume
                    
                    if option_type == 'CE':
                        total_ce_volume += volume
                    else:
                        total_pe_volume += volume
        
        log_chart_debug(f"Collected volumes - CE={total_ce_volume}, PE={total_pe_volume}, entries={len(current_volumes)}")
        
        # Update CE/PE history (for race chart)
        volume_state.ce_pe_history.append({
            'timestamp': datetime.now(),
            'ce_volume': total_ce_volume,
            'pe_volume': total_pe_volume
        })
        
        # Calculate baseline if needed (first poll or every 60 polls)
        if volume_state.volume_baseline == 0 or len(volume_state.intensity_history) % 60 == 0:
            if len(volume_state.ce_pe_history) >= 5:
                recent_ce = [h['ce_volume'] for h in list(volume_state.ce_pe_history)[-5:]]
                recent_pe = [h['pe_volume'] for h in list(volume_state.ce_pe_history)[-5:]]
                volume_state.volume_baseline = np.mean(recent_ce + recent_pe)
        
        # Calculate intensity (for wave chart)
        total_volume = total_ce_volume + total_pe_volume
        if volume_state.volume_baseline > 0:
            intensity_ratio = total_volume / volume_state.volume_baseline
        else:
            intensity_ratio = 1.0
        
        volume_state.intensity_history.append({
            'timestamp': datetime.now(),
            'intensity': intensity_ratio
        })
        
        # Detect spikes (compare with 5-minute average)
        if len(volume_state.ce_pe_history) >= 30:  # Need 30 polls (5 minutes)
            for (strike, option_type), current_vol in current_volumes.items():
                # Get historical volume for this strike
                hist_volumes = []
                for i in range(max(0, len(volume_state.spike_queue) - 30), len(volume_state.spike_queue)):
                    if i < len(volume_state.spike_queue):
                        spike = list(volume_state.spike_queue)[i]
                        if spike.strike == strike and spike.option_type == option_type:
                            hist_volumes.append(spike.volume)
                
                # Calculate average
                if hist_volumes:
                    avg_vol = np.mean(hist_volumes)
                else:
                    # Use baseline estimate
                    avg_vol = volume_state.volume_baseline / (len(strikes_to_check) * 2)
                
                if avg_vol == 0:
                    avg_vol = 1000  # Minimum baseline
                
                # Calculate spike ratio
                spike_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
                
                # Only record if spike >= 2.0x
                if spike_ratio >= 2.0:
                    is_atm = (strike == atm_strike)
                    distance = strike - atm_strike
                    alert_level, _, _ = get_alert_level(spike_ratio)
                    
                    spike = VolumeSpike(
                        timestamp=datetime.now(),
                        strike=strike,
                        option_type=option_type,
                        volume=current_vol,
                        avg_volume=avg_vol,
                        spike_ratio=spike_ratio,
                        is_atm=is_atm,
                        distance_from_atm=distance,
                        alert_level=alert_level
                    )
                    
                    volume_state.spike_queue.append(spike)
                    
                    # 💾 SAVE SPIKE TO CSV FOR AI ANALYSIS
                    save_volume_spike_data(spike)
                    
                    # Add to timeline if spike >= 3.0x or is ATM
                    if spike_ratio >= 3.0 or is_atm:
                        volume_state.timeline_data.append(spike)
        
        # 💾 SAVE INTENSITY DATA TO CSV FOR AI ANALYSIS (every poll)
        save_volume_intensity_data(intensity_ratio, total_ce_volume, total_pe_volume)
        
        log_chart_debug(f"update_volume_data COMPLETE - intensity={intensity_ratio:.2f}x, baseline={volume_state.volume_baseline:.0f}")
        
        return True
    
    except Exception as e:
        log_chart_debug(f"ERROR in update_volume_data: {e}")
        import traceback
        log_chart_debug(f"Traceback: {traceback.format_exc()}")
        return False

# =========================
# CHART 1: VOLUME SPIKE HEATMAP
# =========================

def create_volume_spike_heatmap():
    """Create volume spike heatmap table"""
    try:
        if not volume_state.spike_queue:
            return None
        
        # Get last 10 spikes
        recent_spikes = list(volume_state.spike_queue)[-10:]
        recent_spikes.reverse()  # Newest first
        
        # Create DataFrame
        data = []
        for spike in recent_spikes:
            _, emoji, _ = get_alert_level(spike.spike_ratio)
            data.append({
                'Time': spike.timestamp.strftime('%H:%M:%S'),
                'Strike': f"{spike.strike}",
                'Type': spike.option_type,
                'Volume': format_number(spike.volume),
                'Spike': f"{spike.spike_ratio:.1f}x",
                'Alert': emoji
            })
        
        df = pd.DataFrame(data)
        return df
    
    except Exception as e:
        print(f"Error creating heatmap: {e}")
        return None

# =========================
# CHART 2: CE vs PE VOLUME RACE
# =========================

def create_ce_pe_race_chart():
    """Create CE vs PE volume race bar chart"""
    try:
        if len(volume_state.ce_pe_history) < 2:
            return None
        
        # Get last 60 polls (10 minutes)
        recent_data = list(volume_state.ce_pe_history)[-60:]
        
        # Calculate totals
        ce_total = sum(d['ce_volume'] for d in recent_data)
        pe_total = sum(d['pe_volume'] for d in recent_data)
        total = ce_total + pe_total
        
        if total == 0:
            return None
        
        ce_pct = (ce_total / total) * 100
        pe_pct = (pe_total / total) * 100
        net_flow = ce_total - pe_total
        
        # Calculate 10-min change
        if len(recent_data) >= 60:
            old_ce = recent_data[0]['ce_volume']
            old_pe = recent_data[0]['pe_volume']
            ce_change = ce_total - old_ce
            pe_change = pe_total - old_pe
        else:
            ce_change = 0
            pe_change = 0
        
        # Determine trend
        ce_trend = "↗️" if ce_change > pe_change else ("→" if abs(ce_change - pe_change) < 10000 else "↘️")
        pe_trend = "↗️" if pe_change > ce_change else ("→" if abs(ce_change - pe_change) < 10000 else "↘️")
        
        return {
            'ce_total': ce_total,
            'pe_total': pe_total,
            'ce_pct': ce_pct,
            'pe_pct': pe_pct,
            'net_flow': net_flow,
            'ce_change': ce_change,
            'pe_change': pe_change,
            'ce_trend': ce_trend,
            'pe_trend': pe_trend,
            'bias': 'BULLISH' if net_flow > 0 else ('BEARISH' if net_flow < 0 else 'NEUTRAL')
        }
    
    except Exception as e:
        print(f"Error creating race chart: {e}")
        return None

# =========================
# CHART 3: VOLUME SPIKE TIMELINE
# =========================

def create_volume_spike_timeline():
    """Create volume spike timeline scatter chart"""
    try:
        if not volume_state.timeline_data:
            return None
        
        # Prepare data
        timeline_list = list(volume_state.timeline_data)
        
        timestamps = []
        spike_ratios = []
        colors = []
        labels = []
        hover_texts = []
        
        for spike in timeline_list:
            timestamps.append(spike.timestamp)
            spike_ratios.append(spike.spike_ratio)
            
            # Color based on spike ratio
            _, _, color = get_alert_level(spike.spike_ratio)
            colors.append(color)
            
            # Label
            strike_label = get_strike_label(spike.strike, volume_state.last_atm_strike)
            label = f"{spike.strike}{spike.option_type}"
            if spike.distance_from_atm >= 150 or spike.distance_from_atm <= -150:
                label += "⚡"  # Mark far OTM/ITM
            labels.append(label)
            
            # Hover text
            hover_text = (
                f"<b>{spike.strike} {spike.option_type}</b><br>"
                f"{strike_label}<br>"
                f"Volume: {format_number(spike.volume)}<br>"
                f"Spike: {spike.spike_ratio:.1f}x<br>"
                f"Time: {spike.timestamp.strftime('%H:%M:%S')}"
            )
            hover_texts.append(hover_text)
        
        # Create figure
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=timestamps,
            y=spike_ratios,
            mode='markers+text',
            marker=dict(
                size=12,
                color=colors,
                line=dict(width=1, color='white')
            ),
            text=labels,
            textposition='top center',
            textfont=dict(size=8),
            hovertemplate='%{hovertext}<extra></extra>',
            hovertext=hover_texts,
            name='Spikes'
        ))
        
        fig.update_layout(
            title=f"⚡ NIFTY SMART VOLUME SPIKE TIMELINE (ATM: {volume_state.last_atm_strike})",
            xaxis_title="Time",
            yaxis_title="Spike Ratio (x)",
            height=400,
            hovermode='closest',
            showlegend=False,
            yaxis=dict(range=[0, max(spike_ratios) * 1.1 if spike_ratios else 6])
        )
        
        return fig, timeline_list[-3:] if len(timeline_list) >= 3 else timeline_list  # Last 3 for summary
    
    except Exception as e:
        print(f"Error creating timeline: {e}")
        return None, []

# =========================
# CHART 4: VOLUME INTENSITY WAVE
# =========================

def create_volume_intensity_wave():
    """Create volume intensity wave area chart"""
    try:
        if len(volume_state.intensity_history) < 2:
            return None
        
        # Prepare data
        intensity_list = list(volume_state.intensity_history)
        
        timestamps = []
        intensities = []
        
        for point in intensity_list:
            timestamps.append(point['timestamp'])
            intensities.append(point['intensity'])
        
        # Smooth the curve (moving average)
        if len(intensities) >= 5:
            smoothed = []
            for i in range(len(intensities)):
                start = max(0, i - 2)
                end = min(len(intensities), i + 3)
                smoothed.append(np.mean(intensities[start:end]))
            intensities = smoothed
        
        # Current intensity
        current_intensity = intensities[-1] if intensities else 1.0
        
        # Determine phase
        if current_intensity >= 4.0:
            phase = "EXTREME"
            phase_color = "#ff0000"
            phase_emoji = "🔴"
        elif current_intensity >= 3.0:
            phase = "HIGH"
            phase_color = "#ff8800"
            phase_emoji = "🟠"
        elif current_intensity >= 2.0:
            phase = "MEDIUM"
            phase_color = "#ffaa00"
            phase_emoji = "🟡"
        else:
            phase = "LOW"
            phase_color = "#0088ff"
            phase_emoji = "🔵"
        
        # Trend
        if len(intensities) >= 6:
            recent_trend = intensities[-1] - intensities[-6]
            if recent_trend > 0.3:
                trend = "ACCELERATING"
                trend_emoji = "↗️"
            elif recent_trend < -0.3:
                trend = "DECELERATING"
                trend_emoji = "↘️"
            else:
                trend = "STEADY"
                trend_emoji = "→"
        else:
            trend = "BUILDING"
            trend_emoji = "⏳"
        
        # Create figure
        fig = go.Figure()
        
        # Add area trace
        fig.add_trace(go.Scatter(
            x=timestamps,
            y=intensities,
            mode='lines',
            fill='tozeroy',
            line=dict(color=phase_color, width=2),
            fillcolor=f'rgba{tuple(list(int(phase_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)) + [0.3])}',
            name='Intensity',
            hovertemplate='<b>Time:</b> %{x|%H:%M:%S}<br><b>Intensity:</b> %{y:.1f}x<extra></extra>'
        ))
        
        # Add horizontal lines for phases
        fig.add_hline(y=4.0, line_dash="dash", line_color="red", opacity=0.3)
        fig.add_hline(y=3.0, line_dash="dash", line_color="orange", opacity=0.3)
        fig.add_hline(y=2.0, line_dash="dash", line_color="yellow", opacity=0.3)
        fig.add_hline(y=1.0, line_dash="dash", line_color="blue", opacity=0.3)
        
        fig.update_layout(
            title="🌊 NIFTY VOLUME INTENSITY WAVE (10-Min Rolling Average)",
            xaxis_title="Time",
            yaxis_title="Intensity (x Baseline)",
            height=350,
            hovermode='x unified',
            showlegend=False,
            yaxis=dict(range=[0, max(6, max(intensities) * 1.1) if intensities else 6])
        )
        
        return fig, {
            'current_intensity': current_intensity,
            'phase': phase,
            'phase_emoji': phase_emoji,
            'phase_color': phase_color,
            'trend': trend,
            'trend_emoji': trend_emoji
        }
    
    except Exception as e:
        print(f"Error creating wave chart: {e}")
        return None, {}

# =========================
# TELEGRAM ALERTS
# =========================

def check_volume_alerts(send_alert_func):
    """
    Check for volume spike alerts and send to Telegram
    
    Args:
        send_alert_func: Function to call for sending alerts
    """
    try:
        if not volume_state.spike_queue:
            return
        
        # Get latest spike
        latest_spike = list(volume_state.spike_queue)[-1]
        
        # Only alert if spike >= 5.0x
        if latest_spike.spike_ratio >= 5.0:
            strike_label = get_strike_label(latest_spike.strike, volume_state.last_atm_strike)
            
            alert_msg = (
                f"<b>⚡ VOLUME SPIKE ALERT - NIFTY</b>\n\n"
                f"<b>Strike:</b> {latest_spike.strike} {latest_spike.option_type} ({strike_label})\n"
                f"<b>Volume:</b> {format_number(latest_spike.volume)} (+{latest_spike.spike_ratio:.1f}x)\n"
                f"<b>Time:</b> {latest_spike.timestamp.strftime('%I:%M:%S %p')}\n\n"
                f"<b>Signal:</b> 🔥 STRONG {'BUY' if latest_spike.option_type == 'CE' else 'SELL'}\n"
                f"<b>Avg Volume:</b> {format_number(latest_spike.avg_volume)}\n\n"
                f"<b>Context:</b> {latest_spike.option_type} buying {'accelerating' if latest_spike.spike_ratio > 6 else 'strong'}\n"
                f"<b>Bias:</b> {'Bullish' if latest_spike.option_type == 'CE' else 'Bearish'} momentum building\n\n"
                f"⏰ {datetime.now().strftime('%I:%M:%S %p')}"
            )
            
            send_alert_func(alert_msg, "warning")
    
    except Exception as e:
        print(f"Error checking volume alerts: {e}")

# =========================
# RESET FUNCTION
# =========================

def reset_volume_data():
    """Reset volume data for new trading day"""
    volume_state.spike_queue.clear()
    volume_state.ce_pe_history.clear()
    volume_state.timeline_data.clear()
    volume_state.intensity_history.clear()
    volume_state.volume_baseline = 0.0
    volume_state.last_atm_strike = 0
    print("✓ Volume analysis data reset for new trading day")


# =========================
# SESSION STATE INIT
# =========================
if "auto_refresh_toggle" not in st.session_state:
    st.session_state.auto_refresh_toggle = True
if "polling_running" not in st.session_state:
    st.session_state.polling_running = False
if "refresh_count" not in st.session_state:
    st.session_state.refresh_count = 0

# =========================
# GLOBAL STATE (Thread-Safe via session_state)
# =========================
# ✅ FIX: Use session_state for shared data between polling thread and dashboard
if 'flow_history' not in st.session_state:
    st.session_state.flow_history = deque(maxlen=30)
if 'alerts' not in st.session_state:
    st.session_state.alerts = deque(maxlen=10)
if 'nifty_chart_data' not in st.session_state:
    # Try to load from cache file first
    chart_cache_file = Path('.cache/nifty_chart_data.pkl')
    if chart_cache_file.exists():
        try:
            with open(chart_cache_file, 'rb') as f:
                cached_data = pickle.load(f)
            # Verify it's from today
            if cached_data and isinstance(cached_data, deque):
                latest_time = list(cached_data)[-1]['timestamp'] if cached_data else None
                if latest_time and latest_time.date() == datetime.now().date():
                    st.session_state.nifty_chart_data = cached_data
                    print(f"✅ Loaded {len(cached_data)} chart points from cache")
                else:
                    st.session_state.nifty_chart_data = deque(maxlen=30)
                    print("🔄 Cache from different day, starting fresh")
            else:
                st.session_state.nifty_chart_data = deque(maxlen=30)
        except Exception as e:
            print(f"⚠️ Error loading chart cache: {e}")
            st.session_state.nifty_chart_data = deque(maxlen=30)
    else:
        st.session_state.nifty_chart_data = deque(maxlen=30)

flow_history = st.session_state.flow_history
alerts = st.session_state.alerts
nifty_chart_data = st.session_state.nifty_chart_data  # PHASE 1: Stores (timestamp, spot_price, ce_flow, pe_flow) for charts


# Pattern matching imports
try:
    import sys
    sys.path.insert(0, '/mnt/user-data/outputs')
    from patterns import analyze_pattern, get_market_state, get_available_data_days
    from pattern_alerts import format_pattern_alert, should_generate_alert
    PATTERNS_AVAILABLE = True
    print("✓ Pattern matching modules loaded")
except Exception as e:
    PATTERNS_AVAILABLE = False
    print(f"⚠️ Pattern matching not available: {e}")

# =========================
# CONSTANTS
# =========================
TZ = "Asia/Kolkata"
DATA_ROOT = Path("data")
HISTORICAL_DIR = DATA_ROOT / "historical" / "indices"  # PHASE 1: Historical data storage
CACHE_DIR = Path(".cache")
TOKENS_FILE = CACHE_DIR / "tokens.json"
DASHBOARD_CACHE_FILE = CACHE_DIR / "dashboard_cache.pkl"
INSTRUMENTS_FILE = CACHE_DIR / "instruments.parquet"
FLOW_HISTORY_FILE = CACHE_DIR / "flow_history.pkl"

DATA_ROOT.mkdir(parents=True, exist_ok=True)
HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)  # PHASE 1
CACHE_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv()
API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

DERIV_FUT_SEGMENTS = {"NFO-FUT", "BFO-FUT"}
DERIV_OPT_SEGMENTS = {"NFO-OPT", "BFO-OPT"}
INDEX_NAME_WHITELIST = {
    # Original 5 indices
    "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX",
    # New 10 sectoral indices
    "NIFTY MIDCAP 50", "NIFTY AUTO", "NIFTY PHARMA", "NIFTY METAL", "NIFTY ENERGY",
    "NIFTY FMCG", "NIFTY REALTY", "NIFTY PSU BANK", "NIFTY INFRA", "NIFTY OIL & GAS"
}

@dataclass
class EngineState:
    kite: KiteConnect = None
    polling_thread: threading.Thread = None
    ins_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    token_meta: pd.DataFrame = field(default_factory=pd.DataFrame)
    subscribe_tokens: list = field(default_factory=list)
    stop_flag: bool = False
    indices_with_fo: list = field(default_factory=list)
    stocks_with_fo: list = field(default_factory=list)
    last_poll_time: datetime = None
    polling_active: bool = False
    cached_prev_close: dict = field(default_factory=dict)
    first_15min_range: dict = field(default_factory=dict)
    range_status: dict = field(default_factory=dict)
    futures_volume_history: dict = field(default_factory=dict)
    pattern_enabled: bool = True  # Enable hybrid pattern matching
    last_pattern_alert: dict = field(default_factory=dict)  # Track pattern alerts
    chart_update_counter: int = 0  # PHASE 1: Track when to update charts (every 30 polls = 5 minutes)
    nifty_fut_token: int = None
    nifty_fut_symbol: str = ""
    nifty_fut_expiry: str = ""
    last_stock_alert: dict = field(default_factory=dict)  # Track stock alerts with cooldowns
    top_10_stocks: set = field(default_factory=set)  # Track current Top 10 stocks

engine = EngineState()

# =========================
# NIFTY FUTURES HELPER
# =========================
def get_current_month_nifty_future(ins_df):
    """Get current month NIFTY futures contract"""
    today = datetime.now()
    
    nifty_fut = ins_df[
        (ins_df['name'] == 'NIFTY') & 
        (ins_df['instrument_type'] == 'FUT')
    ].copy()
    
    if nifty_fut.empty:
        return None
    
    nifty_fut['expiry_date'] = pd.to_datetime(nifty_fut['expiry'])
    valid_contracts = nifty_fut[nifty_fut['expiry_date'] >= today]
    
    if valid_contracts.empty:
        return None
    
    current_month_fut = valid_contracts.loc[valid_contracts['expiry_date'].idxmin()]
    
    return {
        'token': int(current_month_fut['instrument_token']),
        'symbol': current_month_fut['tradingsymbol'],
        'expiry': current_month_fut['expiry'].strftime('%d %b')
    }


# =========================
# HELPER FUNCTIONS
# =========================
def save_flow_history(data):
    """Save flow history to disk"""
    try:
        with open(FLOW_HISTORY_FILE, "wb") as f:
            pickle.dump(list(flow_history), f)
    except Exception as e:
        print(f"Error saving flow history: {e}")

def load_flow_history():
    """Load flow history from disk"""
    global flow_history
    if FLOW_HISTORY_FILE.exists():
        try:
            with open(FLOW_HISTORY_FILE, "rb") as f:
                history = pickle.load(f)
                flow_history = deque(history, maxlen=30)
        except Exception as e:
            print(f"Error loading flow history: {e}")

def format_number(num):
    """
    PHASE 1: Format number in K/M notation for better readability
    Examples:
        850 → "850"
        5000 → "5.0K"
        1500000 → "1.50M"
        -25000 → "-25.0K"
    """
    if num is None:
        return "—"
    
    abs_num = abs(num)
    
    if abs_num >= 1_000_000:
        # Millions
        formatted = f"{num/1_000_000:.2f}M"
    elif abs_num >= 1_000:
        # Thousands
        formatted = f"{num/1_000:.1f}K"
    else:
        # Less than 1000
        formatted = f"{num:.0f}"
    
    return formatted

def save_historical_data(index_name, data_row):
    """
    PHASE 1: Save historical data to daily CSV file
    Creates folder structure: data/historical/indices/YYYY-MM-DD/INDEX_NAME.csv
    """
    try:
        # Create date-specific folder
        today = datetime.now().date()
        date_folder = HISTORICAL_DIR / str(today)
        date_folder.mkdir(parents=True, exist_ok=True)
        
        # CSV file path
        csv_file = date_folder / f"{index_name}.csv"
        
        # Check if file exists to determine if we need headers
        file_exists = csv_file.exists()
        
        # Write data
        with open(csv_file, 'a', newline='') as f:
            fieldnames = [
                'timestamp', 'index_name', 'spot_price', 'price_change_pct',
                'ce_flow', 'pe_flow', 'net_flow',
                'delta_1min_ce', 'delta_1min_pe', 'delta_5min_ce', 'delta_5min_pe',
                'sentiment', 'range_status', 'futures_volume', 'avg_volume', 'volume_ratio'
            ]
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
            
            writer.writerow(data_row)
            print(f"✅ [HIST] Wrote row to {csv_file}")
            
    except Exception as e:
        print(f"❌ [HIST] Error saving {index_name}: {e}")
        import traceback
        traceback.print_exc()

def save_volume_spike_data(spike: 'VolumeSpike'):
    """
    Save volume spike data to daily CSV file for AI analysis
    Creates folder structure: data/historical/volume_spikes/YYYY-MM-DD/NIFTY_volume_spikes.csv
    """
    try:
        # Create date-specific folder
        today = datetime.now().date()
        volume_spike_dir = DATA_ROOT / "historical" / "volume_spikes" / str(today)
        volume_spike_dir.mkdir(parents=True, exist_ok=True)
        
        # CSV file path
        csv_file = volume_spike_dir / "NIFTY_volume_spikes.csv"
        
        # Check if file exists
        file_exists = csv_file.exists()
        
        # Write data
        with open(csv_file, 'a', newline='') as f:
            fieldnames = [
                'timestamp', 'strike', 'option_type', 'volume', 'avg_volume',
                'spike_ratio', 'is_atm', 'distance_from_atm', 'alert_level',
                'atm_strike_at_time'
            ]
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
            
            # Write spike data
            writer.writerow({
                'timestamp': spike.timestamp.isoformat(),
                'strike': spike.strike,
                'option_type': spike.option_type,
                'volume': spike.volume,
                'avg_volume': spike.avg_volume,
                'spike_ratio': spike.spike_ratio,
                'is_atm': spike.is_atm,
                'distance_from_atm': spike.distance_from_atm,
                'alert_level': spike.alert_level,
                'atm_strike_at_time': volume_state.last_atm_strike
            })
            
    except Exception as e:
        print(f"Error saving volume spike data: {e}")

def save_volume_intensity_data(intensity_ratio: float, ce_volume: int, pe_volume: int):
    """
    Save volume intensity data to daily CSV file for AI analysis
    Creates folder structure: data/historical/volume_intensity/YYYY-MM-DD/NIFTY_volume_intensity.csv
    """
    try:
        # Create date-specific folder
        today = datetime.now().date()
        intensity_dir = DATA_ROOT / "historical" / "volume_intensity" / str(today)
        intensity_dir.mkdir(parents=True, exist_ok=True)
        
        # CSV file path
        csv_file = intensity_dir / "NIFTY_volume_intensity.csv"
        
        # Check if file exists
        file_exists = csv_file.exists()
        
        # Write data
        with open(csv_file, 'a', newline='') as f:
            fieldnames = [
                'timestamp', 'intensity_ratio', 'ce_volume', 'pe_volume',
                'total_volume', 'baseline_volume', 'atm_strike'
            ]
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
            
            # Write intensity data
            writer.writerow({
                'timestamp': datetime.now().isoformat(),
                'intensity_ratio': intensity_ratio,
                'ce_volume': ce_volume,
                'pe_volume': pe_volume,
                'total_volume': ce_volume + pe_volume,
                'baseline_volume': volume_state.volume_baseline,
                'atm_strike': volume_state.last_atm_strike
            })
            
    except Exception as e:
        print(f"Error saving volume intensity data: {e}")

def calculate_deltas(current_data):
    """Calculate 1min and 5min deltas"""
    print(f"\n{'='*50}")
    print(f"DEBUG DELTA CALCULATION")
    print(f"{'='*50}")
    print(f"Flow history length: {len(flow_history)}")
    print(f"Current data: indices_ce={current_data.get('indices_ce', 0):,.0f}, indices_pe={current_data.get('indices_pe', 0):,.0f}")
    
    if len(flow_history) < 1:
        print("❌ Not enough data for deltas (need at least 1 previous point)")
        print("⏳ This is normal - wait for 2nd poll cycle (20 seconds)")
        return None
    
    data_1min_ago = flow_history[-1] if len(flow_history) >= 1 else None
    data_5min_ago = flow_history[0] if len(flow_history) >= 5 else None
    
    print(f"\n📊 Previous data (1 poll ago):")
    if data_1min_ago:
        print(f"  indices_ce={data_1min_ago.get('indices_ce', 0):,.0f}")
        print(f"  indices_pe={data_1min_ago.get('indices_pe', 0):,.0f}")
    
    deltas = {}
    
    if data_1min_ago:
        for key in ["indices_ce", "indices_pe", "stocks_ce", "stocks_pe"]:
            current_val = current_data.get(key, 0)
            prev_val = data_1min_ago.get(key, 0)
            delta = current_val - prev_val
            deltas[f"{key}_1min"] = delta
            
            if abs(delta) > 0:
                print(f"✅ {key}_1min: Δ{delta:+,.0f} (curr: {current_val:,.0f}, prev: {prev_val:,.0f})")
            else:
                print(f"⚠️ {key}_1min: Δ0 (curr: {current_val:,.0f}, prev: {prev_val:,.0f})")
    
    # PHASE 1: Calculate individual index deltas (1min)
    if data_1min_ago and 'indices_data' in current_data and 'indices_data' in data_1min_ago:
        for idx_name in current_data['indices_data'].keys():
            if idx_name in data_1min_ago['indices_data']:
                curr_idx = current_data['indices_data'][idx_name]
                prev_idx = data_1min_ago['indices_data'][idx_name]
                
                deltas[f"{idx_name}_ce_1min"] = curr_idx.get('ce_flow', 0) - prev_idx.get('ce_flow', 0)
                deltas[f"{idx_name}_pe_1min"] = curr_idx.get('pe_flow', 0) - prev_idx.get('pe_flow', 0)
    
    if data_5min_ago:
        print(f"\n📊 Previous data (5 polls ago):")
        print(f"  indices_ce={data_5min_ago.get('indices_ce', 0):,.0f}")
        
        for key in ["indices_ce", "indices_pe", "stocks_ce", "stocks_pe"]:
            current_val = current_data.get(key, 0)
            prev_val = data_5min_ago.get(key, 0)
            delta = current_val - prev_val
            deltas[f"{key}_5min"] = delta
            
            if abs(delta) > 0:
                print(f"✅ {key}_5min: Δ{delta:+,.0f}")
        
        # PHASE 1: Calculate individual index deltas (5min)
        if 'indices_data' in current_data and 'indices_data' in data_5min_ago:
            for idx_name in current_data['indices_data'].keys():
                if idx_name in data_5min_ago['indices_data']:
                    curr_idx = current_data['indices_data'][idx_name]
                    prev_idx = data_5min_ago['indices_data'][idx_name]
                    
                    deltas[f"{idx_name}_ce_5min"] = curr_idx.get('ce_flow', 0) - prev_idx.get('ce_flow', 0)
                    deltas[f"{idx_name}_pe_5min"] = curr_idx.get('pe_flow', 0) - prev_idx.get('pe_flow', 0)
    else:
        print(f"⏳ 5-min deltas: Waiting for 5th poll cycle (50 seconds)")
    
    print(f"\n🎯 Final deltas: {deltas}")
    print(f"{'='*50}\n")
    return deltas

def get_smart_sentiment(price_change_pct, net_flow):
    """Calculate smart sentiment combining price action and options flow"""
    if price_change_pct is None:
        price_signal = "UNKNOWN"
        price_emoji = "⚪"
    elif price_change_pct > 0.5:
        price_signal = "BULLISH"
        price_emoji = "🟢"
    elif price_change_pct < -0.5:
        price_signal = "BEARISH"
        price_emoji = "🔴"
    else:
        price_signal = "NEUTRAL"
        price_emoji = "🟡"
    
    if abs(net_flow) < 1000:
        flow_signal = "NEUTRAL"
        flow_emoji = "🟡"
    elif net_flow > 1000:
        flow_signal = "BULLISH"
        flow_emoji = "🟢"
    else:
        flow_signal = "BEARISH"
        flow_emoji = "🔴"
    
    if price_signal == flow_signal and price_signal == "BULLISH":
        sentiment = "🟢 STRONG BULLISH"
        color = "#28a745"
        interpretation = "Price rising + Traders buying calls = Strong uptrend momentum"
    elif price_signal == flow_signal and price_signal == "BEARISH":
        sentiment = "🔴 STRONG BEARISH"
        color = "#dc3545"
        interpretation = "Price falling + Traders buying puts = Strong downtrend momentum"
    elif price_signal == "BULLISH" and flow_signal == "BEARISH":
        sentiment = "⚠️ BEARISH DIVERGENCE"
        color = "#ff8800"
        interpretation = "Price rising but traders positioning bearish - Possible reversal down or profit booking expected"
    elif price_signal == "BEARISH" and flow_signal == "BULLISH":
        sentiment = "⚠️ BULLISH DIVERGENCE"
        color = "#ff8800"
        interpretation = "Price falling but traders positioning bullish - Possible reversal up or dip buying opportunity"
    elif price_signal == "NEUTRAL" and flow_signal == "BULLISH":
        sentiment = "🟢 BULLISH POSITIONING"
        color = "#28a745"
        interpretation = "Price stable but traders accumulating calls - Expecting upside move"
    elif price_signal == "NEUTRAL" and flow_signal == "BEARISH":
        sentiment = "🔴 BEARISH POSITIONING"
        color = "#dc3545"
        interpretation = "Price stable but traders accumulating puts - Expecting downside move"
    elif price_signal == "BULLISH" and flow_signal == "NEUTRAL":
        sentiment = "🟢 PRICE MOMENTUM"
        color = "#28a745"
        interpretation = "Price rising but options flow neutral - Follow price action"
    elif price_signal == "BEARISH" and flow_signal == "NEUTRAL":
        sentiment = "🔴 PRICE WEAKNESS"
        color = "#dc3545"
        interpretation = "Price falling but options flow neutral - Follow price action"
    else:
        sentiment = "⚪ MIXED SIGNALS"
        color = "#808080"
        interpretation = "No clear directional bias - Wait for confirmation"
    
    return sentiment, color, price_signal, price_emoji, flow_signal, flow_emoji, interpretation

def detect_spike(deltas, avg_delta, threshold=3.0):
    """Detect if current delta is a spike"""
    if not deltas or not avg_delta or avg_delta == 0:
        return False
    return abs(deltas) > (threshold * abs(avg_delta))

def send_telegram_alert(message):
    """Send alert to Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            return True
        else:
            print(f"Telegram API error: {response.text}")
            return False
            
    except Exception as e:
        print(f"Telegram exception: {str(e)}")
        return False

def add_alert(message, alert_type="info", cooldown_minutes=10):
    """Add alert to alert queue and send to Telegram with cooldown"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    alerts.appendleft({
        "time": timestamp,
        "message": message,
        "type": alert_type
    })

    # Add cooldown for alerts to prevent spam
    # Use message hash as key to track unique alerts
    import hashlib
    message_hash = hashlib.md5(message.encode()).hexdigest()[:8]

    now = datetime.now()
    if message_hash in engine.last_stock_alert:
        last_time = engine.last_stock_alert[message_hash]
        minutes_passed = (now - last_time).total_seconds() / 60
        if minutes_passed < cooldown_minutes:
            # Skip telegram alert if within cooldown
            return

    telegram_message = f"<b>🚨 ALERT - {timestamp}</b>\n\n{message}"
    send_telegram_alert(telegram_message)
    engine.last_stock_alert[message_hash] = now


def send_stock_alert(stock_name, alert_type, price, change_pct, net_flow, volume_ratio=None):
    """
    Send stock alerts via Telegram with cooldown logic

    Alert Types & Cooldowns:
    - BULLISH: 60-min cooldown per stock
    - BEARISH: 60-min cooldown per stock
    """
    now = datetime.now()

    # Check cooldown based on alert type
    cooldown_key = f"{stock_name}_{alert_type}"

    if cooldown_key in engine.last_stock_alert:
        last_alert_time = engine.last_stock_alert[cooldown_key]
        time_diff = (now - last_alert_time).total_seconds() / 60  # minutes

        # Apply 60-minute cooldown
        if time_diff < 60:
            return False

    # Format alert message (Hybrid format - 2-3 lines)
    if alert_type == "BULLISH":
        emoji = "🟢"
        signal = "STRONG BULLISH"
        interpretation = "Price rising + Strong call buying"
    elif alert_type == "BEARISH":
        emoji = "🔴"
        signal = "STRONG BEARISH"
        interpretation = "Price falling + Strong put buying"
    else:
        return False  # Only BULLISH/BEARISH alerts allowed

    # Format price and flow
    price_str = f"₹{price:,.2f}"
    change_emoji = "🟢" if change_pct > 0 else "🔴"
    change_str = f"{change_emoji}{change_pct:+.2f}%"
    flow_emoji = "🟢" if net_flow > 0 else "🔴"
    flow_str = f"{flow_emoji}{format_number(net_flow)}"

    # Hybrid format (2-3 lines)
    telegram_message = f"{emoji} {signal} - {stock_name}\n"
    telegram_message += f"{price_str} {change_str} | Flow {flow_str}\n"
    telegram_message += f"{interpretation}"

    # Send to Telegram
    try:
        send_telegram_alert(telegram_message)
        print(f"📱 Stock Alert: {stock_name} - {signal}")
        engine.last_stock_alert[cooldown_key] = now
        return True
    except Exception as e:
        print(f"Error sending stock alert: {e}")
        return False

def get_momentum_signal(delta_1min, delta_5min):
    """Determine momentum signal"""
    if delta_1min is None:
        return "⏸️ WAITING", "gray"
    
    if delta_5min and delta_5min != 0:
        acceleration = (delta_1min * 5) / delta_5min
    else:
        acceleration = 1.0
    
    if abs(delta_1min) < 1000:
        return "📊 QUIET", "#808080"
    elif acceleration > 2.0:
        return "🔥 ACCELERATING", "#ff4444"
    elif acceleration > 1.3:
        return "⚡ SURGING", "#ff8800"
    elif acceleration > 0.7:
        return "📈 STEADY", "#00aa00"
    else:
        return "⚠️ SLOWING", "#ffaa00"

def get_first_15min_range(index_name, current_time):
    """Get high and low of first 15 minutes (9:15 to 9:30)"""
    try:
        if index_name in engine.first_15min_range:
            return engine.first_15min_range[index_name]
        
        market_open = dt_time(9, 15)
        range_end = dt_time(9, 30)
        
        current_time_only = current_time.time()
        
        if current_time_only >= range_end:
            try:
                spot_token = get_spot_index_token(engine.ins_df, index_name)
                if not spot_token:
                    return None
                
                from_date = current_time.replace(hour=9, minute=15, second=0, microsecond=0)
                to_date = current_time.replace(hour=9, minute=30, second=0, microsecond=0)
                
                historical_data = engine.kite.historical_data(
                    instrument_token=spot_token,
                    from_date=from_date,
                    to_date=to_date,
                    interval="15minute"
                )
                
                if historical_data and len(historical_data) > 0:
                    candle = historical_data[0]
                    range_data = {
                        "high": candle["high"],
                        "low": candle["low"],
                        "open": candle["open"],
                        "close": candle["close"]
                    }
                    engine.first_15min_range[index_name] = range_data
                    print(f"✓ {index_name} First 15min Range: High={range_data['high']:.2f}, Low={range_data['low']:.2f}")
                    return range_data
            except Exception as e:
                print(f"Error fetching historical data for {index_name}: {e}")
                return None
        
        return None
    except Exception as e:
        print(f"Error in get_first_15min_range: {e}")
        return None

def check_range_breakout(index_name, current_price, sentiment_status, futures_volume=None, avg_volume=None):
    """
    Check if price has broken out of first 15min range WITH volume confirmation
    Returns: (status, alert_message)
    """
    try:
        range_data = engine.first_15min_range.get(index_name)
        if not range_data:
            return "CALCULATING", None
        
        high_15min = range_data["high"]
        low_15min = range_data["low"]
        
        volume_ratio = None
        volume_status = ""
        volume_strength = ""
        
        if futures_volume and avg_volume and avg_volume > 0:
            volume_ratio = futures_volume / avg_volume
            
            if volume_ratio >= 1.5:
                volume_status = "STRONG VOLUME ✅"
                volume_strength = "STRONG"
            elif volume_ratio >= 1.2:
                volume_status = "MODERATE VOLUME 📊"
                volume_strength = "MODERATE"
            else:
                volume_status = "LOW VOLUME ⚠️"
                volume_strength = "WEAK"
        
        current_status = engine.range_status.get(index_name, {})
        previous_breakout = current_status.get("breakout_type", None)
        alert_sent = current_status.get("alert_sent", False)
        reverse_alert_sent = current_status.get("reverse_alert_sent", False)
        
        if current_price > high_15min:
            new_status = "RANGEBOUND_BREAKER_HIGH"
            
            if previous_breakout != "HIGH" and not alert_sent:
                engine.range_status[index_name] = {
                    "breakout_type": "HIGH",
                    "alert_sent": True,
                    "reverse_alert_sent": False
                }
                
                if "BULLISH" in sentiment_status.upper():
                    volume_info = ""
                    if volume_ratio:
                        volume_info = f"\n<b>Volume:</b> {format_number(futures_volume)} (Avg: {format_number(avg_volume)}) - {volume_ratio:.1f}x\n<b>{volume_status}</b>\n"
                    
                    alert_msg = (
                        f"<b>🚀 {volume_strength if volume_ratio else ''} BULLISH RANGEBOUND BREAKER</b>\n"
                        f"<b>{index_name}</b>\n\n"
                        f"<b>Price:</b> {current_price:.2f}\n"
                        f"<b>15min High:</b> {high_15min:.2f}\n"
                        f"<b>15min Low:</b> {low_15min:.2f}\n"
                        f"<b>Sentiment:</b> {sentiment_status}\n"
                        f"{volume_info}\n"
                        f"✅ <b>BULLISH BREAKOUT</b> - Price broke above 15min high!\n"
                        f"💡 {'High probability setup' if volume_ratio and volume_ratio >= 1.5 else 'Wait for volume confirmation'} - Consider: Buy {index_name} CE\n\n"
                        f"⏰ {datetime.now().strftime('%I:%M:%S %p')}"
                    )
                    return new_status, alert_msg
            
            elif previous_breakout == "LOW" and not reverse_alert_sent:
                engine.range_status[index_name] = {
                    "breakout_type": "HIGH",
                    "alert_sent": True,
                    "reverse_alert_sent": True
                }
                
                if "BULLISH" in sentiment_status.upper():
                    alert_msg = (
                        f"<b>🔄 BULLISH REVERSE RANGEBOUND BREAKER</b>\n"
                        f"<b>{index_name}</b>\n\n"
                        f"<b>Price:</b> {current_price:.2f}\n"
                        f"<b>15min High:</b> {high_15min:.2f}\n"
                        f"<b>15min Low:</b> {low_15min:.2f}\n"
                        f"<b>Previous:</b> Was below low, now above high\n"
                        f"<b>Sentiment:</b> {sentiment_status}\n\n"
                        f"⚠️ <b>REVERSAL DETECTED</b> - Market reversed from bearish to bullish!\n\n"
                        f"⏰ {datetime.now().strftime('%I:%M:%S %p')}"
                    )
                    return "REVERSE_RANGEBOUND_BREAKER", alert_msg
            
            return new_status, None
        
        elif current_price < low_15min:
            new_status = "RANGEBOUND_BREAKER_LOW"
            
            if previous_breakout != "LOW" and not alert_sent:
                engine.range_status[index_name] = {
                    "breakout_type": "LOW",
                    "alert_sent": True,
                    "reverse_alert_sent": False
                }
                
                if "BEARISH" in sentiment_status.upper():
                    volume_info = ""
                    if volume_ratio:
                        volume_info = f"\n<b>Volume:</b> {format_number(futures_volume)} (Avg: {format_number(avg_volume)}) - {volume_ratio:.1f}x\n<b>{volume_status}</b>\n"
                    
                    alert_msg = (
                        f"<b>📉 {volume_strength if volume_ratio else ''} BEARISH RANGEBOUND BREAKER</b>\n"
                        f"<b>{index_name}</b>\n\n"
                        f"<b>Price:</b> {current_price:.2f}\n"
                        f"<b>15min High:</b> {high_15min:.2f}\n"
                        f"<b>15min Low:</b> {low_15min:.2f}\n"
                        f"<b>Sentiment:</b> {sentiment_status}\n"
                        f"{volume_info}\n"
                        f"✅ <b>BEARISH BREAKOUT</b> - Price broke below 15min low!\n"
                        f"💡 {'High probability setup' if volume_ratio and volume_ratio >= 1.5 else 'Wait for volume confirmation'} - Consider: Buy {index_name} PE\n\n"
                        f"⏰ {datetime.now().strftime('%I:%M:%S %p')}"
                    )
                    return new_status, alert_msg
            
            elif previous_breakout == "HIGH" and not reverse_alert_sent:
                engine.range_status[index_name] = {
                    "breakout_type": "LOW",
                    "alert_sent": True,
                    "reverse_alert_sent": True
                }
                
                if "BEARISH" in sentiment_status.upper():
                    alert_msg = (
                        f"<b>🔄 BEARISH REVERSE RANGEBOUND BREAKER</b>\n"
                        f"<b>{index_name}</b>\n\n"
                        f"<b>Price:</b> {current_price:.2f}\n"
                        f"<b>15min High:</b> {high_15min:.2f}\n"
                        f"<b>15min Low:</b> {low_15min:.2f}\n"
                        f"<b>Previous:</b> Was above high, now below low\n"
                        f"<b>Sentiment:</b> {sentiment_status}\n\n"
                        f"⚠️ <b>REVERSAL DETECTED</b> - Market reversed from bullish to bearish!\n\n"
                        f"⏰ {datetime.now().strftime('%I:%M:%S %p')}"
                    )
                    return "REVERSE_RANGEBOUND_BREAKER", alert_msg
            
            return new_status, None
        
        else:
            if previous_breakout is None:
                engine.range_status[index_name] = {
                    "breakout_type": None,
                    "alert_sent": False,
                    "reverse_alert_sent": False
                }
            return "RANGEBOUND", None
    
    except Exception as e:
        print(f"Error in check_range_breakout for {index_name}: {e}")
        return "ERROR", None

def calculate_atm_strike(current_price, index_name):
    """Calculate ATM strike price based on current price"""
    step_map = {
        "BANKNIFTY": 100, "NIFTY": 50, "FINNIFTY": 50, "MIDCPNIFTY": 25, "SENSEX": 100,
        # New indices (using reasonable defaults, adjust if needed)
        "NIFTY MIDCAP 50": 50, "NIFTY AUTO": 50, "NIFTY PHARMA": 50, 
        "NIFTY METAL": 50, "NIFTY ENERGY": 50, "NIFTY FMCG": 50,
        "NIFTY REALTY": 25, "NIFTY PSU BANK": 25, "NIFTY INFRA": 50, "NIFTY OIL & GAS": 50
    }
    step = step_map.get(index_name, 50)
    atm_strike = round(current_price / step) * step
    return atm_strike, step

def get_option_ltp(ins_df, instrument_name, strike, option_type):
    """Get LTP for a specific option strike"""
    try:
        option_data = ins_df[
            (ins_df["name"] == instrument_name) &
            (ins_df["strike"] == strike) &
            (ins_df["instrument_type"] == option_type) &
            (ins_df["segment"].isin(DERIV_OPT_SEGMENTS))
        ]
        
        if option_data.empty:
            return None, None
        
        option_token = int(option_data.iloc[0]["instrument_token"])
        
        try:
            quote = engine.kite.quote([option_token])
            ltp = list(quote.values())[0].get("last_price", None)
            return ltp, option_token
        except:
            return None, option_token
    except Exception as e:
        print(f"Error getting option LTP: {e}")
        return None, None

def create_actionable_alert_index(index_name, option_type, volume_spike, underlying_price, change_pct):
    """Create actionable alert for index with strike price and entry levels"""
    try:
        atm_strike, step = calculate_atm_strike(underlying_price, index_name)
        
        ltp, token = get_option_ltp(engine.ins_df, index_name, atm_strike, option_type)
        
        if ltp is None:
            print(f"Could not get LTP for {index_name} {atm_strike} {option_type}")
            return None
        
        entry_low = ltp * 0.98
        entry_high = ltp * 1.02
        target = ltp * 1.15
        stop_loss = ltp * 0.90
        
        spike_strength = "🔥 STRONG SPIKE" if volume_spike > 30000000 else ("⚡ MODERATE SPIKE" if volume_spike > 15000000 else "📊 BUILDING")
        
        alert_msg = (
            f"<b>🔥 {index_name} ENTRY SIGNAL 🔥</b>\n\n"
            f"<b>Strike:</b> {atm_strike} {option_type} (ATM)\n"
            f"<b>Current LTP:</b> ₹{ltp:.2f}\n"
            f"<b>Entry:</b> ₹{entry_low:.2f}-{entry_high:.2f}\n"
            f"<b>Target:</b> ₹{target:.2f} (+15.0%)\n"
            f"<b>Stop Loss:</b> ₹{stop_loss:.2f} (-10.0%)\n\n"
            f"<b>Volume Spike:</b> +{format_number(volume_spike)} contracts\n"
            f"<b>Underlying:</b> {underlying_price:.2f} ({change_pct:+.2f}%)\n\n"
            f"<b>Momentum:</b> {spike_strength}\n\n"
            f"<b>⏰</b> {datetime.now().strftime('%H:%M:%S')}"
        )
        
        return alert_msg
    except Exception as e:
        print(f"Error creating index alert: {e}")
        return None

def create_actionable_alert_stock(stock_name, option_type, volume_spike, sector):
    """Create actionable alert for stock with strike price and entry levels"""
    try:
        fut = nearest_fut(engine.ins_df, stock_name)
        if not fut:
            return None
        
        fut_token = int(fut["instrument_token"])
        try:
            quote = engine.kite.quote([fut_token])
            underlying_price = list(quote.values())[0]["last_price"]
        except:
            return None
        
        if underlying_price > 5000:
            step = 100
        elif underlying_price > 1000:
            step = 50
        elif underlying_price > 500:
            step = 25
        elif underlying_price > 100:
            step = 10
        else:
            step = 5
        
        atm_strike = round(underlying_price / step) * step
        
        ltp, token = get_option_ltp(engine.ins_df, stock_name, atm_strike, option_type)
        
        if ltp is None:
            return None
        
        entry_low = ltp * 0.98
        entry_high = ltp * 1.02
        target = ltp * 1.15
        stop_loss = ltp * 0.90
        
        spike_strength = "🔥 STRONG SPIKE" if volume_spike > 10000 else ("⚡ MODERATE SPIKE" if volume_spike > 5000 else "📊 BUILDING")
        
        sector_text = f" ({sector})" if sector and sector != "N/A" else ""
        
        alert_msg = (
            f"<b>⚡ {stock_name} ENTRY SIGNAL ⚡</b>\n\n"
            f"<b>Strike:</b> {atm_strike} {option_type} (ATM)\n"
            f"<b>Current LTP:</b> ₹{ltp:.2f}\n"
            f"<b>Entry:</b> ₹{entry_low:.2f}-{entry_high:.2f}\n"
            f"<b>Target:</b> ₹{target:.2f} (+15.0%)\n"
            f"<b>Stop Loss:</b> ₹{stop_loss:.2f} (-10.0%)\n\n"
            f"<b>Volume Spike:</b> +{format_number(volume_spike)} contracts\n"
            f"<b>Underlying:</b> {underlying_price:.2f}\n"
            f"<b>Sector:</b> {sector_text}\n\n"
            f"<b>Momentum:</b> {spike_strength}\n\n"
            f"<b>⏰</b> {datetime.now().strftime('%H:%M:%S')}"
        )
        
        return alert_msg
    except Exception as e:
        print(f"Error creating stock alert: {e}")
        return None

def get_kite_session():
    if "kite_session" in st.session_state:
        if (datetime.now() - st.session_state.kite_session_time).total_seconds() < 300:
            return st.session_state.kite_session, st.session_state.token_saved_at
    
    if TOKENS_FILE.exists():
        try:
            with open(TOKENS_FILE) as f:
                data = json.load(f)
            saved_at = datetime.fromisoformat(data.get("saved_at", "2000-01-01"))
            now = datetime.now()
            if saved_at.date() < now.date() and now.hour >= 6:
                TOKENS_FILE.unlink()
                return None, None
            kite = KiteConnect(api_key=API_KEY)
            kite.set_access_token(data["access_token"])
            try:
                kite.margins()
            except Exception as e:
                if "token" in str(e).lower() or "auth" in str(e).lower():
                    TOKENS_FILE.unlink()
                    return None, None
            st.session_state.kite_session = kite
            st.session_state.kite_session_time = datetime.now()
            st.session_state.token_saved_at = saved_at
            return kite, saved_at
        except:
            return None, None
    return None, None

def authenticate_kite(request_token):
    try:
        kite = KiteConnect(api_key=API_KEY)
        session = kite.generate_session(request_token, api_secret=API_SECRET)
        token_data = {
            "api_key": API_KEY,
            "access_token": session["access_token"],
            "saved_at": datetime.now().isoformat()
        }
        with open(TOKENS_FILE, "w") as f:
            json.dump(token_data, f, indent=2)
        kite.set_access_token(session["access_token"])
        kite.margins()
        return kite, datetime.now()
    except Exception as e:
        raise Exception(f"Auth failed: {str(e)}")

def get_market_status():
    try:
        now = datetime.now()
        market_open = dt_time(9, 15)
        market_close = dt_time(15, 30)
        is_weekday = now.weekday() < 5
        is_market_hours = market_open <= now.time() <= market_close
        if is_weekday and is_market_hours:
            return "OPEN", "🟢", "success"
        elif is_weekday and now.time() < market_open:
            return "PRE-MARKET", "🟡", "warning"
        elif is_weekday and now.time() > market_close:
            return "CLOSED", "🔴", "error"
        else:
            return "WEEKEND", "🔴", "error"
    except:
        return "UNKNOWN", "⚪", "info"

def save_dashboard_cache(data: dict):
    try:
        data["cached_at"] = datetime.now().isoformat()
        with open(DASHBOARD_CACHE_FILE, "wb") as f:
            pickle.dump(data, f)
    except Exception as e:
        print(f"Error saving cache: {e}")

def load_dashboard_cache():
    if not DASHBOARD_CACHE_FILE.exists():
        return None
    try:
        with open(DASHBOARD_CACHE_FILE, "rb") as f:
            data = pickle.load(f)
        cached_at = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
        now = datetime.now()
        if cached_at.tzinfo:
            cached_at = cached_at.replace(tzinfo=None)
        if now.tzinfo:
            now = now.replace(tzinfo=None)
        if (now - cached_at).total_seconds() < 86400:
            return data
    except Exception as e:
        print(f"Error loading cache: {e}")
    return None

def ensure_instruments(kite: KiteConnect) -> pd.DataFrame:
    if INSTRUMENTS_FILE.exists():
        try:
            df = pd.read_parquet(INSTRUMENTS_FILE)
            need = {"segment","name","tradingsymbol","instrument_token","expiry","strike","instrument_type"}
            if need.issubset(df.columns):
                return df
        except:
            pass
    ins = kite.instruments()
    raw = pd.DataFrame(ins)
    cols = ["segment","name","tradingsymbol","instrument_token","expiry","strike","instrument_type","exchange"]
    for c in cols:
        if c not in raw.columns:
            raw[c] = np.nan
    df = raw[cols].copy()
    for c in ["segment","name","tradingsymbol","instrument_type","exchange"]:
        df[c] = df[c].astype("string")
    df["instrument_token"] = pd.to_numeric(df["instrument_token"], errors="coerce").astype("Int64")
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce")
    df = df.dropna(subset=["instrument_token"]).copy()
    df["instrument_token"] = df["instrument_token"].astype(np.int64, copy=False)
    df = df.drop_duplicates(subset=["instrument_token"]).reset_index(drop=True)
    df.to_parquet(INSTRUMENTS_FILE, index=False)
    return df

def discover_indices_with_fo(ins_df: pd.DataFrame) -> list:
    fut = ins_df[ins_df["segment"].isin(DERIV_FUT_SEGMENTS)].copy()
    if fut.empty: 
        return []
    names = sorted(set(fut["name"].dropna().unique().tolist()))
    return [n for n in names if n in INDEX_NAME_WHITELIST]

def discover_stocks_with_fo(ins_df: pd.DataFrame) -> list:
    """Load F&O stocks from fno_master.json file"""
    fno_json_path = Path("fno_master.json")
    
    if fno_json_path.exists():
        try:
            with open(fno_json_path, 'r') as f:
                fno_stocks = json.load(f)
            print(f"✓ Loaded {len(fno_stocks)} F&O stocks from fno_master.json")
            return sorted(fno_stocks)
        except Exception as e:
            print(f"Error loading fno_master.json: {e}")
    
    fut = ins_df[ins_df["segment"].isin(DERIV_FUT_SEGMENTS)].copy()
    if fut.empty:
        return []
    all_names = set(fut["name"].dropna().unique().tolist())
    stock_names = [n for n in all_names if n not in INDEX_NAME_WHITELIST]
    print(f"Auto-detected {len(stock_names)} F&O stocks")
    return sorted(stock_names)[:30]

def load_sector_mapping():
    """Load sector mapping from FO Stocks with Indices.csv"""
    possible_paths = [
        Path("FO Stocks with Indices.csv"),
        Path("F&O Stocks with Indices.csv"),
    ]
    
    sector_map = {}
    csv_path = None
    
    for path in possible_paths:
        if path.exists():
            csv_path = path
            break
    
    if csv_path is None:
        print(f"⚠️ Sector mapping file not found")
        return sector_map
    
    try:
        df = pd.read_csv(csv_path)
        for _, row in df.iterrows():
            symbol = str(row.get("Symbol", "")).strip().upper()
            sector = str(row.get("Nifty Index", "")).strip()
            if symbol and sector:
                sector_map[symbol] = sector
        print(f"✓ Loaded sector mapping for {len(sector_map)} stocks")
    except Exception as e:
        print(f"Error loading sector mapping: {e}")
    
    return sector_map

def nearest_fut(ins_df: pd.DataFrame, name: str):
    df = ins_df[(ins_df["segment"].isin(DERIV_FUT_SEGMENTS)) & (ins_df["name"]==name)].copy()
    if df.empty: return None
    df["expiry"] = pd.to_datetime(df["expiry"])
    today = pd.Timestamp.today().normalize()
    df = df[df["expiry"]>=today].sort_values("expiry")
    return df.iloc[0].to_dict() if not df.empty else None

def index_opt_chain(ins_df: pd.DataFrame, name: str):
    df = ins_df[(ins_df["segment"].isin(DERIV_OPT_SEGMENTS)) & (ins_df["name"]==name)].copy()
    if df.empty: return df
    df["expiry"] = pd.to_datetime(df["expiry"])
    today = pd.Timestamp.today().normalize()
    df = df[df["expiry"]>=today]
    if df.empty: return df
    expiry = df["expiry"].min()
    return df[df["expiry"]==expiry].copy()

def select_atm_band(options_df: pd.DataFrame, ltp: float, step: int):
    if options_df.empty: return options_df
    strikes = sorted(options_df["strike"].unique().tolist())
    if not strikes: return options_df.head(0)
    atm = min(strikes, key=lambda k: abs(k - ltp))
    band_size = 10 if step >= 25 else 3
    band = [k for k in strikes if abs(k - atm) <= band_size*step]
    return options_df[options_df["strike"].isin(band)]

def get_spot_index_token(ins_df: pd.DataFrame, index_name: str):
    """Get spot index token for NSE indices"""
    spot_mapping = {
        "NIFTY": "NIFTY 50",
        "BANKNIFTY": "NIFTY BANK",
        "FINNIFTY": "NIFTY FIN SERVICE",
        "MIDCPNIFTY": "NIFTY MIDCAP SELECT",
        "SENSEX": "SENSEX",
        # New 10 indices - display names
        "NIFTY MIDCAP 50": "NIFTY MIDCAP 50",
        "NIFTY AUTO": "NIFTY AUTO",
        "NIFTY PHARMA": "NIFTY PHARMA",
        "NIFTY METAL": "NIFTY METAL",
        "NIFTY ENERGY": "NIFTY ENERGY",
        "NIFTY FMCG": "NIFTY FMCG",
        "NIFTY REALTY": "NIFTY REALTY",
        "NIFTY PSU BANK": "NIFTY PSU BANK",
        "NIFTY INFRA": "NIFTY INFRA",
        "NIFTY OIL & GAS": "NIFTY OIL & GAS",
        "FINNIFTY": "NIFTY FIN SERVICE",
        "MIDCPNIFTY": "NIFTY MID SELECT",
        "SENSEX": "SENSEX"
    }
    
    spot_symbol = spot_mapping.get(index_name)
    if not spot_symbol:
        return None
    
    spot = ins_df[
        (ins_df["segment"] == "INDICES") & 
        (ins_df["tradingsymbol"] == spot_symbol)
    ]
    
    if not spot.empty:
        return int(spot.iloc[0]["instrument_token"])
    return None

def build_subscriptions(kite: KiteConnect, ins_df: pd.DataFrame):
    tokens = set()
    metadata_rows = []
    step_map = {
        "BANKNIFTY": 100, "NIFTY": 50, "FINNIFTY": 50, "MIDCPNIFTY": 25, "SENSEX": 100,
        # New indices (using reasonable defaults, adjust if needed)
        "NIFTY MIDCAP 50": 50, "NIFTY AUTO": 50, "NIFTY PHARMA": 50, 
        "NIFTY METAL": 50, "NIFTY ENERGY": 50, "NIFTY FMCG": 50,
        "NIFTY REALTY": 25, "NIFTY PSU BANK": 25, "NIFTY INFRA": 50, "NIFTY OIL & GAS": 50
    }
    fallback_prices = {"NIFTY": 24000, "BANKNIFTY": 50000, "FINNIFTY": 22000, "MIDCPNIFTY": 10000, "SENSEX": 78000}
    
    print("\n" + "="*50)
    print("BUILDING SUBSCRIPTIONS")
    print("="*50)
    print("\n📊 INDICES:")
    
    for idx in engine.indices_with_fo:
        try:
            spot_token = get_spot_index_token(ins_df, idx)
            if spot_token:
                tokens.add(spot_token)
                spot_meta = {
                    "instrument_token": spot_token,
                    "type": "SPOT",
                    "category": "INDEX",
                    "index_name": idx,
                    "name": idx
                }
                metadata_rows.append(spot_meta)
                print(f"  {idx}: Added SPOT index token")
            
            fut = nearest_fut(ins_df, idx)
            if not fut:
                continue
            fut_token = int(fut["instrument_token"])
            tokens.add(fut_token)
            fut_copy = fut.copy()
            fut_copy["type"] = "FUT"
            fut_copy["category"] = "INDEX"
            fut_copy["index_name"] = idx
            metadata_rows.append(fut_copy)
            try:
                q = kite.quote([fut_token])
                ltp = list(q.values())[0]["last_price"]
            except:
                ltp = fallback_prices.get(idx, 24000)
            oc = index_opt_chain(ins_df, idx)
            if not oc.empty:
                oc_sel = select_atm_band(oc, ltp, step_map.get(idx, 50))
                if not oc_sel.empty:
                    opt_tokens = oc_sel["instrument_token"].astype(int).tolist()
                    tokens.update(opt_tokens)
                    oc_sel = oc_sel.copy()
                    oc_sel["type"] = oc_sel["instrument_type"]
                    oc_sel["category"] = "INDEX"
                    oc_sel["index_name"] = idx
                    metadata_rows.extend(oc_sel.to_dict("records"))
                    ce_count = len(oc_sel[oc_sel["instrument_type"] == "CE"])
                    pe_count = len(oc_sel[oc_sel["instrument_type"] == "PE"])
                    print(f"  {idx}: {len(opt_tokens)} options ({ce_count} CE + {pe_count} PE)")
        except Exception as e:
            print(f"  Error {idx}: {e}")
    
    print(f"\n📈 STOCKS (Total: {len(engine.stocks_with_fo)}):")
    stock_count = 0
    for stock in engine.stocks_with_fo:
        try:
            fut = nearest_fut(ins_df, stock)
            if not fut:
                continue
            fut_token = int(fut["instrument_token"])
            tokens.add(fut_token)
            fut["type"] = "FUT"
            fut["category"] = "STOCK"
            metadata_rows.append(fut)
            try:
                q = kite.quote([fut_token])
                ltp = list(q.values())[0]["last_price"]
            except:
                continue
            if ltp > 5000:
                step = 100
            elif ltp > 1000:
                step = 50
            elif ltp > 500:
                step = 25
            elif ltp > 100:
                step = 10
            else:
                step = 5
            oc = index_opt_chain(ins_df, stock)
            if not oc.empty:
                oc_sel = select_atm_band(oc, ltp, step)
                if not oc_sel.empty:
                    opt_tokens = oc_sel["instrument_token"].astype(int).tolist()
                    tokens.update(opt_tokens)
                    oc_sel = oc_sel.copy()
                    oc_sel["type"] = oc_sel["instrument_type"]
                    oc_sel["category"] = "STOCK"
                    metadata_rows.extend(oc_sel.to_dict("records"))
                    ce_count = len(oc_sel[oc_sel["instrument_type"] == "CE"])
                    pe_count = len(oc_sel[oc_sel["instrument_type"] == "PE"])
                    stock_count += 1
                    if stock_count <= 10:
                        print(f"  {stock:12s}: {len(opt_tokens):2d} options ({ce_count} CE + {pe_count} PE)")
        except:
            pass
    
    if stock_count > 10:
        print(f"  ... and {stock_count - 10} more stocks")
    
    result = sorted(list(tokens))
    if metadata_rows:
        engine.token_meta = pd.DataFrame(metadata_rows)
        engine.token_meta = engine.token_meta.drop_duplicates(subset=["instrument_token"])
        engine.token_meta["instrument_token"] = engine.token_meta["instrument_token"].astype(int)
    
    print(f"\n{'='*50}")
    print(f"✓ TOTAL: {len(result)} instruments")
    print(f"  Indices: {len(engine.indices_with_fo)}")
    print(f"  Stocks: {len(engine.stocks_with_fo)}")
    print("="*50 + "\n")
    return result

def polling_loop():
    print("\n" + "="*50)
    print("STARTING LIVE MOMENTUM TRACKER")
    print("Polling every 10 seconds with actionable alerts")
    print("="*50 + "\n")
    
    current_date = datetime.now().date()
    
    while not engine.stop_flag:
        try:
            if datetime.now().date() != current_date:
                print(f"🗓️ New trading day detected - clearing caches")
                engine.cached_prev_close.clear()
                engine.first_15min_range.clear()
                engine.range_status.clear()
                # MEMORY FIX: Force garbage collection on new day
                import gc
                gc.collect()
                print("✅ Memory cleanup - garbage collection done")
                
                engine.futures_volume_history.clear()
                engine.chart_update_counter = 0
                reset_volume_data()  # Reset volume charts  # PHASE 1: Reset chart counter
                current_date = datetime.now().date()
            
            if not engine.subscribe_tokens or engine.token_meta.empty:
                time.sleep(1)
                continue
            
            chunks = [engine.subscribe_tokens[i:i+500] for i in range(0, len(engine.subscribe_tokens), 500)]
            all_quotes = {}
            for chunk in chunks:
                try:
                    quotes = engine.kite.quote(chunk)
                    all_quotes.update(quotes)
                except Exception as e:
                    print(f"Poll error: {e}")
            
            if all_quotes:
                indices_data = {}
                stocks_data = {}
                
                for idx_name in engine.indices_with_fo:
                    idx_meta = engine.token_meta[
                        (engine.token_meta.get("index_name") == idx_name) | 
                        (engine.token_meta.get("name") == idx_name)
                    ].copy()
                    
                    if "category" in idx_meta.columns:
                        idx_meta = idx_meta[idx_meta["category"] == "INDEX"]
                    
                    if idx_meta.empty:
                        continue
                        
                    ce_flow = 0.0
                    pe_flow = 0.0
                    
                    spot_rows = idx_meta[idx_meta.get("type") == "SPOT"]
                    index_price = None
                    index_change_pct = None
                    
                    if not spot_rows.empty:
                        spot_token = int(spot_rows.iloc[0]["instrument_token"])
                        spot_token_str = str(spot_token)
                        
                        if spot_token_str in all_quotes:
                            quote = all_quotes[spot_token_str]
                            index_price = quote.get("last_price", None)
                            
                            net_change = quote.get("net_change", None)
                            prev_close = None
                            
                            if net_change is not None and index_price:
                                prev_close = index_price - net_change
                                if prev_close > 0:
                                    engine.cached_prev_close[idx_name] = prev_close
                                    index_change_pct = (net_change / prev_close) * 100
                                    print(f"✓ {idx_name} SPOT: Price={index_price:.2f}, Net Change={net_change:+.2f}, Prev Close={prev_close:.2f}, Change={index_change_pct:+.2f}% [CACHED]")
                                else:
                                    index_change_pct = None
                            else:
                                if idx_name in engine.cached_prev_close:
                                    prev_close = engine.cached_prev_close[idx_name]
                                    if prev_close > 0 and index_price:
                                        index_change_pct = ((index_price - prev_close) / prev_close) * 100
                                        print(f"✓ {idx_name} SPOT: Price={index_price:.2f}, Prev Close={prev_close:.2f} (cached), Change={index_change_pct:+.2f}%")
                                    else:
                                        index_change_pct = None
                                else:
                                    prev_close = quote.get("last_close", None) or quote.get("previous_close", None)
                                    
                                    if prev_close is None:
                                        ohlc = quote.get("ohlc", {})
                                        if isinstance(ohlc, dict):
                                            prev_close = ohlc.get("previous_close", None) or ohlc.get("last_close", None)
                                    
                                    if prev_close and prev_close > 0 and index_price:
                                        engine.cached_prev_close[idx_name] = prev_close
                                        index_change_pct = ((index_price - prev_close) / prev_close) * 100
                                        print(f"✓ {idx_name} SPOT: Price={index_price:.2f}, Prev Close={prev_close:.2f}, Change={index_change_pct:+.2f}% [CACHED]")
                                    else:
                                        ohlc = quote.get("ohlc", {})
                                        if isinstance(ohlc, dict):
                                            open_price = ohlc.get("open", None)
                                            if open_price and open_price > 0 and index_price:
                                                index_change_pct = ((index_price - open_price) / open_price) * 100
                                                print(f"⚠️ {idx_name} SPOT: Price={index_price:.2f}, Open={open_price:.2f}, Change={index_change_pct:+.2f}% (FALLBACK - no cache)")
                                            else:
                                                index_change_pct = None
                                                print(f"❌ {idx_name} SPOT: Could not calculate change %")
                    
                    for _, row in idx_meta.iterrows():
                        token = int(row["instrument_token"])
                        token_str = str(token)
                        if token_str in all_quotes:
                            quote_data = all_quotes[token_str]
                            volume = quote_data.get("volume", 0)
                            if "type" in row and row["type"] == "CE":
                                ce_flow += volume
                            elif "type" in row and row["type"] == "PE":
                                pe_flow += volume
                            elif "instrument_type" in row:
                                if row["instrument_type"] == "CE":
                                    ce_flow += volume
                                elif row["instrument_type"] == "PE":
                                    pe_flow += volume
                    
                    indices_data[idx_name] = {
                        "ce_flow": ce_flow,
                        "pe_flow": pe_flow,
                        "net_flow": ce_flow - pe_flow,
                        "price": index_price,
                        "change_pct": index_change_pct
                    }
                    
                    now = datetime.now()
                    print(f"DEBUG: Processing {idx_name}, Time={now.strftime('%H:%M:%S')}, After 9:30? {now.time() >= dt_time(9, 30)}")
                    
                    if now.time() >= dt_time(9, 30):
                        if idx_name not in engine.first_15min_range:
                            print(f"DEBUG: Getting first 15min range for {idx_name}")
                            get_first_15min_range(idx_name, now)
                        
                        futures_volume = None
                        avg_volume = None
                        
                        fut_meta = engine.token_meta[
                            (engine.token_meta.get("index_name") == idx_name) &
                            (engine.token_meta.get("type") == "FUT") &
                            (engine.token_meta.get("category") == "INDEX")
                        ]
                        
                        print(f"DEBUG: {idx_name} - Found {len(fut_meta)} futures contracts")
                        
                        if not fut_meta.empty:
                            fut_token = int(fut_meta.iloc[0]["instrument_token"])
                            fut_token_str = str(fut_token)
                            
                            if fut_token_str in all_quotes:
                                quote_data = all_quotes[fut_token_str]
                                futures_volume = quote_data.get("volume", 0)
                                
                                print(f"DEBUG: {idx_name} Futures Volume = {futures_volume:,}")
                                
                                if idx_name not in engine.futures_volume_history:
                                    engine.futures_volume_history[idx_name] = deque(maxlen=15)
                                
                                engine.futures_volume_history[idx_name].append(futures_volume)
                                
                                if len(engine.futures_volume_history[idx_name]) >= 5:
                                    avg_volume = np.mean(list(engine.futures_volume_history[idx_name]))
                                    print(f"DEBUG: {idx_name} Avg Volume = {avg_volume:,.0f}, Ratio = {futures_volume/avg_volume:.2f}x")
                        
                        if index_price and idx_name in engine.first_15min_range:
                            print(f"DEBUG: {idx_name} has range data, checking breakout...")
                            
                            sentiment_text, _, _, _, _, _, _ = get_smart_sentiment(index_change_pct, ce_flow - pe_flow)
                            
                            range_status, alert_message = check_range_breakout(
                                idx_name, 
                                index_price, 
                                sentiment_text, 
                                futures_volume, 
                                avg_volume
                            )
                            
                            print(f"DEBUG: {idx_name} Range Status = {range_status}")
                            
                            indices_data[idx_name]["range_status"] = range_status
                            indices_data[idx_name]["range_high"] = engine.first_15min_range[idx_name]["high"]
                            indices_data[idx_name]["range_low"] = engine.first_15min_range[idx_name]["low"]
                            indices_data[idx_name]["futures_volume"] = futures_volume
                            indices_data[idx_name]["avg_volume"] = avg_volume
                            
                            if alert_message:
                                add_alert(alert_message, "warning")
                        else:
                            print(f"DEBUG: {idx_name} - Missing data. Price={index_price}, Has Range={idx_name in engine.first_15min_range}")
                    
                    # PHASE 1: Save historical data to CSV
                    # DEBUG: Log why data might not save
                    print(f"[HIST] {idx_name}: price={index_price}, change%={index_change_pct}, ce_flow={ce_flow:.0f}, pe_flow={pe_flow:.0f}")
                    
                    if not index_price:
                        print(f"⚠️ [HIST] {idx_name} - SKIP: No index_price")
                    elif index_change_pct is None:
                        print(f"⚠️ [HIST] {idx_name} - SKIP: index_change_pct is None (price={index_price:.2f})")
                    
                    if index_price and index_change_pct is not None:
                        print(f"✅ [HIST] {idx_name} - SAVING data to CSV")
                        sentiment_text, _, _, _, _, _, _ = get_smart_sentiment(index_change_pct, ce_flow - pe_flow)
                        
                        hist_row = {
                            'timestamp': datetime.now().isoformat(),
                            'index_name': idx_name,
                            'spot_price': index_price,
                            'price_change_pct': index_change_pct,
                            'ce_flow': ce_flow,
                            'pe_flow': pe_flow,
                            'net_flow': ce_flow - pe_flow,
                            'delta_1min_ce': None,
                            'delta_1min_pe': None,
                            'delta_5min_ce': None,
                            'delta_5min_pe': None,
                            'sentiment': sentiment_text,
                            'range_status': indices_data[idx_name].get('range_status', 'N/A'),
                            'futures_volume': indices_data[idx_name].get('futures_volume'),
                            'avg_volume': indices_data[idx_name].get('avg_volume'),
                            'volume_ratio': None
                        }
                        
                        save_historical_data(idx_name, hist_row)
                
                # ============================================
                # VOLUME CHARTS DATA COLLECTION (REQUIREMENT 4)
                # ============================================
                if 'NIFTY' in indices_data:
                    nifty_data = indices_data['NIFTY']
                    if nifty_data.get('price'):
                        try:
                            log_chart_debug(f"Calling update_volume_data for NIFTY (spot={nifty_data['price']:.2f})")
                            
                            update_volume_data(
                                kite=engine.kite,
                                ins_df=engine.ins_df,
                                index_name='NIFTY',
                                spot_price=nifty_data['price'],
                                all_quotes=all_quotes,
                                token_meta=engine.token_meta
                            )
                            
                            log_chart_debug(f"Volume data updated - spike_queue={len(volume_state.spike_queue)}, ce_pe_history={len(volume_state.ce_pe_history)}")
                            
                            # Check for volume spike alerts (>5x)
                            check_volume_alerts(add_alert)
                        except Exception as e:
                            log_chart_debug(f"Volume charts error: {e}")
                            import traceback
                            log_chart_debug(f"Traceback: {traceback.format_exc()}")
                    else:
                        log_chart_debug(f"NIFTY data missing price - nifty_data={nifty_data}")
                else:
                    log_chart_debug(f"NIFTY not in indices_data - available={list(indices_data.keys())}")
                
                for stock_name in engine.stocks_with_fo:
                    stock_meta = engine.token_meta[
                        (engine.token_meta["name"] == stock_name) & 
                        (engine.token_meta.get("category", "STOCK") == "STOCK")
                    ].copy()
                    if stock_meta.empty:
                        continue
                    
                    ce_flow = 0.0
                    pe_flow = 0.0
                    stock_price = None
                    stock_change_pct = None
                    
                    # Get stock futures price
                    fut_rows = stock_meta[stock_meta.get("type") == "FUT"]
                    if not fut_rows.empty:
                        fut_token = int(fut_rows.iloc[0]["instrument_token"])
                        fut_token_str = str(fut_token)
                        
                        if fut_token_str in all_quotes:
                            fut_quote = all_quotes[fut_token_str]
                            stock_price = fut_quote.get("last_price", None)

                            # Calculate change % - Try multiple methods
                            stock_change_pct = None

                            # Method 1: Direct change percentage from Kite (most reliable)
                            # BUT: Skip if it's exactly 0 (likely market closed or no data)
                            change_value = fut_quote.get("change")
                            if change_value is not None and change_value != 0:
                                stock_change_pct = change_value

                            # Method 2: Calculate from net_change
                            if stock_change_pct is None and stock_price:
                                net_change = fut_quote.get("net_change")
                                if net_change is not None and net_change != 0:
                                    prev_close = stock_price - net_change
                                    if prev_close > 0:
                                        stock_change_pct = (net_change / prev_close) * 100

                            # Method 3: Use OHLC data (works even when market closed)
                            if stock_change_pct is None and stock_price:
                                ohlc = fut_quote.get("ohlc", {})
                                if isinstance(ohlc, dict):
                                    # Try different previous close fields
                                    prev_close = (ohlc.get("previous_close") or
                                                 ohlc.get("prev_close") or
                                                 ohlc.get("close"))

                                    # If prev_close is same as current price, it's likely today's close
                                    # So check if there's an open price different from close
                                    if prev_close and prev_close > 0:
                                        # If close == last_price, use open as reference (intraday change)
                                        open_price = ohlc.get("open")
                                        if abs(prev_close - stock_price) < 0.01 and open_price:
                                            # Market might be closed, calculate from open
                                            if abs(open_price - stock_price) > 0.01:
                                                stock_change_pct = ((stock_price - open_price) / open_price) * 100
                                        else:
                                            # Normal case: calculate from previous close
                                            stock_change_pct = ((stock_price - prev_close) / prev_close) * 100
                    
                    # Calculate CE/PE flows from options
                    for _, row in stock_meta.iterrows():
                        token = int(row["instrument_token"])
                        token_str = str(token)
                        if token_str in all_quotes:
                            quote_data = all_quotes[token_str]
                            volume = quote_data.get("volume", 0)
                            if "type" in row and row["type"] == "CE":
                                ce_flow += volume
                            elif "type" in row and row["type"] == "PE":
                                pe_flow += volume
                            elif "instrument_type" in row:
                                if row["instrument_type"] == "CE":
                                    ce_flow += volume
                                elif row["instrument_type"] == "PE":
                                    pe_flow += volume
                    
                    stocks_data[stock_name] = {
                        "price": stock_price,
                        "change_pct": stock_change_pct,
                        "ce_flow": ce_flow,
                        "pe_flow": pe_flow,
                        "net_flow": ce_flow - pe_flow
                    }

                # Log stock data collection with sample
                if stocks_data:
                    print(f"✅ Collected data for {len(stocks_data)} stocks")
                    # Show sample with change % to verify it's working
                    sample_stocks = list(stocks_data.items())[:3]
                    for name, data in sample_stocks:
                        chg = data.get('change_pct')
                        if chg is not None:
                            print(f"   {name}: ₹{data.get('price'):.2f} ({chg:+.2f}%)")
                        else:
                            print(f"   {name}: ₹{data.get('price'):.2f} (change% = None)")

                    # DEBUG: Show what raw data looks like for first stock
                    if len(stocks_data) > 0:
                        first_stock = list(stocks_data.keys())[0]
                        fut_rows_debug = engine.token_meta[
                            (engine.token_meta["name"] == first_stock) &
                            (engine.token_meta.get("type") == "FUT")
                        ]
                        if not fut_rows_debug.empty:
                            fut_token_debug = str(int(fut_rows_debug.iloc[0]["instrument_token"]))
                            if fut_token_debug in all_quotes:
                                quote_debug = all_quotes[fut_token_debug]
                                print(f"   DEBUG {first_stock} quote: change={quote_debug.get('change')}, net_change={quote_debug.get('net_change')}")
                                ohlc_debug = quote_debug.get('ohlc', {})
                                if ohlc_debug:
                                    print(f"   DEBUG {first_stock} OHLC: open={ohlc_debug.get('open')}, close={ohlc_debug.get('close')}, prev_close={ohlc_debug.get('previous_close')}")
                
                total_indices_ce = sum(d["ce_flow"] for d in indices_data.values())
                total_indices_pe = sum(d["pe_flow"] for d in indices_data.values())
                total_stocks_ce = sum(d["ce_flow"] for d in stocks_data.values())
                total_stocks_pe = sum(d["pe_flow"] for d in stocks_data.values())
                total_ce = total_indices_ce + total_stocks_ce
                total_pe = total_indices_pe + total_stocks_pe
                net_flow = total_ce - total_pe
                
                if abs(net_flow) < 10000:
                    composite_score = 50.0
                    signal_band = "Sideways"
                    stance = "Wait"
                elif net_flow > 0:
                    composite_score = min(100, 50 + (net_flow / 1000))
                    signal_band = "Bullish" if composite_score > 65 else "Mild Bullish"
                    stance = "Long" if composite_score > 65 else "Wait"
                else:
                    composite_score = max(0, 50 - (abs(net_flow) / 1000))
                    signal_band = "Bearish" if composite_score < 35 else "Mild Bearish"
                    stance = "Short" if composite_score < 35 else "Wait"
                
                # ====================
                # PROCESS STOCKS DATA
                # ====================
                for stock_name in engine.stocks_with_fo:
                    try:
                        stock_meta = engine.token_meta[
                            (engine.token_meta.get("name") == stock_name) &
                            (engine.token_meta.get("category") == "STOCK")
                        ].copy()
                        
                        if stock_meta.empty:
                            continue
                        
                        stock_ce_flow = 0.0
                        stock_pe_flow = 0.0
                        stock_price = None
                        stock_change_pct = None
                        
                        # Get stock futures price
                        fut_rows = stock_meta[stock_meta.get("type") == "FUT"]
                        if not fut_rows.empty:
                            fut_token = int(fut_rows.iloc[0]["instrument_token"])
                            fut_token_str = str(fut_token)
                            
                            if fut_token_str in all_quotes:
                                fut_quote = all_quotes[fut_token_str]
                                stock_price = fut_quote.get("last_price", None)

                                # Calculate change % - Try multiple methods
                                stock_change_pct = None

                                # Method 1: Direct change percentage from Kite (most reliable)
                                # BUT: Skip if it's exactly 0 (likely market closed or no data)
                                change_value = fut_quote.get("change")
                                if change_value is not None and change_value != 0:
                                    stock_change_pct = change_value

                                # Method 2: Calculate from net_change
                                if stock_change_pct is None and stock_price:
                                    net_change = fut_quote.get("net_change")
                                    if net_change is not None and net_change != 0:
                                        prev_close = stock_price - net_change
                                        if prev_close > 0:
                                            stock_change_pct = (net_change / prev_close) * 100

                                # Method 3: Use OHLC data (works even when market closed)
                                if stock_change_pct is None and stock_price:
                                    ohlc = fut_quote.get("ohlc", {})
                                    if isinstance(ohlc, dict):
                                        # Try different previous close fields
                                        prev_close = (ohlc.get("previous_close") or
                                                     ohlc.get("prev_close") or
                                                     ohlc.get("close"))

                                        # If prev_close is same as current price, it's likely today's close
                                        # So check if there's an open price different from close
                                        if prev_close and prev_close > 0:
                                            # If close == last_price, use open as reference (intraday change)
                                            open_price = ohlc.get("open")
                                            if abs(prev_close - stock_price) < 0.01 and open_price:
                                                # Market might be closed, calculate from open
                                                if abs(open_price - stock_price) > 0.01:
                                                    stock_change_pct = ((stock_price - open_price) / open_price) * 100
                                            else:
                                                # Normal case: calculate from previous close
                                                stock_change_pct = ((stock_price - prev_close) / prev_close) * 100
                        
                        # Calculate CE/PE flows
                        for _, row in stock_meta.iterrows():
                            token = int(row["instrument_token"])
                            token_str = str(token)
                            if token_str in all_quotes:
                                quote_data = all_quotes[token_str]
                                volume = quote_data.get("volume", 0)
                                if "type" in row and row["type"] == "CE":
                                    stock_ce_flow += volume
                                elif "type" in row and row["type"] == "PE":
                                    stock_pe_flow += volume
                        
                        # Store stock data
                        stocks_data[stock_name] = {
                            "price": stock_price,
                            "change_pct": stock_change_pct,
                            "ce_flow": stock_ce_flow,
                            "pe_flow": stock_pe_flow,
                            "net_flow": stock_ce_flow - stock_pe_flow
                        }
                    except Exception as e:
                        pass

                # Log top stocks by net flow
                if stocks_data and len(stocks_data) > 0:
                    top_5 = sorted(stocks_data.items(), key=lambda x: abs(x[1].get("net_flow", 0)), reverse=True)[:5]
                    print(f"📊 Top 5 stocks by net flow: {', '.join([s[0] for s in top_5])}")
                
                
                flow_snapshot = {
                    "timestamp": datetime.now().isoformat(),
                    "indices_ce": total_indices_ce,
                    "indices_pe": total_indices_pe,
                    "stocks_ce": total_stocks_ce,
                    "stocks_pe": total_stocks_pe,
                    "indices_net": total_indices_ce - total_indices_pe,
                    "stocks_net": total_stocks_ce - total_stocks_pe,
                    "indices_data": indices_data,
                    "stocks_data": stocks_data
                }
                
                deltas = calculate_deltas(flow_snapshot)
                flow_history.append(flow_snapshot)
                save_flow_history(flow_snapshot)
                

                # ====================
                # NIFTY FUTURES DATA COLLECTION
                # ====================
                nifty_futures_data = None
                if engine.nifty_fut_token:
                    fut_token_str = str(engine.nifty_fut_token)
                    if fut_token_str in all_quotes:
                        fut_quote = all_quotes[fut_token_str]
                        
                        fut_price = fut_quote.get('last_price', 0)
                        fut_net_change = fut_quote.get('net_change', 0)
                        fut_prev_close = fut_price - fut_net_change if fut_net_change else 0
                        fut_change_pct = (fut_net_change / fut_prev_close * 100) if fut_prev_close > 0 else 0
                        
                        fut_oi = fut_quote.get('oi', 0)
                        fut_oi_day_low = fut_quote.get('oi_day_low', 0)
                        
                        fut_volume = fut_quote.get('volume', 0)
                        fut_buy_qty = fut_quote.get('buy_quantity', 0)
                        fut_sell_qty = fut_quote.get('sell_quantity', 0)
                        
                        # Calculate buyers vs sellers
                        if fut_change_pct > 0:
                            buyers = fut_buy_qty if fut_buy_qty > 0 else fut_volume * 0.6
                            sellers = fut_sell_qty if fut_sell_qty > 0 else fut_volume * 0.4
                        else:
                            buyers = fut_buy_qty if fut_buy_qty > 0 else fut_volume * 0.4
                            sellers = fut_sell_qty if fut_sell_qty > 0 else fut_volume * 0.6
                        
                        nifty_futures_data = {
                            'price': fut_price,
                            'change_pct': fut_change_pct,
                            'buyers': int(buyers),
                            'sellers': int(sellers),
                            'oi': int(fut_oi),
                            'oi_change': int(fut_oi - fut_oi_day_low) if fut_oi_day_low else 0,
                            'symbol': engine.nifty_fut_symbol,
                            'expiry': engine.nifty_fut_expiry
                        }
                        # Store in session state to persist across refreshes
                        st.session_state.nifty_futures_data = nifty_futures_data
                        print(f"✓ Futures: {engine.nifty_fut_symbol} Price={fut_price:.2f} Change={fut_change_pct:+.2f}% OI={fut_oi}")

                # ============================================
                # TOP 10 STOCKS TRACKING & NEW ENTRY ALERTS
                # ============================================
                if stocks_data:
                    # Sort by absolute net flow to get top stocks
                    sorted_stocks = sorted(stocks_data.items(), key=lambda x: abs(x[1].get("net_flow", 0)), reverse=True)

                    # Get current Top 10 stocks
                    current_top_10 = set([stock[0] for stock in sorted_stocks[:10]])

                    # Find NEW entries (stocks that just entered Top 10)
                    new_entries = current_top_10 - engine.top_10_stocks

                    # Alert ONLY for NEW stocks entering Top 10
                    if new_entries:
                        for stock_name in new_entries:
                            # Find this stock's data
                            stock_data = stocks_data.get(stock_name)
                            if not stock_data:
                                continue

                            stock_price = stock_data.get("price")
                            change_pct = stock_data.get("change_pct")
                            net_flow = stock_data.get("net_flow", 0)

                            # Skip if missing critical data
                            if stock_price is None or abs(net_flow) < 50000:
                                continue

                            # Find rank in Top 10
                            rank = next((i+1 for i, (name, _) in enumerate(sorted_stocks[:10]) if name == stock_name), None)

                            # Send "NEW TOP 10 ENTRY" alert
                            emoji = "🔥" if rank <= 3 else "⭐"
                            signal = f"NEW TOP {rank} ENTRY"

                            flow_direction = "BULLISH" if net_flow > 0 else "BEARISH"
                            flow_emoji = "🟢" if net_flow > 0 else "🔴"

                            price_str = f"₹{stock_price:,.2f}"
                            change_emoji = "🟢" if change_pct and change_pct > 0 else "🔴"
                            change_str = f"{change_emoji}{change_pct:+.2f}%" if change_pct else ""
                            flow_str = f"{flow_emoji}{format_number(net_flow)}"

                            telegram_message = f"{emoji} {signal} - {stock_name}\n"
                            telegram_message += f"{price_str} {change_str} | Flow {flow_str}\n"
                            telegram_message += f"📊 Rank #{rank} | {flow_direction} momentum"

                            try:
                                # DISABLED: Stock alerts temporarily disabled
                                # send_telegram_alert(telegram_message)
                                print(f"🔕 ALERT DISABLED - NEW Top 10 Entry: #{rank} {stock_name} (Net Flow: {format_number(net_flow)})")
                            except Exception as e:
                                print(f"Error sending Top 10 alert: {e}")

                    # Update Top 10 tracking
                    engine.top_10_stocks = current_top_10

                    # ============================================
                    # BULLISH/BEARISH ALERTS FOR TOP 10 STOCKS
                    # ============================================
                    # Check each Top 10 stock for BULLISH or BEARISH conditions
                    for stock_name, _ in sorted_stocks[:10]:
                        stock_data = stocks_data.get(stock_name)
                        if not stock_data:
                            continue

                        stock_price = stock_data.get("price")
                        change_pct = stock_data.get("change_pct")
                        net_flow = stock_data.get("net_flow", 0)

                        # Skip if missing critical data
                        if stock_price is None or change_pct is None:
                            continue

                        # BULLISH Alert: Price > +1% AND Net Flow > +100M
                        if change_pct > 1.0 and net_flow > 100:
                            send_stock_alert(stock_name, "BULLISH", stock_price, change_pct, net_flow)

                        # BEARISH Alert: Price < -1% AND Net Flow < -100M
                        elif change_pct < -1.0 and net_flow < -100:
                            send_stock_alert(stock_name, "BEARISH", stock_price, change_pct, net_flow)


                cache_data = {
                    "composite_score": composite_score,
                    "signal_band": signal_band,
                    "stance": stance,
                    "total_ce_cod": total_ce,
                    "total_pe_cod": total_pe,
                    "indices_ce_cod": total_indices_ce,
                    "indices_pe_cod": total_indices_pe,
                    "stocks_ce_cod": total_stocks_ce,
                    "stocks_pe_cod": total_stocks_pe,
                    "indices_data": indices_data,
                    # MEMORY FIX: Cache only top 20 stocks by net flow (not all 210!)
                    "stocks_data": dict(sorted(stocks_data.items(), key=lambda x: abs(x[1].get("net_flow", 0)), reverse=True)[:20]) if stocks_data else {},
                    "deltas": deltas,
                    "nifty_futures_data": nifty_futures_data,
                    "last_update": datetime.now().isoformat()
                }
                save_dashboard_cache(cache_data)

                # PHASE 1: Update chart data every 5 minutes (30 polls = 5 min at 10 sec intervals)
                engine.chart_update_counter += 1
                log_chart_debug(f"chart_update_counter = {engine.chart_update_counter}/30")
                
                if engine.chart_update_counter >= 10:  # 5 minutes
                    log_chart_debug(f"🎯 CHART UPDATE TRIGGERED! Counter reached {engine.chart_update_counter}")
                    engine.chart_update_counter = 0
                    
                    log_chart_debug(f"📊 Checking for NIFTY in indices_data...")
                    log_chart_debug(f"📊 indices_data keys: {list(indices_data.keys())}")
                    
                    if "NIFTY" in indices_data:
                        nifty_data = indices_data["NIFTY"]
                        log_chart_debug(f"📊 NIFTY data found: {nifty_data}")
                        
                        if nifty_data.get("price"):
                            chart_point = {
                                "timestamp": datetime.now(),
                                "spot_price": nifty_data["price"],
                                "ce_flow": nifty_data["ce_flow"],
                                "pe_flow": nifty_data["pe_flow"]
                            }
                            nifty_chart_data.append(chart_point)
                            log_chart_debug(f"✅ Chart point added: Nifty {nifty_data['price']:.2f}, CE {format_number(nifty_data['ce_flow'])}, PE {format_number(nifty_data['pe_flow'])}")
                            log_chart_debug(f"✅ nifty_chart_data now has {len(nifty_chart_data)} points")
                            
                            # 💾 Save chart data to cache (survives app restarts)
                            try:
                                chart_cache_file = Path('.cache/nifty_chart_data.pkl')
                                chart_cache_file.parent.mkdir(parents=True, exist_ok=True)
                                with open(chart_cache_file, 'wb') as f:
                                    pickle.dump(st.session_state.nifty_chart_data, f)
                                log_chart_debug(f"💾 Chart data saved to cache")
                            except Exception as e:
                                log_chart_debug(f"⚠️ Error saving chart cache: {e}")
                        else:
                            log_chart_debug(f"⚠️ NIFTY price missing - nifty_data={nifty_data}")
                    else:
                        log_chart_debug(f"❌ NIFTY not in indices_data! Available: {list(indices_data.keys())}")
                
                # 💾 Save volume state periodically (every 10 polls = ~100 seconds)
                if engine.chart_update_counter % 10 == 0:
                    try:
                        volume_cache_file = Path('.cache/volume_state.pkl')
                        volume_cache_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(volume_cache_file, 'wb') as f:
                            pickle.dump(st.session_state.volume_state, f)
                        log_chart_debug(f"💾 Volume state saved to cache")
                    except Exception as e:
                        log_chart_debug(f"⚠️ Error saving volume cache: {e}")
                
                engine.last_poll_time = datetime.now()
                
                # Alert detection logic remains here (will continue in next section)
                if deltas and len(flow_history) >= 5:
                    for idx_name in engine.indices_with_fo:
                        if idx_name in indices_data:
                            idx_data = indices_data[idx_name]
                            
                            hist_ce = [flow_history[i].get('indices_data', {}).get(idx_name, {}).get('ce_flow', 0) 
                                      for i in range(max(0, len(flow_history)-5), len(flow_history)) 
                                      if i < len(flow_history)]
                            hist_pe = [flow_history[i].get('indices_data', {}).get(idx_name, {}).get('pe_flow', 0) 
                                      for i in range(max(0, len(flow_history)-5), len(flow_history)) 
                                      if i < len(flow_history)]
                            
                            if len(hist_ce) >= 2:
                                ce_delta = idx_data['ce_flow'] - hist_ce[-1]
                                pe_delta = idx_data['pe_flow'] - hist_pe[-1]
                                
                                avg_ce = np.mean(hist_ce) if len(hist_ce) > 1 else hist_ce[0]
                                avg_pe = np.mean(hist_pe) if len(hist_pe) > 1 else hist_pe[0]
                                
                                if detect_spike(ce_delta, avg_ce / 5, threshold=2.0):
                                    if idx_data.get('price') and idx_data.get('change_pct') is not None:
                                        alert_msg = create_actionable_alert_index(
                                            idx_name, 
                                            "CE", 
                                            ce_delta, 
                                            idx_data['price'], 
                                            idx_data['change_pct']
                                        )
                                        if alert_msg:
                                            pass  # DISABLED: Stock alerts temporarily disabled
                                            # add_alert(alert_msg, "warning")

                                if detect_spike(pe_delta, avg_pe / 5, threshold=2.0):
                                    if idx_data.get('price') and idx_data.get('change_pct') is not None:
                                        alert_msg = create_actionable_alert_index(
                                            idx_name, 
                                            "PE", 
                                            pe_delta, 
                                            idx_data['price'], 
                                            idx_data['change_pct']
                                        )
                                        if alert_msg:
                                            pass  # DISABLED: Stock alerts temporarily disabled
                                            # add_alert(alert_msg, "warning")

                    stock_items = sorted(stocks_data.items(), key=lambda x: abs(x[1]["net_flow"]), reverse=True)[:20]
                    sector_mapping = load_sector_mapping()
                    
                    for stock_name, stock_data in stock_items:
                        hist_ce = [flow_history[i].get('stocks_data', {}).get(stock_name, {}).get('ce_flow', 0) 
                                  for i in range(max(0, len(flow_history)-5), len(flow_history)) 
                                  if i < len(flow_history)]
                        hist_pe = [flow_history[i].get('stocks_data', {}).get(stock_name, {}).get('pe_flow', 0) 
                                  for i in range(max(0, len(flow_history)-5), len(flow_history)) 
                                  if i < len(flow_history)]
                        
                        if len(hist_ce) >= 2:
                            ce_delta = stock_data['ce_flow'] - hist_ce[-1]
                            pe_delta = stock_data['pe_flow'] - hist_pe[-1]
                            
                            avg_ce = np.mean(hist_ce) if len(hist_ce) > 1 else hist_ce[0]
                            avg_pe = np.mean(hist_pe) if len(hist_pe) > 1 else hist_pe[0]
                            
                            sector = sector_mapping.get(stock_name.upper(), "N/A")
                            
                            if detect_spike(ce_delta, avg_ce / 5, threshold=2.5):
                                alert_msg = create_actionable_alert_stock(
                                    stock_name, 
                                    "CE", 
                                    ce_delta, 
                                    sector
                                )
                                if alert_msg:
                                    pass  # DISABLED: Stock alerts temporarily disabled
                                    # add_alert(alert_msg, "warning")

                            if detect_spike(pe_delta, avg_pe / 5, threshold=2.5):
                                alert_msg = create_actionable_alert_stock(
                                    stock_name, 
                                    "PE", 
                                    pe_delta,
                                    sector
                                )
                                if alert_msg:
                                    pass  # DISABLED: Stock alerts temporarily disabled
                                    # add_alert(alert_msg, "warning")

                # ============================================
                # HYBRID PATTERN MATCHING (REQUIREMENT 3)
                # Pattern Detection + OI Filtering
                # ============================================
                if PATTERNS_AVAILABLE and engine.pattern_enabled and deltas and len(flow_history) >= 6:
                    try:
                        patterns_found = run_pattern_detection(
                            flow_history,
                            indices_data,
                            deltas,
                            engine.indices_with_fo,
                            engine.last_pattern_alert,
                            add_alert,
                            kite=engine.kite,  # For OI data
                            ins_df=engine.ins_df  # For OI data
                        )
                        
                        if patterns_found > 0:
                            print(f"🎯 {patterns_found} high-confidence pattern(s) matched (Hybrid)")
                    except Exception as e:
                        print(f"⚠️ Pattern matching error: {e}")
                

                poll_msg = f"âœ“ Poll #{len(flow_history)} | Indices CE: {int(total_indices_ce):,} PE: {int(total_indices_pe):,}"
                
                if deltas and len(flow_history) >= 2:
                    indices_ce_1min = deltas.get('indices_ce_1min', 0)
                    indices_pe_1min = deltas.get('indices_pe_1min', 0)
                    
                    if abs(indices_ce_1min) > 0 or abs(indices_pe_1min) > 0:
                        poll_msg += f" | Î”1m: CE{indices_ce_1min:+,.0f} PE{indices_pe_1min:+,.0f} ðŸ”¥"
                    else:
                        poll_msg += f" | Î”1m: CEÂ±0 PEÂ±0"
                else:
                    poll_msg += f" | Î”1m: Collecting baseline..."
                
                print(poll_msg)
            
            time.sleep(10)
            
            # MEMORY FIX: Periodic garbage collection
            import gc
            gc.collect()
        except Exception as e:
            print(f"Polling error: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)
    print("\nPolling stopped")

def start_polling():
    global _POLLING_STARTED
    
    # Check global flag first
    if _POLLING_STARTED:
        print("⚠️ BLOCKED: Polling already started (global flag)")
        return False
    
    # Check lock file
    if _POLLING_LOCK_FILE.exists():
        try:
            with open(_POLLING_LOCK_FILE, 'r') as f:
                lock_time_str = f.read().strip()
            if lock_time_str:
                lock_time = datetime.fromisoformat(lock_time_str)
                age = (datetime.now() - lock_time).total_seconds()
                if age < 60:  # Lock less than 1 minute old
                    print(f"⚠️ BLOCKED: Lock file exists ({age:.0f}s old)")
                    return False
        except:
            pass
    
    # Check thread status
    if engine.polling_thread and engine.polling_thread.is_alive():
        print("⚠️ BLOCKED: Thread already running")
        _POLLING_STARTED = True
        return True
    # Create lock file BEFORE starting thread
    try:
        _POLLING_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_POLLING_LOCK_FILE, 'w') as f:
            f.write(datetime.now().isoformat())
        print("🔒 Lock file created")
    except Exception as e:
        print(f"❌ Could not create lock: {e}")
        return False
    
    # Set global flag
    _POLLING_STARTED = True
    
    # Start thread
    engine.stop_flag = False
    engine.polling_thread = threading.Thread(target=polling_loop, daemon=True)
    engine.polling_thread.start()
    engine.polling_active = True
    print("✅ Polling thread started")
    
    startup_msg = (
        "<b>🚀 LIVE MOMENTUM SYSTEM STARTED</b>\n\n"
        f"📅 Date: {datetime.now().strftime('%d %b %Y')}\n"
        f"⏰ Time: {datetime.now().strftime('%I:%M %p')}\n"
        f"📊 Tracking: {len(engine.indices_with_fo)} Indices + {len(engine.stocks_with_fo)} Stocks\n"
        f"🔔 Alerts: <b>ACTIONABLE with Strike Prices</b>\n\n"
        "<i>You will receive real-time entry signals with exact strikes, entry, target & SL...</i>"
    )
    send_telegram_alert(startup_msg)
    
    return True

def stop_polling():
    engine.stop_flag = True
    engine.polling_active = False
    print("Stopping polling...")
    
    stop_msg = (
        "<b>🛑 LIVE MOMENTUM SYSTEM STOPPED</b>\n\n"
        f"⏰ Time: {datetime.now().strftime('%I:%M %p')}\n"
        "<i>Alerts paused until restart</i>"
    )
    send_telegram_alert(stop_msg)

# =========================
# STREAMLIT UI
# =========================
st.set_page_config(page_title="Live Momentum Trading System", layout="wide", initial_sidebar_state="expanded")

if AUTOREFRESH_AVAILABLE and st.session_state.get("auto_refresh_toggle", True) and st.session_state.get("polling_running", False):
    st.session_state.refresh_count += 1
    count = st_autorefresh(interval=10 * 1000, key="auto_refresh_counter")

st.markdown("""
<style>
.main-header {font-size: 2.5rem; font-weight: bold; color: #1f77b4;}
.alert-box {padding: 0.5rem; border-radius: 0.3rem; margin-bottom: 0.3rem; font-size: 0.9rem;}
.alert-warning {background-color: #fff3cd; border-left: 4px solid #ffc107;}
.alert-success {background-color: #d4edda; border-left: 4px solid #28a745;}
.momentum-gauge {text-align: center; padding: 0.5rem; border-radius: 0.5rem; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🎛️ System Status")
    st.markdown("---")
    market_status, status_emoji, status_type = get_market_status()
    st.markdown(f"**{status_emoji} {market_status}**")
    st.caption(datetime.now().strftime('%I:%M %p, %d %b %Y'))
    st.markdown("---")
    st.markdown("### 🔐 Authentication")
    kite, token_saved_at = get_kite_session()
    if kite and token_saved_at:
        st.success("✅ Authenticated")
        time_since = datetime.now() - token_saved_at
        hours_left = max(0, 24 - time_since.total_seconds() / 3600)
        st.metric("Token Valid", f"{int(hours_left)}h {int((hours_left % 1) * 60)}m")
        if st.button("🚪 Logout", use_container_width=True, key="logout_btn"):
            TOKENS_FILE.unlink()
            st.rerun()
    else:
        st.warning("⚠️ Not Authenticated")
    st.markdown("---")
    st.markdown("### ⚙️ Engine Status")
    is_running = st.session_state.get("polling_running", False)
    thread_alive = engine.polling_thread and engine.polling_thread.is_alive()
    if is_running and thread_alive:
        st.success("🟢 Polling Active")
        if engine.last_poll_time:
            ago = (datetime.now() - engine.last_poll_time).total_seconds()
            st.caption(f"Last poll: {int(ago)}s ago")
    elif is_running and not thread_alive:
        st.error("🔴 Thread Died")
    else:
        st.info("⏸️ Stopped")
    if engine.subscribe_tokens:
        st.metric("Instruments", len(engine.subscribe_tokens))
    st.markdown("---")
    st.markdown("### 📊 Flow History")
    st.metric("Data Points", len(flow_history))    
    st.markdown("---")
    st.markdown("### 🔍 Hybrid Pattern Matching")
    
    if PATTERNS_AVAILABLE:
        pattern_status = get_pattern_status()
        st.info(pattern_status)
        
        engine.pattern_enabled = st.toggle(
            "Enable Hybrid Patterns",
            value=engine.pattern_enabled,
            help="Pattern matching + OI liquidity filtering",
            key="pattern_toggle"
        )
        
        if engine.pattern_enabled:
            st.success("✅ Hybrid mode active")
            st.caption("• Pattern detection (8 types)")
            st.caption("• OI filtering")
            st.caption("• Liquidity scoring")
        else:
            st.warning("⏸️ Pattern matching paused")
    else:
        st.warning("⚠️ Pattern modules not loaded")


st.markdown('<p class="main-header">🔥 Live Momentum Trading System</p>', unsafe_allow_html=True)

if not API_KEY or not API_SECRET:
    st.error("❌ Missing credentials in .env file")
    st.stop()

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    st.warning("⚠️ Telegram alerts not configured")
else:
    st.success(f"✅ Telegram alerts enabled (Chat ID: {TELEGRAM_CHAT_ID[-4:]}...)")

if not kite:
    st.warning("⚠️ Please authenticate")
    login_url = f"https://kite.zerodha.com/connect/login?api_key={API_KEY}&v=3"
    st.markdown(f"[Click here to login]({login_url})")
    with st.form("auth_form"):
        request_token = st.text_input("Request Token:", type="password")
        if st.form_submit_button("🔐 Authenticate"):
            try:
                kite, _ = authenticate_kite(request_token.strip())
                engine.kite = kite
                st.success("✅ Authenticated!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"❌ {e}")
    st.stop()

engine.kite = kite

if st.session_state.get("polling_running", False):
    if not (engine.polling_thread and engine.polling_thread.is_alive()):
        if engine.subscribe_tokens:
            start_polling()

if engine.ins_df.empty:
    with st.spinner("Loading instruments..."):
        engine.ins_df = ensure_instruments(kite)

if not engine.indices_with_fo:
    engine.indices_with_fo = discover_indices_with_fo(engine.ins_df)
# Get NIFTY current month futures
if not engine.nifty_fut_token and not engine.ins_df.empty:
    nifty_fut_info = get_current_month_nifty_future(engine.ins_df)
    if nifty_fut_info:
        engine.nifty_fut_token = nifty_fut_info['token']
        engine.nifty_fut_symbol = nifty_fut_info['symbol']
        engine.nifty_fut_expiry = nifty_fut_info['expiry']
        print(f"✓ NIFTY Futures: {engine.nifty_fut_symbol} (Exp: {engine.nifty_fut_expiry})")


if not engine.stocks_with_fo:
    engine.stocks_with_fo = discover_stocks_with_fo(engine.ins_df)

sector_mapping = load_sector_mapping()
load_flow_history()

if DASHBOARD_CACHE_FILE.exists():
    try:
        with open(DASHBOARD_CACHE_FILE, "rb") as f:
            old_cache = pickle.load(f)
        cached_date = datetime.fromisoformat(old_cache.get("cached_at", "2000-01-01")).date()
        if cached_date < datetime.now().date():
            DASHBOARD_CACHE_FILE.unlink()
            flow_history.clear()
            if FLOW_HISTORY_FILE.exists():
                FLOW_HISTORY_FILE.unlink()
    except:
        pass

if alerts:
    st.subheader("🚨 Live Alerts")
    for alert in list(alerts)[:5]:
        alert_class = "alert-warning" if alert["type"] == "warning" else "alert-success"
        st.markdown(f"""
        <div class="alert-box {alert_class}">
            <strong>{alert['time']}</strong> - {alert['message']}
        </div>
        """, unsafe_allow_html=True)
    st.markdown("---")

# ============================================
# PHASE 1: NIFTY FLOW ANALYSIS CHARTS
# ============================================

# Automatic diagnostic logging when charts are empty
if len(nifty_chart_data) <= 1:
    log_chart_debug("="*60)
    log_chart_debug("CHARTS ARE EMPTY - RUNNING DIAGNOSTICS")
    log_chart_debug("="*60)
    log_chart_debug(f"nifty_chart_data length: {len(nifty_chart_data)} (needs > 1)")
    log_chart_debug(f"flow_history length: {len(flow_history)}")
    
    if engine:
        log_chart_debug(f"Engine.polling_active: {engine.polling_active}")
        log_chart_debug(f"Engine.chart_update_counter: {engine.chart_update_counter}/30")
        log_chart_debug(f"Engine.subscribe_tokens: {len(engine.subscribe_tokens) if engine.subscribe_tokens else 0}")
        log_chart_debug(f"Engine.last_poll_time: {engine.last_poll_time}")
    
    if flow_history:
        log_chart_debug(f"✅ flow_history HAS data ({len(flow_history)} entries)")
        latest = list(flow_history)[-1]
        log_chart_debug(f"Latest flow_history entry: {latest.get('timestamp', 'N/A')}")
        
        # Check if NIFTY data exists in flow_history
        nifty_entries = [e for e in flow_history if e.get('index_name') == 'NIFTY']
        log_chart_debug(f"NIFTY entries in flow_history: {len(nifty_entries)}")
        
        if nifty_entries:
            sample = nifty_entries[-1]
            log_chart_debug(f"Sample NIFTY entry: spot={sample.get('price', 'N/A')}, ce={sample.get('ce_flow', 0)}, pe={sample.get('pe_flow', 0)}")
        else:
            log_chart_debug("❌ NO NIFTY entries in flow_history!")
    else:
        log_chart_debug("❌ flow_history is EMPTY!")
    
    # Check data folders
    from pathlib import Path
    today = datetime.now().date()
    indices_dir = Path("data/historical/indices") / str(today)
    
    if indices_dir.exists():
        csv_files = list(indices_dir.glob("*.csv"))
        log_chart_debug(f"✅ Historical data folder exists with {len(csv_files)} CSV files")
        
        nifty_csv = indices_dir / "NIFTY.csv"
        if nifty_csv.exists():
            size = nifty_csv.stat().st_size
            log_chart_debug(f"NIFTY.csv size: {size:,} bytes")
            if size > 100:
                with open(nifty_csv, 'r') as f:
                    lines = f.readlines()
                log_chart_debug(f"NIFTY.csv has {len(lines)-1} data rows")
        else:
            log_chart_debug("❌ NIFTY.csv not found!")
    else:
        log_chart_debug(f"❌ Historical data folder missing: {indices_dir}")
    
    log_chart_debug("="*60)
    log_chart_debug("DIAGNOSIS COMPLETE - Check above for issues")
    log_chart_debug("="*60)

if len(nifty_chart_data) > 1:
    st.markdown("---")
    st.subheader("📊 NIFTY Flow Analysis Charts")
    
    # Prepare data
    chart_list = list(nifty_chart_data)
    timestamps = [point["timestamp"].strftime("%H:%M") for point in chart_list]
    spot_prices = [point["spot_price"] for point in chart_list]
    ce_flows = [point["ce_flow"] / 1000 for point in chart_list]  # Convert to K
    pe_flows = [point["pe_flow"] / 1000 for point in chart_list]  # Convert to K
    
    # Determine trend
    if len(spot_prices) >= 2:
        ce_trend = ce_flows[-1] - ce_flows[0]
        pe_trend = pe_flows[-1] - pe_flows[0]
        price_trend = spot_prices[-1] - spot_prices[0]
        
        if ce_trend > 0 and pe_trend < 0 and price_trend > 0:
            signal = "🟢 STRONG BULLISH CONFIRMATION"
            signal_color = "#28a745"
        elif ce_trend < 0 and pe_trend > 0 and price_trend < 0:
            signal = "🔴 STRONG BEARISH CONFIRMATION"
            signal_color = "#dc3545"
        elif ce_trend > 0 and pe_trend > 0:
            signal = "⚠️ MIXED SIGNALS - Caution"
            signal_color = "#ff8800"
        else:
            signal = "⚪ NEUTRAL"
            signal_color = "#808080"
    else:
        signal = "⏳ Collecting Data..."
        signal_color = "#808080"
    
    col1, col2 = st.columns(2)
    
    with col1:
        # CE Flow vs Spot Price Chart
        fig_ce = go.Figure()
        fig_ce.add_trace(go.Scatter(
            x=spot_prices,
            y=ce_flows,
            mode='lines+markers',
            name='CE Flow',
            line=dict(color='#28a745', width=2),
            marker=dict(size=8),
            hovertemplate='<b>Price:</b> %{x:.2f}<br><b>CE Flow:</b> %{y:.1f}K<br><extra></extra>'
        ))
        
        fig_ce.update_layout(
            title="NIFTY CE FLOW vs SPOT PRICE",
            xaxis_title="Nifty Spot Price (₹)",
            yaxis_title="CE Flow (K)",
            height=400,
            hovermode='closest'
        )
        
        st.plotly_chart(fig_ce, use_container_width=True)
    
    with col2:
        # PE Flow vs Spot Price Chart
        fig_pe = go.Figure()
        fig_pe.add_trace(go.Scatter(
            x=spot_prices,
            y=pe_flows,
            mode='lines+markers',
            name='PE Flow',
            line=dict(color='#dc3545', width=2),
            marker=dict(size=8),
            hovertemplate='<b>Price:</b> %{x:.2f}<br><b>PE Flow:</b> %{y:.1f}K<br><extra></extra>'
        ))
        
        fig_pe.update_layout(
            title="NIFTY PE FLOW vs SPOT PRICE",
            xaxis_title="Nifty Spot Price (₹)",
            yaxis_title="PE Flow (K)",
            height=400,
            hovermode='closest'
        )
        
        st.plotly_chart(fig_pe, use_container_width=True)
    
    st.markdown(f"<h3 style='text-align: center; color: {signal_color};'>{signal}</h3>", unsafe_allow_html=True)
    st.caption(f"📊 Chart updates every 5 minutes | Last {len(nifty_chart_data)} data points ({len(nifty_chart_data) * 5} minutes)")

else:
    # Show blank charts with axes before data arrives
    st.info("📊 Charts ready - waiting for data (updates every 5 minutes after polling starts)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Blank CE Flow chart
        fig_ce = go.Figure()
        fig_ce.add_trace(go.Scatter(
            x=[],
            y=[],
            mode='lines+markers',
            name='CE Flow',
            line=dict(color='#28a745', width=2),
            marker=dict(size=8)
        ))
        
        fig_ce.update_layout(
            title="NIFTY CE FLOW vs SPOT PRICE",
            xaxis_title="Nifty Spot Price (₹)",
            yaxis_title="CE Flow (K)",
            height=400,
            xaxis=dict(range=[23000, 24000]),  # Default range
            yaxis=dict(range=[0, 1000])  # Default range
        )
        
        st.plotly_chart(fig_ce, use_container_width=True)
    
    with col2:
        # Blank PE Flow chart
        fig_pe = go.Figure()
        fig_pe.add_trace(go.Scatter(
            x=[],
            y=[],
            mode='lines+markers',
            name='PE Flow',
            line=dict(color='#dc3545', width=2),
            marker=dict(size=8)
        ))
        
        fig_pe.update_layout(
            title="NIFTY PE FLOW vs SPOT PRICE",
            xaxis_title="Nifty Spot Price (₹)",
            yaxis_title="PE Flow (K)",
            height=400,
            xaxis=dict(range=[23000, 24000]),  # Default range
            yaxis=dict(range=[0, 1000])  # Default range
        )
        
        st.plotly_chart(fig_pe, use_container_width=True)
    
    st.markdown("<h3 style='text-align: center; color: #808080;'>⏳ Waiting for data...</h3>", unsafe_allow_html=True)
    st.caption("📊 Charts will populate after 5 minutes of polling | Start polling to begin data collection")

st.markdown("---")

# =========================
# NIFTY OPTIONS VOLUME ANALYSIS CHARTS (REQUIREMENT 4)
# =========================

st.subheader("🔥 NIFTY Options Volume Analysis")

# Automatic diagnostic logging for volume charts when empty
if len(volume_state.ce_pe_history) == 0 or len(volume_state.spike_queue) == 0:
    log_chart_debug("="*60)
    log_chart_debug("VOLUME CHARTS ARE EMPTY - RUNNING DIAGNOSTICS")
    log_chart_debug("="*60)
    log_chart_debug(f"volume_state.spike_queue length: {len(volume_state.spike_queue)}")
    log_chart_debug(f"volume_state.ce_pe_history length: {len(volume_state.ce_pe_history)}")
    log_chart_debug(f"volume_state.timeline_data length: {len(volume_state.timeline_data)}")
    log_chart_debug(f"volume_state.intensity_history length: {len(volume_state.intensity_history)}")
    log_chart_debug(f"volume_state.volume_baseline: {volume_state.volume_baseline}")
    log_chart_debug(f"volume_state.last_atm_strike: {volume_state.last_atm_strike}")
    
    if len(volume_state.ce_pe_history) == 0:
        log_chart_debug("❌ ce_pe_history is EMPTY - update_volume_data may not be called!")
        log_chart_debug("Possible reasons:")
        log_chart_debug("  1. NIFTY not in indices_data")
        log_chart_debug("  2. update_volume_data() not being called in polling loop")
        log_chart_debug("  3. Error in update_volume_data() function")
        log_chart_debug("  4. token_meta missing NIFTY option tokens")
    
    # Check volume data folders
    from pathlib import Path
    today = datetime.now().date()
    volume_spike_dir = Path("data/historical/volume_spikes") / str(today)
    volume_intensity_dir = Path("data/historical/volume_intensity") / str(today)
    
    if volume_intensity_dir.exists():
        files = list(volume_intensity_dir.glob("*.csv"))
        log_chart_debug(f"✅ Volume intensity folder exists with {len(files)} files")
        if files:
            for f in files:
                size = f.stat().st_size
                log_chart_debug(f"  {f.name}: {size:,} bytes")
    else:
        log_chart_debug(f"❌ Volume intensity folder missing: {volume_intensity_dir}")
        log_chart_debug("This means update_volume_data() is NOT saving data!")
    
    log_chart_debug("="*60)
    log_chart_debug("VOLUME DIAGNOSIS COMPLETE")
    log_chart_debug("="*60)

# Chart 1: Volume Spike Heatmap
heatmap_df = create_volume_spike_heatmap()

if heatmap_df is not None and not heatmap_df.empty:
    st.markdown("### 🔥 Volume Spike Monitor (Last 10 Spikes)")
    st.dataframe(
        heatmap_df,
        use_container_width=True,
        hide_index=True
    )
    st.caption("🔥 >3x = Strong Signal | 🟡 2-3x = Moderate | 🟢 <2x = Normal")
else:
    # Show blank heatmap table
    st.markdown("### 🔥 Volume Spike Monitor (Last 10 Spikes)")
    blank_df = pd.DataFrame({
        'Time': ['—'] * 5,
        'Strike': ['—'] * 5,
        'Type': ['—'] * 5,
        'Volume': ['—'] * 5,
        'Spike': ['—'] * 5,
        'Alert': ['⏳'] * 5
    })
    st.dataframe(blank_df, use_container_width=True, hide_index=True)
    st.caption("⏳ Waiting for data - spikes will appear after 5 minutes of polling")

# Volume Spike Session Summary (Option B)
if volume_state.spike_queue and len(volume_state.spike_queue) > 0:
    st.markdown("")
    st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    st.markdown("### 📊 SESSION SUMMARY (Since 9:15 AM)")
    st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # Calculate statistics
    all_spikes = list(volume_state.spike_queue)
    ce_spikes = [s for s in all_spikes if s.option_type == "CE"]
    pe_spikes = [s for s in all_spikes if s.option_type == "PE"]
    
    # CE Stats
    ce_count = len(ce_spikes)
    ce_total_volume = sum(s.volume for s in ce_spikes)
    ce_avg_volume = ce_total_volume / ce_count if ce_count > 0 else 0
    ce_largest = max(ce_spikes, key=lambda s: s.volume) if ce_spikes else None
    
    # PE Stats
    pe_count = len(pe_spikes)
    pe_total_volume = sum(s.volume for s in pe_spikes)
    pe_avg_volume = pe_total_volume / pe_count if pe_count > 0 else 0
    pe_largest = max(pe_spikes, key=lambda s: s.volume) if pe_spikes else None
    
    # Display in two columns
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🟢 CE Spikes")
        st.markdown("─────────────────────────────────────")
        st.metric("Total Spikes", f"{ce_count} spikes")
        st.metric("Total Volume", format_number(ce_total_volume))
        st.metric("Avg Volume", format_number(ce_avg_volume) + "/spike")
        if ce_largest:
            largest_time = ce_largest.timestamp.strftime("%I:%M %p")
            st.metric("Largest Spike", f"{format_number(ce_largest.volume)} ({largest_time})")
        else:
            st.metric("Largest Spike", "—")
    
    with col2:
        st.markdown("#### 🔴 PE Spikes")
        st.markdown("─────────────────────────────────────")
        st.metric("Total Spikes", f"{pe_count} spikes")
        st.metric("Total Volume", format_number(pe_total_volume))
        st.metric("Avg Volume", format_number(pe_avg_volume) + "/spike")
        if pe_largest:
            largest_time = pe_largest.timestamp.strftime("%I:%M %p")
            st.metric("Largest Spike", f"{format_number(pe_largest.volume)} ({largest_time})")
        else:
            st.metric("Largest Spike", "—")
    
    # Race Summary
    st.markdown("")
    st.markdown("#### Race Summary")
    
    total_spikes = ce_count + pe_count
    if total_spikes > 0:
        ce_pct = (ce_count / total_spikes) * 100
        pe_pct = 100 - ce_pct
        
        # Create visual race bar
        ce_blocks = int(round(ce_pct / 10))
        pe_blocks = 10 - ce_blocks
        race_bar = f"[🟢{'▓' * ce_blocks}🔴{'▓' * pe_blocks}]"
        
        # Determine signal
        if ce_pct >= 60:
            signal = "🚀 BULLS AGGRESSIVE - More CE spikes today"
            signal_color = "success"
        elif pe_pct >= 60:
            signal = "📉 BEARS AGGRESSIVE - More PE spikes today"
            signal_color = "error"
        else:
            signal = "⚖️ BALANCED - CE and PE spikes roughly equal"
            signal_color = "info"
        
        st.markdown(f"**CE Dominance: {ce_pct:.0f}%**  {race_bar}  {ce_pct:.0f}% CE | {pe_pct:.0f}% PE")
        
        if signal_color == "success":
            st.success(f"**Signal:** {signal}")
        elif signal_color == "error":
            st.error(f"**Signal:** {signal}")
        else:
            st.info(f"**Signal:** {signal}")
    
    st.markdown("")


st.markdown("")

# Chart 2 & 4: Race Chart + Wave Chart (Side by side)
col1, col2 = st.columns([1, 2])

with col1:
    # CE vs PE Race Chart
    race_data = create_ce_pe_race_chart()
    
    if race_data:
        st.markdown("### 📈 CE vs PE Race")
        st.markdown("**10-Minute Window**")
        
        # CE Bar
        st.markdown(f"**CE Volume:** {format_number(race_data['ce_total'])} ({race_data['ce_pct']:.1f}%)")
        st.progress(race_data['ce_pct'] / 100)
        
        # PE Bar
        st.markdown(f"**PE Volume:** {format_number(race_data['pe_total'])} ({race_data['pe_pct']:.1f}%)")
        st.progress(race_data['pe_pct'] / 100)
        
        # Net Bias
        if race_data['bias'] == 'BULLISH':
            st.success(f"**Net {race_data['bias']}:** +{format_number(race_data['net_flow'])}")
        elif race_data['bias'] == 'BEARISH':
            st.error(f"**Net {race_data['bias']}:** {format_number(race_data['net_flow'])}")
        else:
            st.info(f"**Net {race_data['bias']}:** {format_number(race_data['net_flow'])}")
        
        # 10-Min Change
        st.markdown("**10-Min Change:**")
        st.caption(f"CE: {format_number(race_data['ce_change'])} {race_data['ce_trend']}")
        st.caption(f"PE: {format_number(race_data['pe_change'])} {race_data['pe_trend']}")
    else:
        # Show blank race chart
        st.markdown("### 📈 CE vs PE Race")
        st.markdown("**10-Minute Window**")
        
        st.markdown(f"**CE Volume:** — (—%)")
        st.progress(0.5)
        
        st.markdown(f"**PE Volume:** — (—%)")
        st.progress(0.5)
        
        st.info(f"**Net NEUTRAL:** —")
        
        st.markdown("**10-Min Change:**")
        st.caption(f"CE: — ⏳")
        st.caption(f"PE: — ⏳")
        
        st.caption("⏳ Collecting data... (need 10 minutes)")

with col2:
    # Volume Intensity Wave
    wave_result = create_volume_intensity_wave()
    
    if wave_result and wave_result[0] is not None:
        fig_wave, wave_info = wave_result
        st.plotly_chart(fig_wave, use_container_width=True)
        
        # Wave info
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric(
                "Current Intensity",
                f"{wave_info['current_intensity']:.1f}x",
                delta=None
            )
        with col_b:
            st.markdown(f"**Phase:** {wave_info['phase_emoji']} {wave_info['phase']}")
        with col_c:
            st.markdown(f"**Trend:** {wave_info['trend_emoji']} {wave_info['trend']}")
        
        st.caption("🔵 Low (1-2x) | 🟡 Medium (2-3x) | 🟠 High (3-4x) | 🔴 Extreme (4x+)")
    else:
        # Show blank intensity wave chart
        fig_blank_wave = go.Figure()
        
        # Add blank line
        fig_blank_wave.add_trace(go.Scatter(
            x=[0, 1, 2, 3, 4, 5],
            y=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            mode='lines',
            fill='tozeroy',
            fillcolor='rgba(100, 100, 100, 0.1)',
            line=dict(color='gray', width=2),
            name='Intensity'
        ))
        
        # Add threshold lines
        fig_blank_wave.add_hline(y=1.0, line_dash="dash", line_color="gray", opacity=0.3)
        fig_blank_wave.add_hline(y=2.0, line_dash="dash", line_color="yellow", opacity=0.3)
        fig_blank_wave.add_hline(y=3.0, line_dash="dash", line_color="orange", opacity=0.3)
        fig_blank_wave.add_hline(y=4.0, line_dash="dash", line_color="red", opacity=0.3)
        
        fig_blank_wave.update_layout(
            title="📊 Volume Intensity Wave (30-Minute Window)",
            xaxis_title="Time",
            yaxis_title="Intensity Ratio (Volume / Baseline)",
            height=400,
            showlegend=False,
            xaxis=dict(showticklabels=False)
        )
        
        st.plotly_chart(fig_blank_wave, use_container_width=True)
        
        # Blank wave info
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Current Intensity", "—x", delta=None)
        with col_b:
            st.markdown(f"**Phase:** ⏳ WAITING")
        with col_c:
            st.markdown(f"**Trend:** ⏳ BUILDING")
        
        st.caption("⏳ Collecting data... | 🔵 Low (1-2x) | 🟡 Medium (2-3x) | 🟠 High (3-4x) | 🔴 Extreme (4x+)")

st.markdown("")

# Chart 3: Volume Spike Timeline
timeline_result = create_volume_spike_timeline()

if timeline_result and timeline_result[0] is not None:
    fig_timeline, recent_spikes = timeline_result
    st.plotly_chart(fig_timeline, use_container_width=True)
    
    # Show recent spikes summary
    if recent_spikes:
        st.markdown("**🔥 Latest Spikes:**")
        for spike in recent_spikes:
            strike_label = get_strike_label(spike.strike, volume_state.last_atm_strike)
            _, emoji, _ = get_alert_level(spike.spike_ratio)
            
            st.caption(
                f"{emoji} {spike.strike} {spike.option_type} ({strike_label}): "
                f"{format_number(spike.volume)} ({spike.spike_ratio:.1f}x) "
                f"at {spike.timestamp.strftime('%H:%M:%S')}"
            )
else:
    # Show blank timeline chart
    fig_blank_timeline = go.Figure()
    
    # Add sample blank points
    fig_blank_timeline.add_trace(go.Scatter(
        x=[0, 1, 2, 3, 4, 5],
        y=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        mode='markers',
        marker=dict(size=10, color='gray', opacity=0.3),
        name='Spikes'
    ))
    
    # Add threshold lines
    fig_blank_timeline.add_hline(y=2.0, line_dash="dash", line_color="yellow", opacity=0.3, 
                                  annotation_text="2.0x (Moderate)")
    fig_blank_timeline.add_hline(y=3.0, line_dash="dash", line_color="red", opacity=0.3,
                                  annotation_text="3.0x (Strong)")
    fig_blank_timeline.add_hline(y=5.0, line_dash="dash", line_color="darkred", opacity=0.3,
                                  annotation_text="5.0x (Alert)")
    
    fig_blank_timeline.update_layout(
        title="📈 Volume Spike Timeline (Last 30 Minutes) - Smart Hybrid Tracking",
        xaxis_title="Time",
        yaxis_title="Spike Ratio (Current / 5-Min Avg)",
        height=400,
        showlegend=False,
        xaxis=dict(showticklabels=False),
        yaxis=dict(range=[0, 6])
    )
    
    st.plotly_chart(fig_blank_timeline, use_container_width=True)
    
    st.markdown("**🔥 Latest Spikes:**")
    st.caption("⏳ Waiting for spike events... (spikes >2.0x will appear here)")
    st.caption("📊 Tracking: ATM strike + any spike >3.0x across all strikes")
    st.caption("⚡ Far OTM/ITM (distance >150) will be marked with lightning bolt")

st.markdown("---")

st.subheader("⚙️ Control Panel")
col_info, col_toggle = st.columns([3, 1])
with col_info:
    if not AUTOREFRESH_AVAILABLE:
        st.warning("⚠️ Auto-refresh unavailable")
    elif st.session_state.get("auto_refresh_toggle", True) and st.session_state.get("polling_running", False):
        st.info(f"📡 Live Tracking - 🔄 Auto-refreshing (#{st.session_state.refresh_count})")
    else:
        st.info("📡 REST API Polling Mode")
with col_toggle:
    auto_refresh_enabled = st.toggle("Auto-refresh", value=st.session_state.get("auto_refresh_toggle", True), key="auto_refresh_toggle", disabled=not AUTOREFRESH_AVAILABLE)

# AUTO-START POLLING (First time only)
if not st.session_state.get("polling_running", False):
    if not st.session_state.get("auto_start_attempted", False):
        st.session_state.auto_start_attempted = True
        
        # Build subscriptions if needed
        if not engine.subscribe_tokens:
            with st.spinner("🔄 Auto-starting: Building subscriptions..."):
                engine.subscribe_tokens = build_subscriptions(kite, engine.ins_df)
        
        # Start polling automatically
        if engine.subscribe_tokens:
            if start_polling():
                st.session_state.polling_running = True
                st.success(f"✅ Auto-started polling! Tracking {len(engine.subscribe_tokens)} instruments")
                st.rerun()
        else:
            st.warning("⚠️ Auto-start failed - click Start Polling button")

col1, col2, col3 = st.columns(3)
with col1:
    # Button only shows if polling NOT running
    if not st.session_state.get("polling_running", False):
        if st.button("▶️ Start Polling", use_container_width=True, type="primary", key="start_btn"):
            if not engine.subscribe_tokens:
                with st.spinner("Building subscriptions..."):
                    engine.subscribe_tokens = build_subscriptions(kite, engine.ins_df)
            if engine.subscribe_tokens:
                if start_polling():
                    st.session_state.polling_running = True
                    st.success(f"✅ Started! {len(engine.subscribe_tokens)} instruments")
                    st.rerun()
            else:
                st.error("❌ No subscriptions")
    else:
        st.success(f"✅ Polling Active - {len(engine.subscribe_tokens)} instruments")

with col2:
    if st.button("⏸️ Stop Polling", use_container_width=True, key="stop_btn"):
        stop_polling()
        st.session_state.polling_running = False
        st.warning("🛑 Stopped")

with col3:
    if st.button("📱 Test Telegram", use_container_width=True, key="test_telegram_btn"):
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            st.error("❌ Telegram not configured")
        else:
            with st.spinner("Sending test message..."):
                test_msg = (
                    "<b>🧪 TELEGRAM TEST MESSAGE</b>\n\n"
                    f"⏰ Time: {datetime.now().strftime('%I:%M:%S %p')}\n"
                    f"📅 Date: {datetime.now().strftime('%d %b %Y')}\n\n"
                    "<b>Sample Actionable Alert:</b>\n"
                    "🔥 <b>NIFTY ENTRY SIGNAL</b> 🔥\n\n"
                    "<b>Strike:</b> 23500 CE (ATM)\n"
                    "<b>Current LTP:</b> ₹145.50\n"
                    "<b>Entry:</b> ₹142.59-149.41\n"
                    "<b>Target:</b> ₹167.33 (+15.0%)\n"
                    "<b>Stop Loss:</b> ₹130.95 (-10.0%)\n\n"
                    "<i>If you received this, Telegram alerts are working! 🎉</i>"
                )
                if send_telegram_alert(test_msg):
                    st.success("✅ Test message sent! Check your Telegram")
                else:
                    st.error("❌ Failed to send")

col3a, col3b = st.columns(2)
with col3a:
    st.metric("📊 Indices", len(engine.indices_with_fo))
with col3b:
    st.metric("📈 Stocks", len(engine.stocks_with_fo))

if engine.indices_with_fo:
    st.caption(f"**Indices:** {', '.join(engine.indices_with_fo)}")
if engine.stocks_with_fo:
    stock_list = ', '.join(engine.stocks_with_fo[:10])
    if len(engine.stocks_with_fo) > 10:
        stock_list += f" + {len(engine.stocks_with_fo) - 10} more"
    st.caption(f"**Stocks:** {stock_list}")

st.markdown("---")

st.subheader("📈 Live Composite Score")
cached_data = load_dashboard_cache()
latest_score = None
latest_band = None

if cached_data:
    latest_score = cached_data.get("composite_score", 50.0)
    latest_band = cached_data.get("signal_band", "Sideways")
    last_update = cached_data.get("last_update")
    if last_update:
        update_time = datetime.fromisoformat(last_update)
        if update_time.tzinfo:
            update_time = update_time.replace(tzinfo=None)
        time_ago = (datetime.now() - update_time).total_seconds()
        if time_ago < 60:
            st.success(f"🟢 Live • Updated {int(time_ago)}s ago")
        else:
            st.info(f"📦 Cached {int(time_ago/60)}m ago")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Composite Score", f"{latest_score:.1f}" if latest_score else "—")
with col2:
    st.metric("Signal Band", latest_band if latest_band else "—")
with col3:
    stance = cached_data.get("stance", "Wait") if cached_data else "—"
    st.metric("Strategy Stance", stance)

if latest_score:
    st.progress((latest_score + 100) / 200)

st.markdown("---")

st.subheader("🔥 Live Momentum Tracker")

if cached_data and cached_data.get("deltas"):
    deltas = cached_data["deltas"]
    
    st.markdown("### 📊 Indices Momentum")
    
    indices_ce = cached_data.get("indices_ce_cod", 0.0)
    indices_pe = cached_data.get("indices_pe_cod", 0.0)
    indices_net = indices_ce - indices_pe
    
    indices_ce_1min = deltas.get("indices_ce_1min", 0)
    indices_pe_1min = deltas.get("indices_pe_1min", 0)
    indices_net_1min = indices_ce_1min - indices_pe_1min
    
    indices_ce_5min = deltas.get("indices_ce_5min", 0)
    indices_pe_5min = deltas.get("indices_pe_5min", 0)
    indices_net_5min = indices_ce_5min - indices_pe_5min
    
    momentum_signal, momentum_color = get_momentum_signal(indices_net_1min, indices_net_5min)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("**Cumulative**")
        st.metric("CE Flow", format_number(indices_ce))
        st.metric("PE Flow", format_number(indices_pe))
        net_emoji = "🟢" if indices_net > 0 else ("🔴" if indices_net < 0 else "⚪")
        st.metric(f"{net_emoji} Net", format_number(indices_net))
    
    with col2:
        st.markdown("**Δ 1 Minute**")
        st.metric("CE Δ", format_number(indices_ce_1min))
        st.metric("PE Δ", format_number(indices_pe_1min))
        net_emoji = "🟢" if indices_net_1min > 0 else ("🔴" if indices_net_1min < 0 else "⚪")
        st.metric(f"{net_emoji} Net Δ", format_number(indices_net_1min))
    
    with col3:
        st.markdown("**Δ 5 Minutes**")
        if indices_ce_5min is not None:
            st.metric("CE Δ", format_number(indices_ce_5min))
            st.metric("PE Δ", format_number(indices_pe_5min))
            net_emoji = "🟢" if indices_net_5min > 0 else ("🔴" if indices_net_5min < 0 else "⚪")
            st.metric(f"{net_emoji} Net Δ", format_number(indices_net_5min))
        else:
            st.info("Collecting...")
    
    with col4:
        st.markdown("**Momentum**")
        st.markdown(f"""
        <div class="momentum-gauge" style="background-color: {momentum_color}; color: white;">
            {momentum_signal}
        </div>
        """, unsafe_allow_html=True)
        
        if "ACCELERATING" in momentum_signal or "SURGING" in momentum_signal:
            if indices_net_1min > 0:
                st.success("🎯 **BUY SIGNAL**")
            else:
                st.error("🎯 **SELL SIGNAL**")
    
    st.markdown("---")
    
    # ============================================
    # PHASE 1: INDIVIDUAL INDEX MOMENTUM TRACKERS
    # ============================================
    
    indices_data = cached_data.get("indices_data", {})
    
    # NIFTY Momentum Section
    if "NIFTY" in indices_data:
        st.markdown("### 📈 NIFTY Momentum")
        
        nifty = indices_data["NIFTY"]
        ce_flow = nifty.get('ce_flow', 0)
        pe_flow = nifty.get('pe_flow', 0)
        net_flow = ce_flow - pe_flow
        
        ce_1min = deltas.get('NIFTY_ce_1min', 0)
        pe_1min = deltas.get('NIFTY_pe_1min', 0)
        net_1min = ce_1min - pe_1min
        
        ce_5min = deltas.get('NIFTY_ce_5min')
        pe_5min = deltas.get('NIFTY_pe_5min')
        net_5min = (ce_5min - pe_5min) if ce_5min is not None and pe_5min is not None else None
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown("**Cumulative**")
            st.metric("CE Flow", format_number(ce_flow))
            st.metric("PE Flow", format_number(pe_flow))
            net_emoji = "🟢" if net_flow > 0 else ("🔴" if net_flow < 0 else "⚪")
            st.metric(f"{net_emoji} Net", format_number(net_flow))
        
        with col2:
            st.markdown("**Δ 1 Minute**")
            st.metric("CE Δ", format_number(ce_1min))
            st.metric("PE Δ", format_number(pe_1min))
            net_emoji = "🟢" if net_1min > 0 else ("🔴" if net_1min < 0 else "⚪")
            st.metric(f"{net_emoji} Net Δ", format_number(net_1min))
        
        with col3:
            st.markdown("**Δ 5 Minutes**")
            if ce_5min is not None:
                st.metric("CE Δ", format_number(ce_5min))
                st.metric("PE Δ", format_number(pe_5min))
                net_emoji = "🟢" if net_5min > 0 else ("🔴" if net_5min < 0 else "⚪")
                st.metric(f"{net_emoji} Net Δ", format_number(net_5min))
            else:
                st.info("Collecting...")
        
        with col4:
            st.markdown("**Momentum**")
            momentum_signal, momentum_color = get_momentum_signal(net_1min, net_5min)
            st.markdown(f'<div class="momentum-gauge" style="background-color: {momentum_color}; color: white;">{momentum_signal}</div>', unsafe_allow_html=True)
            
            if "ACCELERATING" in momentum_signal or "SURGING" in momentum_signal:
                if net_1min > 0:
                    st.success("🎯 BUY")
                else:
                    st.error("🎯 SELL")
        
        st.markdown("---")
    
    # BANKNIFTY Momentum Section
    if "BANKNIFTY" in indices_data:
        st.markdown("### 📈 BANKNIFTY Momentum")
        
        banknifty = indices_data["BANKNIFTY"]
        ce_flow = banknifty.get('ce_flow', 0)
        pe_flow = banknifty.get('pe_flow', 0)
        net_flow = ce_flow - pe_flow
        
        ce_1min = deltas.get('BANKNIFTY_ce_1min', 0)
        pe_1min = deltas.get('BANKNIFTY_pe_1min', 0)
        net_1min = ce_1min - pe_1min
        
        ce_5min = deltas.get('BANKNIFTY_ce_5min')
        pe_5min = deltas.get('BANKNIFTY_pe_5min')
        net_5min = (ce_5min - pe_5min) if ce_5min is not None and pe_5min is not None else None
        
        # CE vs PE Race
        total_flow = ce_flow + pe_flow
        if total_flow > 0:
            ce_pct = (ce_flow / total_flow) * 100
            pe_pct = 100 - ce_pct
        else:
            ce_pct = 50
            pe_pct = 50
        
        # Create visual race bar (10 blocks)
        ce_blocks = int(round(ce_pct / 10))
        pe_blocks = 10 - ce_blocks
        race_bar = f"[🟢{'▓' * ce_blocks}🔴{'▓' * pe_blocks}] {ce_pct:.0f}%"
        
        # Dominance indicator
        if ce_pct >= 75:
            dominance = "🚀 CE DOMINATING"
        elif pe_pct >= 75:
            dominance = "📉 PE DOMINATING"
        else:
            dominance = "⚖️ Balanced"
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown("**Cumulative**")
            st.metric("CE Flow", format_number(ce_flow))
            st.metric("PE Flow", format_number(pe_flow))
            net_emoji = "🟢" if net_flow > 0 else ("🔴" if net_flow < 0 else "⚪")
            st.metric(f"{net_emoji} Net", format_number(net_flow))
        
            
            st.markdown("**CE vs PE Race**")
            st.markdown(race_bar)
            st.caption(dominance)
        with col2:
            st.markdown("**Δ 1 Minute**")
            st.metric("CE Δ", format_number(ce_1min))
            st.metric("PE Δ", format_number(pe_1min))
            net_emoji = "🟢" if net_1min > 0 else ("🔴" if net_1min < 0 else "⚪")
            st.metric(f"{net_emoji} Net Δ", format_number(net_1min))
        
        with col3:
            st.markdown("**Δ 5 Minutes**")
            if ce_5min is not None:
                st.metric("CE Δ", format_number(ce_5min))
                st.metric("PE Δ", format_number(pe_5min))
                net_emoji = "🟢" if net_5min > 0 else ("🔴" if net_5min < 0 else "⚪")
                st.metric(f"{net_emoji} Net Δ", format_number(net_5min))
            else:
                st.info("Collecting...")
        
        with col4:
            st.markdown("**Momentum**")
            momentum_signal, momentum_color = get_momentum_signal(net_1min, net_5min)
            st.markdown(f'<div class="momentum-gauge" style="background-color: {momentum_color}; color: white;">{momentum_signal}</div>', unsafe_allow_html=True)
            
            if "ACCELERATING" in momentum_signal or "SURGING" in momentum_signal:
                if net_1min > 0:
                    st.success("🎯 BUY")
                else:
                    st.error("🎯 SELL")
        
        st.markdown("---")
    
    # FINNIFTY Momentum Section
    if "FINNIFTY" in indices_data:
        st.markdown("### 📈 FINNIFTY Momentum")
        
        finnifty = indices_data["FINNIFTY"]
        ce_flow = finnifty.get('ce_flow', 0)
        pe_flow = finnifty.get('pe_flow', 0)
        net_flow = ce_flow - pe_flow
        
        ce_1min = deltas.get('FINNIFTY_ce_1min', 0)
        pe_1min = deltas.get('FINNIFTY_pe_1min', 0)
        net_1min = ce_1min - pe_1min
        
        ce_5min = deltas.get('FINNIFTY_ce_5min')
        pe_5min = deltas.get('FINNIFTY_pe_5min')
        net_5min = (ce_5min - pe_5min) if ce_5min is not None and pe_5min is not None else None
        
        # CE vs PE Race
        total_flow = ce_flow + pe_flow
        if total_flow > 0:
            ce_pct = (ce_flow / total_flow) * 100
            pe_pct = 100 - ce_pct
        else:
            ce_pct = 50
            pe_pct = 50
        
        # Create visual race bar (10 blocks)
        ce_blocks = int(round(ce_pct / 10))
        pe_blocks = 10 - ce_blocks
        race_bar = f"[🟢{'▓' * ce_blocks}🔴{'▓' * pe_blocks}] {ce_pct:.0f}%"
        
        # Dominance indicator
        if ce_pct >= 75:
            dominance = "🚀 CE DOMINATING"
        elif pe_pct >= 75:
            dominance = "📉 PE DOMINATING"
        else:
            dominance = "⚖️ Balanced"
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown("**Cumulative**")
            st.metric("CE Flow", format_number(ce_flow))
            st.metric("PE Flow", format_number(pe_flow))
            net_emoji = "🟢" if net_flow > 0 else ("🔴" if net_flow < 0 else "⚪")
            st.metric(f"{net_emoji} Net", format_number(net_flow))
        
            
            st.markdown("**CE vs PE Race**")
            st.markdown(race_bar)
            st.caption(dominance)
        with col2:
            st.markdown("**Δ 1 Minute**")
            st.metric("CE Δ", format_number(ce_1min))
            st.metric("PE Δ", format_number(pe_1min))
            net_emoji = "🟢" if net_1min > 0 else ("🔴" if net_1min < 0 else "⚪")
            st.metric(f"{net_emoji} Net Δ", format_number(net_1min))
        
        with col3:
            st.markdown("**Δ 5 Minutes**")
            if ce_5min is not None:
                st.metric("CE Δ", format_number(ce_5min))
                st.metric("PE Δ", format_number(pe_5min))
                net_emoji = "🟢" if net_5min > 0 else ("🔴" if net_5min < 0 else "⚪")
                st.metric(f"{net_emoji} Net Δ", format_number(net_5min))
            else:
                st.info("Collecting...")
        
        with col4:
            st.markdown("**Momentum**")
            momentum_signal, momentum_color = get_momentum_signal(net_1min, net_5min)
            st.markdown(f'<div class="momentum-gauge" style="background-color: {momentum_color}; color: white;">{momentum_signal}</div>', unsafe_allow_html=True)
            
            if "ACCELERATING" in momentum_signal or "SURGING" in momentum_signal:
                if net_1min > 0:
                    st.success("🎯 BUY")
                else:
                    st.error("🎯 SELL")
        
        st.markdown("---")
    
    # MIDCPNIFTY Momentum Section
    if "MIDCPNIFTY" in indices_data:
        st.markdown("### 📈 MIDCPNIFTY Momentum")
        
        midcpnifty = indices_data["MIDCPNIFTY"]
        ce_flow = midcpnifty.get('ce_flow', 0)
        pe_flow = midcpnifty.get('pe_flow', 0)
        net_flow = ce_flow - pe_flow
        
        ce_1min = deltas.get('MIDCPNIFTY_ce_1min', 0)
        pe_1min = deltas.get('MIDCPNIFTY_pe_1min', 0)
        net_1min = ce_1min - pe_1min
        
        ce_5min = deltas.get('MIDCPNIFTY_ce_5min')
        pe_5min = deltas.get('MIDCPNIFTY_pe_5min')
        net_5min = (ce_5min - pe_5min) if ce_5min is not None and pe_5min is not None else None
        
        # CE vs PE Race
        total_flow = ce_flow + pe_flow
        if total_flow > 0:
            ce_pct = (ce_flow / total_flow) * 100
            pe_pct = 100 - ce_pct
        else:
            ce_pct = 50
            pe_pct = 50
        
        # Create visual race bar (10 blocks)
        ce_blocks = int(round(ce_pct / 10))
        pe_blocks = 10 - ce_blocks
        race_bar = f"[🟢{'▓' * ce_blocks}🔴{'▓' * pe_blocks}] {ce_pct:.0f}%"
        
        # Dominance indicator
        if ce_pct >= 75:
            dominance = "🚀 CE DOMINATING"
        elif pe_pct >= 75:
            dominance = "📉 PE DOMINATING"
        else:
            dominance = "⚖️ Balanced"
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown("**Cumulative**")
            st.metric("CE Flow", format_number(ce_flow))
            st.metric("PE Flow", format_number(pe_flow))
            net_emoji = "🟢" if net_flow > 0 else ("🔴" if net_flow < 0 else "⚪")
            st.metric(f"{net_emoji} Net", format_number(net_flow))
        
            
            st.markdown("**CE vs PE Race**")
            st.markdown(race_bar)
            st.caption(dominance)
        with col2:
            st.markdown("**Δ 1 Minute**")
            st.metric("CE Δ", format_number(ce_1min))
            st.metric("PE Δ", format_number(pe_1min))
            net_emoji = "🟢" if net_1min > 0 else ("🔴" if net_1min < 0 else "⚪")
            st.metric(f"{net_emoji} Net Δ", format_number(net_1min))
        
        with col3:
            st.markdown("**Δ 5 Minutes**")
            if ce_5min is not None:
                st.metric("CE Δ", format_number(ce_5min))
                st.metric("PE Δ", format_number(pe_5min))
                net_emoji = "🟢" if net_5min > 0 else ("🔴" if net_5min < 0 else "⚪")
                st.metric(f"{net_emoji} Net Δ", format_number(net_5min))
            else:
                st.info("Collecting...")
        
        with col4:
            st.markdown("**Momentum**")
            momentum_signal, momentum_color = get_momentum_signal(net_1min, net_5min)
            st.markdown(f'<div class="momentum-gauge" style="background-color: {momentum_color}; color: white;">{momentum_signal}</div>', unsafe_allow_html=True)
            
            if "ACCELERATING" in momentum_signal or "SURGING" in momentum_signal:
                if net_1min > 0:
                    st.success("🎯 BUY")
                else:
                    st.error("🎯 SELL")
        
        st.markdown("---")
    
    # SENSEX Momentum Section
    if "SENSEX" in indices_data:
        st.markdown("### 📈 SENSEX Momentum")
        
        sensex = indices_data["SENSEX"]
        ce_flow = sensex.get('ce_flow', 0)
        pe_flow = sensex.get('pe_flow', 0)
        net_flow = ce_flow - pe_flow
        
        ce_1min = deltas.get('SENSEX_ce_1min', 0)
        pe_1min = deltas.get('SENSEX_pe_1min', 0)
        net_1min = ce_1min - pe_1min
        
        ce_5min = deltas.get('SENSEX_ce_5min')
        pe_5min = deltas.get('SENSEX_pe_5min')
        net_5min = (ce_5min - pe_5min) if ce_5min is not None and pe_5min is not None else None
        
        # CE vs PE Race
        total_flow = ce_flow + pe_flow
        if total_flow > 0:
            ce_pct = (ce_flow / total_flow) * 100
            pe_pct = 100 - ce_pct
        else:
            ce_pct = 50
            pe_pct = 50
        
        # Create visual race bar (10 blocks)
        ce_blocks = int(round(ce_pct / 10))
        pe_blocks = 10 - ce_blocks
        race_bar = f"[🟢{'▓' * ce_blocks}🔴{'▓' * pe_blocks}] {ce_pct:.0f}%"
        
        # Dominance indicator
        if ce_pct >= 75:
            dominance = "🚀 CE DOMINATING"
        elif pe_pct >= 75:
            dominance = "📉 PE DOMINATING"
        else:
            dominance = "⚖️ Balanced"
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown("**Cumulative**")
            st.metric("CE Flow", format_number(ce_flow))
            st.metric("PE Flow", format_number(pe_flow))
            net_emoji = "🟢" if net_flow > 0 else ("🔴" if net_flow < 0 else "⚪")
            st.metric(f"{net_emoji} Net", format_number(net_flow))
        
            
            st.markdown("**CE vs PE Race**")
            st.markdown(race_bar)
            st.caption(dominance)
        with col2:
            st.markdown("**Δ 1 Minute**")
            st.metric("CE Δ", format_number(ce_1min))
            st.metric("PE Δ", format_number(pe_1min))
            net_emoji = "🟢" if net_1min > 0 else ("🔴" if net_1min < 0 else "⚪")
            st.metric(f"{net_emoji} Net Δ", format_number(net_1min))
        
        with col3:
            st.markdown("**Δ 5 Minutes**")
            if ce_5min is not None:
                st.metric("CE Δ", format_number(ce_5min))
                st.metric("PE Δ", format_number(pe_5min))
                net_emoji = "🟢" if net_5min > 0 else ("🔴" if net_5min < 0 else "⚪")
                st.metric(f"{net_emoji} Net Δ", format_number(net_5min))
            else:
                st.info("Collecting...")
        
        with col4:
            st.markdown("**Momentum**")
            momentum_signal, momentum_color = get_momentum_signal(net_1min, net_5min)
            st.markdown(f'<div class="momentum-gauge" style="background-color: {momentum_color}; color: white;">{momentum_signal}</div>', unsafe_allow_html=True)
            
            if "ACCELERATING" in momentum_signal or "SURGING" in momentum_signal:
                if net_1min > 0:
                    st.success("🎯 BUY")
                else:
                    st.error("🎯 SELL")
        
        st.markdown("---")
    
    st.markdown("### 📈 Stocks Momentum")
    
    stocks_ce = cached_data.get("stocks_ce_cod", 0.0)
    stocks_pe = cached_data.get("stocks_pe_cod", 0.0)
    stocks_net = stocks_ce - stocks_pe
    
    stocks_ce_1min = deltas.get("stocks_ce_1min", 0)
    stocks_pe_1min = deltas.get("stocks_pe_1min", 0)
    stocks_net_1min = stocks_ce_1min - stocks_pe_1min
    
    stocks_ce_5min = deltas.get("stocks_ce_5min", 0)
    stocks_pe_5min = deltas.get("stocks_pe_5min", 0)
    stocks_net_5min = stocks_ce_5min - stocks_pe_5min
    
    momentum_signal_stocks, momentum_color_stocks = get_momentum_signal(stocks_net_1min, stocks_net_5min)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("**Cumulative**")
        st.metric("CE Flow", format_number(stocks_ce))
        st.metric("PE Flow", format_number(stocks_pe))
        net_emoji = "🟢" if stocks_net > 0 else ("🔴" if stocks_net < 0 else "⚪")
        st.metric(f"{net_emoji} Net", format_number(stocks_net))
    
    with col2:
        st.markdown("**Δ 1 Minute**")
        st.metric("CE Δ", format_number(stocks_ce_1min))
        st.metric("PE Δ", format_number(stocks_pe_1min))
        net_emoji = "🟢" if stocks_net_1min > 0 else ("🔴" if stocks_net_1min < 0 else "⚪")
        st.metric(f"{net_emoji} Net Δ", format_number(stocks_net_1min))
    
    with col3:
        st.markdown("**Δ 5 Minutes**")
        if stocks_ce_5min is not None:
            st.metric("CE Δ", format_number(stocks_ce_5min))
            st.metric("PE Δ", format_number(stocks_pe_5min))
            net_emoji = "🟢" if stocks_net_5min > 0 else ("🔴" if stocks_net_5min < 0 else "⚪")
            st.metric(f"{net_emoji} Net Δ", format_number(stocks_net_5min))
        else:
            st.info("Collecting...")
    
    with col4:
        st.markdown("**Momentum**")
        st.markdown(f"""
        <div class="momentum-gauge" style="background-color: {momentum_color_stocks}; color: white;">
            {momentum_signal_stocks}
        </div>
        """, unsafe_allow_html=True)

else:
    st.info("⏳ Start polling to see live momentum data")

st.markdown("---")


# ====================
# NIFTY FUTURES CARD
# ====================
st.markdown("---")
st.subheader("📊 NIFTY Current Month Futures")

# Get from session state (updated by polling thread)
nifty_futures_data_display = st.session_state.get('nifty_futures_data', None)

# If not in session state, try cache as fallback
if not nifty_futures_data_display:
    cached = load_dashboard_cache()
    if cached and 'nifty_futures_data' in cached:
        nifty_futures_data_display = cached['nifty_futures_data']
        # Store in session state for next time
        st.session_state.nifty_futures_data = nifty_futures_data_display

if nifty_futures_data_display:
    fut_col1, fut_col2, fut_col3, fut_col4 = st.columns(4)
    
    with fut_col1:
        st.markdown(f"**{nifty_futures_data_display['symbol']}**")
        st.caption(f"Exp: {nifty_futures_data_display['expiry']}")
        st.metric(
            "Price", 
            f"₹{nifty_futures_data_display['price']:.2f}",
            f"{nifty_futures_data_display['change_pct']:+.2f}%"
        )
    
    with fut_col2:
        st.markdown("**Buyers vs Sellers**")
        buyers = nifty_futures_data_display['buyers']
        sellers = nifty_futures_data_display['sellers']
        total = buyers + sellers
        
        if total > 0:
            buyers_pct = (buyers / total) * 100
            sellers_pct = (sellers / total) * 100
            
            st.metric("🟢 Buyers", format_number(buyers))
            st.caption(f"{buyers_pct:.1f}% of total")
            st.metric("🔴 Sellers", format_number(sellers))
            st.caption(f"{sellers_pct:.1f}% of total")
            
            if buyers > sellers * 1.5:
                st.success("**🚀 BUYERS DOMINATING**")
            elif sellers > buyers * 1.5:
                st.error("**📉 SELLERS DOMINATING**")
            else:
                st.info("**⚖️ BALANCED**")
        else:
            st.info("No volume data yet")
    
    with fut_col3:
        st.markdown("**Open Interest**")
        oi_change_pct = (nifty_futures_data_display['oi_change'] / nifty_futures_data_display['oi'] * 100) if nifty_futures_data_display['oi'] > 0 else 0
        
        st.metric(
            "Total OI", 
            format_number(nifty_futures_data_display['oi']),
            f"{oi_change_pct:+.1f}%"
        )
        st.metric("OI Change", format_number(nifty_futures_data_display['oi_change']))
    
    with fut_col4:
        st.markdown("**Market Signal**")
        
        price_up = nifty_futures_data_display['change_pct'] > 0.1
        price_down = nifty_futures_data_display['change_pct'] < -0.1
        oi_up = nifty_futures_data_display['oi_change'] > 0
        
        if price_up and oi_up:
            st.success("🟢 **LONG BUILDUP**")
            st.caption("Bullish: Price ↑ + OI ↑")
        elif price_down and oi_up:
            st.error("🔴 **SHORT BUILDUP**")
            st.caption("Bearish: Price ↓ + OI ↑")
        elif price_up and not oi_up:
            st.warning("🟡 **SHORT COVERING**")
            st.caption("Weak: Price ↑ + OI ↓")
        elif price_down and not oi_up:
            st.info("🔵 **LONG UNWINDING**")
            st.caption("Weak: Price ↓ + OI ↓")
        else:
            st.info("**NEUTRAL**")
            st.caption("No clear signal")
else:
    st.info("⏳ Waiting for NIFTY Futures data...")
    st.caption("Data will appear once polling starts")


st.subheader("💹 Combined CE/PE Summary")

if cached_data:
    indices_ce = cached_data.get("indices_ce_cod", 0.0)
    indices_pe = cached_data.get("indices_pe_cod", 0.0)
    stocks_ce = cached_data.get("stocks_ce_cod", 0.0)
    stocks_pe = cached_data.get("stocks_pe_cod", 0.0)
    indices_net = indices_ce - indices_pe
    stocks_net = stocks_ce - stocks_pe
    total_net = indices_net + stocks_net
    
    if abs(total_net) < 10000:
        overall_sentiment = "⚪ NEUTRAL"
    elif total_net > 0:
        overall_sentiment = "🟢 BULLISH"
    else:
        overall_sentiment = "🔴 BEARISH"
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"### 📊 Indices ({len(engine.indices_with_fo)})")
        st.metric("CE Flow", format_number(indices_ce))
        st.metric("PE Flow", format_number(indices_pe))
        net_color = "🟢" if indices_net > 0 else ("🔴" if indices_net < 0 else "⚪")
        st.metric(f"{net_color} Net", format_number(indices_net))
    with col2:
        st.markdown(f"### 📈 Stocks ({len(engine.stocks_with_fo)})")
        st.metric("CE Flow", format_number(stocks_ce))
        st.metric("PE Flow", format_number(stocks_pe))
        net_color = "🟢" if stocks_net > 0 else ("🔴" if stocks_net < 0 else "⚪")
        st.metric(f"{net_color} Net", format_number(stocks_net))
    with col3:
        st.markdown("### 💰 Total Market")
        total_ce = indices_ce + stocks_ce
        total_pe = indices_pe + stocks_pe
        st.metric("Total CE", format_number(total_ce))
        st.metric("Total PE", format_number(total_pe))
        st.markdown(f"<h3>{overall_sentiment}</h3>", unsafe_allow_html=True)
        st.metric("Net Flow", format_number(total_net))
else:
    st.info("Start polling to see data")

st.markdown("---")

with st.expander("📈 View Top 10 Stocks (Live Rankings)", expanded=False):
    # Try to get live data first, then cached data, then show available stocks
    stocks_data = {}
    
    # Priority 1: Live polling data
    if cached_data and "stocks_data" in cached_data and cached_data["stocks_data"]:
        stocks_data = cached_data["stocks_data"]
        st.success("🟢 Live Data")
    
    # Priority 2: Cached data from file (last session)
    elif DASHBOARD_CACHE_FILE.exists():
        try:
            with open(DASHBOARD_CACHE_FILE, "rb") as f:
                cache = pickle.load(f)
            if "stocks_data" in cache and cache["stocks_data"]:
                stocks_data = cache["stocks_data"]
                cache_time = cache.get("cached_at", "Unknown")
                st.info(f"📊 Cached Data (Last: {cache_time})")
        except:
            pass
    
    # Priority 3: Show message about waiting for data
    if not stocks_data:
        if hasattr(engine, 'stocks_with_fo') and engine.stocks_with_fo:
            st.info(f"⏳ Tracking {len(engine.stocks_with_fo)} F&O stocks. Top 10 will appear after first data collection cycle (~10-20 seconds)")
            st.caption("💡 The polling system is collecting live options flow data. Refresh page in a few moments.")
        else:
            st.warning("⚠️ No stocks configured for tracking. Check fno_master.json file.")
    
    # Display stocks data
    if stocks_data:
        # Show live rankings
        sorted_stocks = sorted(stocks_data.items(), key=lambda x: abs(x[1].get("net_flow", 0)), reverse=True)[:10]
        
        if sorted_stocks:
            st.markdown("### 🔥 Top 10 by Net Flow")
            
            for rank, (stock_name, data) in enumerate(sorted_stocks, 1):
                ce_flow = data.get("ce_flow", 0)
                pe_flow = data.get("pe_flow", 0)
                net_flow = data.get("net_flow", 0)
                stock_price = data.get("price")
                change_pct = data.get("change_pct")
                
                sector = sector_mapping.get(stock_name.upper(), "N/A")
                
                # Calculate CE vs PE percentage
                total_flow = ce_flow + pe_flow
                if total_flow > 0:
                    ce_pct = (ce_flow / total_flow) * 100
                    pe_pct = (pe_flow / total_flow) * 100
                else:
                    ce_pct = 50
                    pe_pct = 50
                
                # Display
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    # Stock name and sector
                    price_str = f"₹{stock_price:,.2f}" if stock_price else "N/A"
                    change_str = f"({change_pct:+.2f}%)" if change_pct is not None else ""
                    st.markdown(f"**{rank}. {stock_name}** {price_str} {change_str}")
                    st.caption(f"_{sector}_")
                    
                    # CE/PE race bar
                    st.progress(ce_pct / 100, text=f"CE: {ce_pct:.1f}% | PE: {pe_pct:.1f}%")
                
                with col2:
                    # Net flow
                    if net_flow > 0:
                        st.metric("Net", f"+{net_flow:,.0f}", delta="Bullish", delta_color="normal")
                    else:
                        st.metric("Net", f"{net_flow:,.0f}", delta="Bearish", delta_color="inverse")
                
                st.markdown("---")

# ============================================
# MARKET-WIDE PERFORMANCE (Outside Expander)
# ============================================
# Get stocks_data from cache
if cached_data and "stocks_data" in cached_data:
    stocks_data = cached_data.get("stocks_data", {})
    
    if stocks_data and len(stocks_data) > 0:
        st.markdown("")
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        st.markdown("### 📊 MARKET-WIDE PERFORMANCE (All 209 F&O Stocks)")
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        

st.markdown("---")

# ============================================
# INDICES-WIDE PERFORMANCE (All Tracked Indices)
# ============================================
if cached_data and "indices_data" in cached_data:
    indices_data_perf = cached_data.get("indices_data", {})
    
    if indices_data_perf and len(indices_data_perf) > 0:
        st.markdown("")
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        st.markdown(f"### 📊 INDICES-WIDE PERFORMANCE ({len(indices_data_perf)} Indices Tracked)")
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        # Calculate performance stats
        total_indices = len(indices_data_perf)
        positive_indices = []
        negative_indices = []
        neutral_indices = []
        
        for idx_name, idx_data in indices_data_perf.items():
            # Get price change - try different keys
            change_pct = 0
            if "change_pct" in idx_data:
                change_pct = idx_data["change_pct"]
            elif "price" in idx_data and "prev_close" in idx_data:
                if idx_data["prev_close"] and idx_data["prev_close"] > 0:
                    change_pct = ((idx_data["price"] - idx_data["prev_close"]) / idx_data["prev_close"]) * 100
            
            if change_pct > 0:
                positive_indices.append((idx_name, change_pct))
            elif change_pct < 0:
                negative_indices.append((idx_name, change_pct))
            else:
                neutral_indices.append(idx_name)
        
        pos_count = len(positive_indices)
        neg_count = len(negative_indices)
        neutral_count = len(neutral_indices)
        
        pos_pct = (pos_count / total_indices * 100) if total_indices > 0 else 0
        neg_pct = (neg_count / total_indices * 100) if total_indices > 0 else 0
        
        # Breakdown by strength
        very_strong_up = len([i for i in positive_indices if i[1] > 2])
        strong_up = len([i for i in positive_indices if 1 <= i[1] <= 2])
        weak_up = len([i for i in positive_indices if 0 < i[1] < 1])
        
        weak_down = len([i for i in negative_indices if -1 < i[1] < 0])
        strong_down = len([i for i in negative_indices if -2 <= i[1] <= -1])
        very_strong_down = len([i for i in negative_indices if i[1] < -2])
        
        # Display performance bar
        st.markdown("**Index Performance Distribution:**")
        
        col1, col2, col3 = st.columns([max(pos_pct, 1), max(neg_pct, 1), 0.1])
        
        with col1:
            st.markdown(f'<div style="background: linear-gradient(to right, #00ff00, #90EE90); padding: 20px; text-align: center; border-radius: 5px;"><b>🟢 POSITIVE</b><br>{pos_count} indices ({pos_pct:.0f}%)</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown(f'<div style="background: linear-gradient(to right, #ffcccb, #ff0000); padding: 20px; text-align: center; border-radius: 5px;"><b>🔴 NEGATIVE</b><br>{neg_count} indices ({neg_pct:.0f}%)</div>', unsafe_allow_html=True)
        
        st.markdown("")
        
        # Detailed breakdown
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 🟢 Advancing Indices")
            st.metric("Very Strong (> +2%)", f"{very_strong_up} indices")
            st.metric("Strong (+1% to +2%)", f"{strong_up} indices")
            st.metric("Weak (0% to +1%)", f"{weak_up} indices")
        
        with col2:
            st.markdown("#### 🔴 Declining Indices")
            st.metric("Weak (0% to -1%)", f"{weak_down} indices")
            st.metric("Strong (-1% to -2%)", f"{strong_down} indices")
            st.metric("Very Strong (< -2%)", f"{very_strong_down} indices")
        
        st.markdown("")
        
        # Market breadth signal
        if pos_pct >= 60:
            sentiment = "🚀 STRONG BREADTH"
            sentiment_text = f"{pos_pct:.0f}% indices advancing - Broad-based rally"
            st.success(f"**Market Breadth:** {sentiment} - {sentiment_text}")
        elif neg_pct >= 60:
            sentiment = "📉 WEAK BREADTH"
            sentiment_text = f"{neg_pct:.0f}% indices declining - Broad-based selloff"
            st.error(f"**Market Breadth:** {sentiment} - {sentiment_text}")
        else:
            sentiment = "⚖️ MIXED BREADTH"
            sentiment_text = f"Market split - {pos_pct:.0f}% up, {neg_pct:.0f}% down"
            st.info(f"**Market Breadth:** {sentiment} - {sentiment_text}")
        
        st.markdown("")
        
        # ============================================
        # AGGREGATE CE vs PE RACE (All Indices)
        # ============================================
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        st.markdown("### 🏁 ALL INDICES CE vs PE RACE (Aggregate Flow)")
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        st.markdown("**Total Options Flow Across All Tracked Indices:**")
        
        # Calculate aggregate
        total_ce_flow_idx = sum(d.get("ce_flow", 0) for n, d in indices_data_perf.items())
        total_pe_flow_idx = sum(d.get("pe_flow", 0) for n, d in indices_data_perf.items())
        total_flow_idx = total_ce_flow_idx + total_pe_flow_idx
        
        if total_flow_idx > 0:
            ce_pct_idx = (total_ce_flow_idx / total_flow_idx) * 100
            pe_pct_idx = 100 - ce_pct_idx
            
            avg_ce_idx = total_ce_flow_idx / total_indices if total_indices > 0 else 0
            avg_pe_idx = total_pe_flow_idx / total_indices if total_indices > 0 else 0
            
            # Visual race bar
            ce_blocks_idx = int(round(ce_pct_idx / 10))
            pe_blocks_idx = 10 - ce_blocks_idx
            race_bar_idx = f"[🟢{'▓' * ce_blocks_idx}🔴{'▓' * pe_blocks_idx}]"
            
            st.markdown(f"**CE vs PE Race:**")
            st.markdown(f"## {race_bar_idx} {ce_pct_idx:.0f}% CE | {pe_pct_idx:.0f}% PE")
            
            st.markdown("")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### 🟢 CE Flow (Calls)")
                st.metric("Total CE Flow", format_number(total_ce_flow_idx))
                st.metric("Average per Index", format_number(avg_ce_idx))
                if ce_pct_idx >= 60:
                    st.success("🚀 CE DOMINATING")
                elif ce_pct_idx >= 55:
                    st.info("🟢 CE Leading")
                else:
                    st.warning("⚖️ Balanced")
            
            with col2:
                st.markdown("#### 🔴 PE Flow (Puts)")
                st.metric("Total PE Flow", format_number(total_pe_flow_idx))
                st.metric("Average per Index", format_number(avg_pe_idx))
                if pe_pct_idx >= 60:
                    st.error("📉 PE DOMINATING")
                elif pe_pct_idx >= 55:
                    st.info("🔴 PE Leading")
                else:
                    st.warning("⚖️ Balanced")
            
            st.markdown("")
            
            # Signal
            st.markdown("**Indices Options Signal:**")
            
            if ce_pct_idx >= 65:
                signal = "🚀 BULLS VERY AGGRESSIVE"
                interpretation = "Smart money heavily buying calls across indices - strong bullish conviction"
                st.success(f"**{signal}**")
                st.caption(interpretation)
            elif ce_pct_idx >= 55:
                signal = "🟢 BULLS AGGRESSIVE"
                interpretation = "More call buying than put buying - moderate bullish sentiment"
                st.success(f"**{signal}**")
                st.caption(interpretation)
            elif pe_pct_idx >= 65:
                signal = "📉 BEARS VERY AGGRESSIVE"
                interpretation = "Smart money heavily buying puts across indices - strong bearish conviction"
                st.error(f"**{signal}**")
                st.caption(interpretation)
            elif pe_pct_idx >= 55:
                signal = "🔴 BEARS AGGRESSIVE"
                interpretation = "More put buying than call buying - moderate bearish sentiment"
                st.error(f"**{signal}**")
                st.caption(interpretation)
            else:
                signal = "⚖️ BALANCED FLOW"
                interpretation = "Call and put buying roughly equal - no clear directional bias"
                st.info(f"**{signal}**")
                st.caption(interpretation)
            
            st.caption(f"📊 CE/PE Ratio: {(total_ce_flow_idx/total_pe_flow_idx):.2f}" if total_pe_flow_idx > 0 else "📊 CE/PE Ratio: N/A")
        
        st.markdown("")
        
        # ============================================
        # TOP & BOTTOM PERFORMERS
        # ============================================
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        st.markdown("### 🎯 SECTOR PERFORMANCE")
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        # Prepare sorted list
        all_idx_with_change = []
        for idx_name, idx_data in indices_data_perf.items():
            change_pct = 0
            if "change_pct" in idx_data:
                change_pct = idx_data["change_pct"]
            elif "price" in idx_data and "prev_close" in idx_data:
                if idx_data["prev_close"] and idx_data["prev_close"] > 0:
                    change_pct = ((idx_data["price"] - idx_data["prev_close"]) / idx_data["prev_close"]) * 100
            
            ce_flow = idx_data.get("ce_flow", 0)
            pe_flow = idx_data.get("pe_flow", 0)
            all_idx_with_change.append((idx_name, change_pct, ce_flow, pe_flow))
        
        sorted_indices = sorted(all_idx_with_change, key=lambda x: x[1], reverse=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 🥇 TOP 5 PERFORMERS")
            medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
            for i, (name, change, ce, pe) in enumerate(sorted_indices[:5]):
                total = ce + pe
                ce_pct_sector = (ce / total * 100) if total > 0 else 50
                
                # CE/PE bar
                ce_blocks_s = int(round(ce_pct_sector / 10))
                pe_blocks_s = 10 - ce_blocks_s
                mini_bar = f"[🟢{'▓' * ce_blocks_s}🔴{'▓' * pe_blocks_s}]"
                
                # Signal
                signal_icon = "🚀" if ce_pct_sector >= 70 else "✅" if ce_pct_sector >= 60 else "⚖️"
                
                medal = medals[i] if i < 5 else "📊"
                st.markdown(f"{medal} **{name}**: {change:+.2f}%")
                st.caption(f"{mini_bar} {ce_pct_sector:.0f}% CE {signal_icon}")
        
        with col2:
            st.markdown("#### 📉 BOTTOM 5 PERFORMERS")
            for i, (name, change, ce, pe) in enumerate(sorted_indices[-5:][::-1]):
                total = ce + pe
                ce_pct_sector = (ce / total * 100) if total > 0 else 50
                
                # CE/PE bar
                ce_blocks_s = int(round(ce_pct_sector / 10))
                pe_blocks_s = 10 - ce_blocks_s
                mini_bar = f"[🟢{'▓' * ce_blocks_s}🔴{'▓' * pe_blocks_s}]"
                
                # Signal
                signal_icon = "⚠️" if ce_pct_sector < 40 else "📉" if ce_pct_sector < 50 else "⚖️"
                
                st.markdown(f"**{name}**: {change:+.2f}%")
                st.caption(f"{mini_bar} {ce_pct_sector:.0f}% CE {signal_icon}")
        
        st.markdown("")

st.caption("🔥 Live Momentum Trading System - Actionable Alerts with Strike Prices! 🚀")