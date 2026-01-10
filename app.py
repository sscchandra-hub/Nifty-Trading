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
import imaplib
import email
from email.header import decode_header
from html.parser import HTMLParser

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
if 'alert_history' not in st.session_state:
    st.session_state.alert_history = []
if 'session_start_time' not in st.session_state:
    st.session_state.session_start_time = datetime.now()
if 'poll_count' not in st.session_state:
    st.session_state.poll_count = 0
if 'dark_mode' not in st.session_state:
    st.session_state.dark_mode = False
if 'watchlist' not in st.session_state:
    # Try to load from cache
    try:
        watchlist_file = Path('.cache/watchlist.json')
        if watchlist_file.exists():
            import json
            with open(watchlist_file, 'r') as f:
                st.session_state.watchlist = set(json.load(f))
        else:
            st.session_state.watchlist = set()
    except:
        st.session_state.watchlist = set()
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

# Security validation
def validate_credentials():
    """Validate environment variables and security settings"""
    issues = []

    # Check .env file exists
    env_file = Path(".env")
    if not env_file.exists():
        issues.append("⚠️ .env file not found - create one with your API credentials")
    else:
        # Check file permissions (Unix/Linux/Mac only)
        if hasattr(os, 'stat') and env_file.exists():
            import stat
            mode = os.stat(env_file).st_mode
            # Warn if file is readable by others (not just owner)
            if mode & stat.S_IROTH or mode & stat.S_IWOTH:
                issues.append("🔒 Security Warning: .env file is readable by others (run: chmod 600 .env)")

    # Validate required credentials
    if not API_KEY or not API_SECRET:
        issues.append("❌ KITE_API_KEY and KITE_API_SECRET are required in .env file")
    elif len(API_KEY) < 10 or len(API_SECRET) < 10:
        issues.append("⚠️ API credentials look invalid (too short)")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        issues.append("⚠️ Telegram credentials missing - alerts will not work")

    # Check .gitignore exists and contains .env
    gitignore_file = Path(".gitignore")
    if gitignore_file.exists():
        gitignore_content = gitignore_file.read_text()
        if ".env" not in gitignore_content:
            issues.append("🔒 Security Warning: .env not in .gitignore - your credentials may be exposed!")
    else:
        issues.append("⚠️ No .gitignore file - credentials may be committed to git!")

    # Print validation results
    if issues:
        print("\n" + "="*60)
        print("🔐 SECURITY VALIDATION")
        print("="*60)
        for issue in issues:
            print(issue)
        print("="*60 + "\n")
    else:
        print("✅ Security validation passed - credentials properly configured\n")

validate_credentials()

DERIV_FUT_SEGMENTS = {"NFO-FUT", "BFO-FUT"}
DERIV_OPT_SEGMENTS = {"NFO-OPT", "BFO-OPT"}
INDEX_NAME_WHITELIST = {
    # Original 5 indices
    "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX",
    # Sectoral indices (F&O + Non-F&O for complete sector view)
    "NIFTY MIDCAP 50", "NIFTY AUTO", "NIFTY PHARMA", "NIFTY METAL", "NIFTY ENERGY",
    "NIFTY FMCG", "NIFTY REALTY", "NIFTY PSU BANK", "NIFTY INFRA", "NIFTY OIL & GAS",
    # Additional sectoral indices (Non-F&O but useful for sector performance)
    "INDIA VIX", "NIFTY HEALTHCARE", "NIFTY IT", "NIFTY MEDIA",
    # Defence sector (checking both spellings)
    "NIFTY IND DEFENCE", "NIFTY INDIA DEFENCE"
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
    last_stock_alert: dict = field(default_factory=dict)  # Track stock alerts with cooldowns and momentum data (time, change_pct, net_flow)
    top_10_stocks: set = field(default_factory=set)  # Track current Top 10 stocks
    alert_cooldowns: dict = field(default_factory=dict)  # Track smart alert cooldowns (stock_name -> timestamp)
    daily_score_history: list = field(default_factory=list)  # Track all scores for daily summary
    nifty_momentum_state: str = None  # Track NIFTY momentum class for reversal detection
    nifty_momentum_last_alert: datetime = None  # Track last NIFTY momentum alert time
    sector_mapping: dict = field(default_factory=dict)  # Stock to sector mapping

    # Enhanced Alert System - 3-minute confirmation tracking
    nifty_score_buffer: list = field(default_factory=list)  # Last 3 scores for confirmation
    nifty_price_buffer: list = field(default_factory=list)  # Last 3 prices for confirmation
    nifty_confirmation_start: datetime = None  # When confirmation period started
    nifty_last_alert_type: str = None  # Type of last alert sent (STRONG_BULLISH, BULLISH, etc.)
    nifty_last_alert_score: int = 0  # Score when last alert was sent
    nifty_universal_cooldown: datetime = None  # Universal cooldown for all NIFTY alerts

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

# ============================================
# ENHANCED UI HELPER FUNCTIONS
# ============================================

def create_cepe_progress_bar(ce_value, pe_value, show_labels=True):
    """
    Create visual CE vs PE progress bar using HTML/CSS
    Returns HTML string for st.markdown()
    """
    total = ce_value + pe_value
    if total > 0:
        ce_pct = (ce_value / total) * 100
        pe_pct = 100 - ce_pct
    else:
        ce_pct = 50
        pe_pct = 50

    ce_label = f"{ce_pct:.1f}%" if show_labels else ""
    pe_label = f"{pe_pct:.1f}%" if show_labels else ""

    html = f"""<div class="cepe-bar-container"><div class="cepe-bar-ce" style="width: {ce_pct}%;">{ce_label}</div><div class="cepe-bar-pe" style="width: {pe_pct}%;">{pe_label}</div></div>"""
    return html

def get_status_indicator(value, threshold_high=0, threshold_low=0):
    """
    Return traffic light status indicator based on value
    🟢 Green for positive/bullish
    🟡 Yellow for neutral
    🔴 Red for negative/bearish
    """
    if value > threshold_high:
        return '<span class="status-green">🟢</span>'
    elif value < threshold_low:
        return '<span class="status-red">🔴</span>'
    else:
        return '<span class="status-yellow">🟡</span>'

def create_enhanced_section_header(title, icon="📊"):
    """
    Create enhanced section header with icon and styling
    """
    html = f"""
    <div class="section-header">
        <h3 style="margin: 0; color: #1f77b4; font-size: 1.5rem;">
            {icon} {title}
        </h3>
    </div>
    """
    return html

def create_metric_card(label, value, card_type="neutral"):
    """
    Create color-coded metric card
    card_type: 'bullish', 'bearish', or 'neutral'
    """
    class_name = f"metric-card-{card_type}"
    html = f"""
    <div class="{class_name}">
        <div style="font-size: 0.9rem; color: #666; margin-bottom: 0.3rem;">{label}</div>
        <div style="font-size: 1.5rem; font-weight: bold; color: #333;">{value}</div>
    </div>
    """
    return html

def create_market_overview_panel(indices_data, deltas):
    """
    Create compact Market Overview Panel showing key metrics at a glance
    """
    # Calculate aggregate metrics
    total_ce = sum(idx.get('ce_flow', 0) for idx in indices_data.values())
    total_pe = sum(idx.get('pe_flow', 0) for idx in indices_data.values())
    net_flow = total_ce - total_pe

    # Get delta metrics
    indices_ce_1min = deltas.get('indices_ce_1min', 0)
    indices_pe_1min = deltas.get('indices_pe_1min', 0)
    net_1min = indices_ce_1min - indices_pe_1min

    # Determine market sentiment
    if net_flow > 0 and net_1min > 0:
        sentiment = "🟢 BULLISH"
        sentiment_color = "#28a745"
    elif net_flow < 0 and net_1min < 0:
        sentiment = "🔴 BEARISH"
        sentiment_color = "#dc3545"
    else:
        sentiment = "🟡 NEUTRAL"
        sentiment_color = "#ffc107"

    # Calculate PCR (Put-Call Ratio)
    pcr = (total_pe / total_ce) if total_ce > 0 else 0

    html = f"""
    <div class="overview-panel">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin-bottom: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 0.9rem; opacity: 0.9;">Market Sentiment</div>
                <div style="font-size: 1.8rem; font-weight: bold; color: {sentiment_color};">{sentiment}</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 0.9rem; opacity: 0.9;">Net Flow</div>
                <div style="font-size: 1.8rem; font-weight: bold;">{format_number(net_flow)}</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 0.9rem; opacity: 0.9;">1min Δ</div>
                <div style="font-size: 1.8rem; font-weight: bold;">{format_number(net_1min)}</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 0.9rem; opacity: 0.9;">PCR</div>
                <div style="font-size: 1.8rem; font-weight: bold;">{pcr:.2f}</div>
            </div>
        </div>
        <div style="margin-top: 1rem;">
            {create_cepe_progress_bar(total_ce, total_pe, show_labels=True)}
        </div>
    </div>
    """
    return html

def create_stock_card(stock_name, price, change_pct, net_flow, card_type="neutral"):
    """
    Create color-coded stock card for gainers/losers
    card_type: 'gainer', 'loser', or 'neutral'
    """
    if card_type == "gainer":
        bg_color = "linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%)"
        border_color = "#28a745"
    elif card_type == "loser":
        bg_color = "linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%)"
        border_color = "#dc3545"
    else:
        bg_color = "linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%)"
        border_color = "#ffc107"

    flow_color = "#28a745" if net_flow > 0 else "#dc3545"
    flow_emoji = "🟢" if net_flow > 0 else "🔴"
    change_emoji = "🟢" if change_pct > 0 else "🔴"
    price_str = f"₹{price:,.2f}" if price else "N/A"

    html = f"""<div style="background: {bg_color}; border-left: 4px solid {border_color}; padding: 0.8rem; border-radius: 8px; margin: 0.5rem 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);"><div style="font-size: 1.1rem; font-weight: bold; color: #333; margin-bottom: 0.3rem;">{stock_name}</div><div style="font-size: 0.9rem; color: #666; margin-bottom: 0.3rem;">{price_str} <span style="color: {flow_color}; font-weight: bold;">{change_emoji} {change_pct:+.2f}%</span></div><div style="font-size: 0.85rem; color: #666;">{flow_emoji} Flow: {format_number(net_flow)}</div></div>"""
    return html

def create_stocks_market_overview_panel(stocks_data, deltas):
    """
    Create compact Stocks Market Overview Panel showing key metrics at a glance
    """
    if not stocks_data:
        return ""

    # Calculate aggregate metrics
    total_stocks = len(stocks_data)
    total_ce = sum(s.get('ce_flow', 0) for s in stocks_data.values())
    total_pe = sum(s.get('pe_flow', 0) for s in stocks_data.values())
    net_flow = total_ce - total_pe

    # Get delta metrics
    stocks_ce_1min = deltas.get('stocks_ce_1min', 0)
    stocks_pe_1min = deltas.get('stocks_pe_1min', 0)
    net_1min = stocks_ce_1min - stocks_pe_1min

    # Count bullish/bearish stocks
    bullish_count = sum(1 for s in stocks_data.values() if s.get('net_flow', 0) > 0)
    bearish_count = sum(1 for s in stocks_data.values() if s.get('net_flow', 0) < 0)

    # Determine market sentiment
    if bullish_count > bearish_count:
        sentiment = "🟢 BULLISH"
        sentiment_color = "#28a745"
    elif bearish_count > bullish_count:
        sentiment = "🔴 BEARISH"
        sentiment_color = "#dc3545"
    else:
        sentiment = "🟡 NEUTRAL"
        sentiment_color = "#ffc107"

    # Calculate breadth (bullish vs bearish ratio)
    bullish_pct = (bullish_count / total_stocks * 100) if total_stocks > 0 else 50
    bearish_pct = (bearish_count / total_stocks * 100) if total_stocks > 0 else 50

    html = f"""
    <div class="overview-panel">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin-bottom: 1rem;">
            <div style="text-align: center;">
                <div style="font-size: 0.9rem; opacity: 0.9;">Market Sentiment</div>
                <div style="font-size: 1.8rem; font-weight: bold; color: {sentiment_color};">{sentiment}</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 0.9rem; opacity: 0.9;">Net Flow</div>
                <div style="font-size: 1.8rem; font-weight: bold;">{format_number(net_flow)}</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 0.9rem; opacity: 0.9;">1min Δ</div>
                <div style="font-size: 1.8rem; font-weight: bold;">{format_number(net_1min)}</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 0.9rem; opacity: 0.9;">Market Breadth</div>
                <div style="font-size: 1.8rem; font-weight: bold;">{bullish_count}/{total_stocks}</div>
            </div>
        </div>
        <div style="margin-top: 1rem;">
            <div style="font-size: 0.85rem; margin-bottom: 0.3rem; color: #fff; opacity: 0.9;">Bullish vs Bearish Stocks</div>
            {create_cepe_progress_bar(bullish_count, bearish_count, show_labels=True)}
        </div>
    </div>
    """
    return html

def create_stock_performance_heatbar(stocks_data):
    """
    Create stock performance heat bar showing distribution across price change ranges
    """
    if not stocks_data:
        return ""

    # Get stocks with price data
    stocks_with_price = [s for s in stocks_data.values() if s.get('change_pct') is not None]

    if not stocks_with_price:
        return ""

    total_stocks = len(stocks_with_price)

    # Define ranges and count stocks in each
    ranges = {
        'dark_red': {'min': float('-inf'), 'max': -2.0, 'count': 0, 'color': '#dc3545', 'label': 'Below -2%'},
        'med_red': {'min': -2.0, 'max': -1.0, 'count': 0, 'color': '#e74c3c', 'label': '-2% to -1%'},
        'light_red': {'min': -1.0, 'max': 0.0, 'count': 0, 'color': '#f8d7da', 'label': '-1% to 0%'},
        'light_green': {'min': 0.0, 'max': 1.0, 'count': 0, 'color': '#d4edda', 'label': '0% to 1%'},
        'med_green': {'min': 1.0, 'max': 2.0, 'count': 0, 'color': '#28a745', 'label': '1% to 2%'},
        'dark_green': {'min': 2.0, 'max': float('inf'), 'count': 0, 'color': '#218838', 'label': 'Above 2%'}
    }

    # Count stocks in each range
    for stock in stocks_with_price:
        change_pct = stock.get('change_pct', 0)

        if change_pct < -2.0:
            ranges['dark_red']['count'] += 1
        elif -2.0 <= change_pct < -1.0:
            ranges['med_red']['count'] += 1
        elif -1.0 <= change_pct < 0.0:
            ranges['light_red']['count'] += 1
        elif 0.0 <= change_pct < 1.0:
            ranges['light_green']['count'] += 1
        elif 1.0 <= change_pct < 2.0:
            ranges['med_green']['count'] += 1
        else:  # >= 2.0
            ranges['dark_green']['count'] += 1

    # Calculate percentages
    for range_data in ranges.values():
        range_data['pct'] = (range_data['count'] / total_stocks * 100) if total_stocks > 0 else 0

    # Count bearish vs bullish
    bearish_count = ranges['dark_red']['count'] + ranges['med_red']['count'] + ranges['light_red']['count']
    bullish_count = ranges['light_green']['count'] + ranges['med_green']['count'] + ranges['dark_green']['count']

    # Build segments HTML first
    segments_html = ""
    for key in ['dark_red', 'med_red', 'light_red', 'light_green', 'med_green', 'dark_green']:
        range_data = ranges[key]
        if range_data['count'] > 0:
            text_color = '#fff' if key in ['dark_red', 'med_red', 'med_green', 'dark_green'] else '#333'
            segments_html += f'<div style="flex: {range_data["pct"]}; background-color: {range_data["color"]}; display: flex; flex-direction: column; justify-content: center; align-items: center; color: {text_color}; font-weight: bold; font-size: 0.85rem; border-right: 1px solid rgba(255,255,255,0.3);"><div style="font-size: 1.1rem;">{range_data["count"]}</div><div style="font-size: 0.7rem; opacity: 0.9;">{range_data["label"]}</div></div>'

    # Summary stats
    bearish_pct = (bearish_count / total_stocks * 100) if total_stocks > 0 else 0
    bullish_pct = (bullish_count / total_stocks * 100) if total_stocks > 0 else 0

    # Build complete HTML as single compact string
    html = f'<div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 10px; padding: 1.5rem; margin: 1rem 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);"><div style="text-align: center; font-size: 1.2rem; font-weight: bold; color: #333; margin-bottom: 1rem;">📊 STOCK PERFORMANCE DISTRIBUTION ({total_stocks} Stocks)</div><div style="display: flex; height: 60px; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 6px rgba(0,0,0,0.15); margin-bottom: 1rem;">{segments_html}</div><div style="display: flex; justify-content: space-between; font-size: 0.9rem; color: #666;"><div style="text-align: left;"><span style="color: #dc3545; font-weight: bold;">◄ Bearish: {bearish_count} stocks ({bearish_pct:.1f}%)</span></div><div style="text-align: right;"><span style="color: #28a745; font-weight: bold;">Bullish: {bullish_count} stocks ({bullish_pct:.1f}%) ►</span></div></div></div>'

    return html

# ============================================
# VWAP & SUPERTREND STRATEGY FUNCTIONS
# ============================================

def calculate_vwap(candles):
    """
    Calculate VWAP (Volume Weighted Average Price)
    VWAP = Cumulative(Typical Price * Volume) / Cumulative(Volume)
    Typical Price = (High + Low + Close) / 3
    """
    if not candles or len(candles) == 0:
        return None

    cumulative_tp_volume = 0
    cumulative_volume = 0

    for candle in candles:
        typical_price = (candle['high'] + candle['low'] + candle['close']) / 3
        volume = candle['volume']
        cumulative_tp_volume += typical_price * volume
        cumulative_volume += volume

    if cumulative_volume == 0:
        return None

    vwap = cumulative_tp_volume / cumulative_volume
    return vwap

def calculate_atr(candles, period=7):
    """
    Calculate ATR (Average True Range)
    TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
    ATR = average of TR over period
    """
    if not candles or len(candles) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(candles)):
        high = candles[i]['high']
        low = candles[i]['low']
        prev_close = candles[i-1]['close']

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    # Average of last 'period' true ranges
    atr = sum(true_ranges[-period:]) / period
    return atr

def calculate_supertrend(candles, atr_period=7, multiplier=3.0):
    """
    Calculate SuperTrend indicator
    Basic Band = (High + Low) / 2
    Upper Band = Basic Band + (Multiplier × ATR)
    Lower Band = Basic Band - (Multiplier × ATR)

    Returns: (supertrend_value, trend_direction)
    trend_direction: 'green' (bullish) or 'red' (bearish)
    """
    if not candles or len(candles) < atr_period + 1:
        return None, None

    atr = calculate_atr(candles, atr_period)
    if atr is None:
        return None, None

    # Get last candle
    last_candle = candles[-1]
    basic_band = (last_candle['high'] + last_candle['low']) / 2

    upper_band = basic_band + (multiplier * atr)
    lower_band = basic_band - (multiplier * atr)

    close_price = last_candle['close']

    # Determine trend direction
    if close_price > upper_band:
        trend = 'green'
        supertrend_value = lower_band
    elif close_price < lower_band:
        trend = 'red'
        supertrend_value = upper_band
    else:
        # Price between bands - use previous trend or default to red
        # For simplicity, if price is near lower band, it's bullish
        if close_price > basic_band:
            trend = 'green'
            supertrend_value = lower_band
        else:
            trend = 'red'
            supertrend_value = upper_band

    return supertrend_value, trend

def detect_vwap_supertrend_signal(candles, vwap, supertrend_value, supertrend_trend):
    """
    Detect VWAP + SuperTrend strategy signal

    Bullish Signal:
    - SuperTrend is GREEN (bullish)
    - VWAP is ABOVE SuperTrend
    - Last candle is GREEN (close > open)
    - Candle closes ABOVE VWAP

    Bearish Signal:
    - SuperTrend is RED (bearish)
    - VWAP is BELOW SuperTrend
    - Last candle is RED (close < open)
    - Candle closes BELOW VWAP

    Returns: ('BULLISH', 'BEARISH', or 'NEUTRAL')
    """
    if not candles or vwap is None or supertrend_value is None or supertrend_trend is None:
        return 'NEUTRAL'

    last_candle = candles[-1]
    candle_close = last_candle['close']
    candle_open = last_candle['open']

    # Check if candle is green or red
    is_green_candle = candle_close > candle_open
    is_red_candle = candle_close < candle_open

    # Bullish conditions
    if (supertrend_trend == 'green' and
        vwap > supertrend_value and
        is_green_candle and
        candle_close > vwap):
        return 'BULLISH'

    # Bearish conditions
    if (supertrend_trend == 'red' and
        vwap < supertrend_value and
        is_red_candle and
        candle_close < vwap):
        return 'BEARISH'

    return 'NEUTRAL'

def fetch_nifty_futures_15min_candles():
    """
    Fetch 15-minute candles for Nifty Futures from 9:15 AM to current time
    Returns list of candle dictionaries
    """
    try:
        if not hasattr(engine, 'nifty_fut_token') or not engine.nifty_fut_token:
            print("❌ Nifty Futures token not available")
            return None

        current_time = datetime.now()

        # Market hours check
        if current_time.time() < dt_time(9, 15):
            print("⏰ Market not open yet")
            return None

        # From 9:15 AM today
        from_date = current_time.replace(hour=9, minute=15, second=0, microsecond=0)
        # To current time
        to_date = current_time

        print(f"📊 Fetching 15-min candles for Nifty Futures from {from_date.strftime('%H:%M')} to {to_date.strftime('%H:%M')}")

        historical_data = engine.kite.historical_data(
            instrument_token=engine.nifty_fut_token,
            from_date=from_date,
            to_date=to_date,
            interval="15minute"
        )

        if historical_data and len(historical_data) > 0:
            print(f"✅ Fetched {len(historical_data)} candles for Nifty Futures")
            return historical_data
        else:
            print("⚠️ No historical data received")
            return None

    except Exception as e:
        print(f"❌ Error fetching 15-min candles: {e}")
        import traceback
        traceback.print_exc()
        return None

def create_vwap_supertrend_card(vwap, supertrend_value, supertrend_trend, signal, last_candle, ltp):
    """
    Create compact HTML card for VWAP & SuperTrend strategy (Option 1)
    """
    if vwap is None or supertrend_value is None:
        # Show placeholder card with structure when data is not available
        placeholder_html = '<div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 10px; padding: 1.5rem; margin: 1rem 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);"><div style="text-align: center; font-size: 1.3rem; font-weight: bold; color: #1f77b4; margin-bottom: 1rem;">📈 VWAP & SUPERTREND STRATEGY (15-min)</div><div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 1rem; border-radius: 5px; margin-bottom: 1rem;"><p style="margin: 0; color: #856404; font-weight: bold;">⏳ Waiting for market data... (requires at least 8 candles after 9:15 AM)</p></div><div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1rem;"><div style="background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%); border-radius: 8px; padding: 1rem; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); opacity: 0.6;"><div style="font-size: 0.85rem; color: #666; margin-bottom: 0.5rem;">SIGNAL</div><div style="font-size: 1.5rem; font-weight: bold; color: #ffc107;">🟡 NEUTRAL</div></div><div style="background: #fff; border-radius: 8px; padding: 1rem; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); opacity: 0.6;"><div style="font-size: 0.85rem; color: #666; margin-bottom: 0.5rem;">VWAP</div><div style="font-size: 1.1rem; font-weight: bold; color: #999;">Waiting...</div></div><div style="background: #fff; border-radius: 8px; padding: 1rem; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); opacity: 0.6;"><div style="font-size: 0.85rem; color: #666; margin-bottom: 0.5rem;">SUPERTREND</div><div style="font-size: 1.1rem; font-weight: bold; color: #999;">Waiting...</div></div></div><div style="background: #fff; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; box-shadow: 0 2px 4px rgba(0,0,0,0.05); opacity: 0.6;"><div style="font-size: 0.85rem; font-weight: bold; color: #333; margin-bottom: 0.75rem;">📊 Visual Stack Preview:</div><div style="font-family: monospace; font-size: 0.8rem; line-height: 1.8;"><div style="color: #999;">🟢 Candle Close: Waiting...</div><div style="color: #999;">══ VWAP: Waiting...</div><div style="color: #999;">── SuperTrend: Waiting...</div></div></div><div style="text-align: center; font-size: 0.75rem; color: #999;">⏰ Strategy will activate once market opens and sufficient candles are available</div></div>'
        return placeholder_html

    # Determine signal color and emoji
    if signal == 'BULLISH':
        signal_color = '#28a745'
        signal_bg = 'linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%)'
        signal_emoji = '🟢'
        signal_text = 'BULLISH'
    elif signal == 'BEARISH':
        signal_color = '#dc3545'
        signal_bg = 'linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%)'
        signal_emoji = '🔴'
        signal_text = 'BEARISH'
    else:
        signal_color = '#ffc107'
        signal_bg = 'linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%)'
        signal_emoji = '🟡'
        signal_text = 'NEUTRAL'

    # SuperTrend color
    st_color = '#28a745' if supertrend_trend == 'green' else '#dc3545'
    st_text = '🟢 GREEN' if supertrend_trend == 'green' else '🔴 RED'

    # Candle info
    candle_close = last_candle['close'] if last_candle else ltp
    candle_open = last_candle['open'] if last_candle else ltp
    is_green = candle_close > candle_open
    candle_color = '#28a745' if is_green else '#dc3545'
    candle_emoji = '🟢' if is_green else '🔴'

    # Position check
    close_vs_vwap = "Above VWAP" if candle_close > vwap else "Below VWAP"
    close_vs_vwap_icon = "✅" if (signal == 'BULLISH' and candle_close > vwap) or (signal == 'BEARISH' and candle_close < vwap) else "⚠️"

    # Visual stack
    vwap_vs_st = vwap - supertrend_value
    close_vs_vwap_diff = candle_close - vwap

    # Last updated time
    last_update = datetime.now().strftime('%H:%M:%S')

    html = f'<div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 10px; padding: 1.5rem; margin: 1rem 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);"><div style="text-align: center; font-size: 1.3rem; font-weight: bold; color: #1f77b4; margin-bottom: 1rem;">📈 VWAP & SUPERTREND STRATEGY (15-min)</div><div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 1rem;"><div style="background: {signal_bg}; border-radius: 8px; padding: 1rem; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1);"><div style="font-size: 0.85rem; color: #666; margin-bottom: 0.5rem;">SIGNAL</div><div style="font-size: 1.5rem; font-weight: bold; color: {signal_color};">{signal_emoji} {signal_text}</div></div><div style="background: #fff; border-radius: 8px; padding: 1rem; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1);"><div style="font-size: 0.85rem; color: #666; margin-bottom: 0.5rem;">VWAP</div><div style="font-size: 1.3rem; font-weight: bold; color: #333;">₹{vwap:.2f}</div></div><div style="background: #fff; border-radius: 8px; padding: 1rem; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1);"><div style="font-size: 0.85rem; color: #666; margin-bottom: 0.5rem;">SUPERTREND</div><div style="font-size: 1.3rem; font-weight: bold; color: {st_color};">₹{supertrend_value:.2f}</div><div style="font-size: 0.75rem; color: {st_color}; margin-top: 0.25rem;">{st_text}</div></div></div><div style="background: #fff; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; box-shadow: 0 2px 4px rgba(0,0,0,0.05);"><div style="font-size: 0.9rem; font-weight: bold; color: #333; margin-bottom: 0.5rem;">Last 15-min Candle: {candle_emoji} Close: ₹{candle_close:.2f}</div><div style="font-size: 0.85rem; color: #666;">Candle Position: {close_vs_vwap_icon} {close_vs_vwap} ({abs(close_vs_vwap_diff):+.2f})</div></div><div style="background: #fff; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; box-shadow: 0 2px 4px rgba(0,0,0,0.05);"><div style="font-size: 0.85rem; font-weight: bold; color: #333; margin-bottom: 0.75rem;">📊 Visual Stack:</div><div style="font-family: monospace; font-size: 0.8rem; line-height: 1.8;"><div style="color: {candle_color};">🟢 Candle Close: ₹{candle_close:.2f}</div><div style="color: #1f77b4;">══ VWAP: ₹{vwap:.2f} ({vwap_vs_st:+.2f} vs ST)</div><div style="color: {st_color};">── SuperTrend: ₹{supertrend_value:.2f} ({st_text})</div></div></div><div style="text-align: center; font-size: 0.75rem; color: #999;">⏰ Last Updated: {last_update}</div></div>'

    return html

# ============================================
# MOMENTUM STOCKS TRACKING FUNCTIONS
# ============================================

def get_stock_weekly_ohlc(stock_name):
    """
    Fetch current week's OHLC for a stock (from Monday/start of week to now)
    Returns: (high, low, close) or (None, None, None)
    """
    try:
        # Get stock futures token
        fut_rows = engine.token_meta[
            (engine.token_meta["name"] == stock_name) &
            (engine.token_meta.get("type") == "FUT") &
            (engine.token_meta.get("category") == "STOCK")
        ]

        if fut_rows.empty:
            return None, None, None

        fut_token = int(fut_rows.iloc[0]["instrument_token"])

        # Get start of current week (Monday)
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())  # Monday
        start_of_week = start_of_week.replace(hour=9, minute=15, second=0, microsecond=0)

        # Fetch weekly candle data
        weekly_data = engine.kite.historical_data(
            instrument_token=fut_token,
            from_date=start_of_week,
            to_date=today,
            interval="week"
        )

        if weekly_data and len(weekly_data) > 0:
            current_week = weekly_data[-1]
            return current_week['high'], current_week['low'], current_week['close']

        return None, None, None

    except Exception as e:
        # print(f"Error fetching weekly OHLC for {stock_name}: {e}")
        return None, None, None

def get_stock_daily_ohlc(stock_name):
    """
    Fetch today's OHLC for a stock (from 9:15 AM to now)
    Returns: (high, low, close) or (None, None, None)
    """
    try:
        # Get stock futures token
        fut_rows = engine.token_meta[
            (engine.token_meta["name"] == stock_name) &
            (engine.token_meta.get("type") == "FUT") &
            (engine.token_meta.get("category") == "STOCK")
        ]

        if fut_rows.empty:
            return None, None, None

        fut_token = int(fut_rows.iloc[0]["instrument_token"])

        # Get today's start (9:15 AM)
        today = datetime.now()
        today_start = today.replace(hour=9, minute=15, second=0, microsecond=0)

        # Fetch daily candle data
        daily_data = engine.kite.historical_data(
            instrument_token=fut_token,
            from_date=today_start,
            to_date=today,
            interval="day"
        )

        if daily_data and len(daily_data) > 0:
            today_candle = daily_data[-1]
            return today_candle['high'], today_candle['low'], today_candle['close']

        return None, None, None

    except Exception as e:
        # print(f"Error fetching daily OHLC for {stock_name}: {e}")
        return None, None, None

def check_momentum_conditions(stock_name, ltp):
    """
    Check if stock meets bullish or bearish momentum conditions

    Bullish: Weekly Close = Weekly High AND Daily Close = Daily High
    Bearish: Weekly Close = Weekly Low AND Daily Close = Daily Low

    Returns: ('BULLISH', 'BEARISH', or None)
    """
    try:
        # Fetch weekly and daily OHLC
        weekly_high, weekly_low, weekly_close = get_stock_weekly_ohlc(stock_name)
        daily_high, daily_low, daily_close = get_stock_daily_ohlc(stock_name)

        if None in [weekly_high, weekly_low, weekly_close, daily_high, daily_low, daily_close]:
            return None

        # Use LTP as current close
        current_close = ltp

        # Check BULLISH conditions (exact match)
        if (current_close == weekly_high and
            current_close == daily_high and
            weekly_close == weekly_high and
            daily_close == daily_high):
            return 'BULLISH'

        # Check BEARISH conditions (exact match)
        if (current_close == weekly_low and
            current_close == daily_low and
            weekly_close == weekly_low and
            daily_close == daily_low):
            return 'BEARISH'

        return None

    except Exception as e:
        # print(f"Error checking momentum for {stock_name}: {e}")
        return None

def load_momentum_tracking():
    """
    Load today's momentum tracking from CSV
    Returns: dict with structure {stock_name: {'bullish': count, 'bearish': count}}
    """
    try:
        today = datetime.now().date()
        momentum_file = HISTORICAL_DIR / f"momentum_{today}.csv"

        if not momentum_file.exists():
            return {}

        import csv
        tracking = {}

        with open(momentum_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                stock_name = row['stock_name']
                tracking[stock_name] = {
                    'bullish': int(row.get('bullish_count', 0)),
                    'bearish': int(row.get('bearish_count', 0))
                }

        return tracking

    except Exception as e:
        print(f"Error loading momentum tracking: {e}")
        return {}

def save_momentum_tracking(tracking):
    """
    Save momentum tracking to today's CSV file
    tracking: dict with structure {stock_name: {'bullish': count, 'bearish': count}}
    """
    try:
        today = datetime.now().date()
        HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)
        momentum_file = HISTORICAL_DIR / f"momentum_{today}.csv"

        import csv

        with open(momentum_file, 'w', newline='') as f:
            fieldnames = ['stock_name', 'bullish_count', 'bearish_count', 'last_updated']
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            writer.writeheader()
            for stock_name, counts in tracking.items():
                writer.writerow({
                    'stock_name': stock_name,
                    'bullish_count': counts['bullish'],
                    'bearish_count': counts['bearish'],
                    'last_updated': datetime.now().isoformat()
                })

        print(f"✅ Momentum tracking saved: {len(tracking)} stocks")

    except Exception as e:
        print(f"Error saving momentum tracking: {e}")

# ============================================
# SMART SCORING & ALERT SYSTEM
# ============================================

def calculate_stock_score(stock_name, top_10_stocks, volume_spikes, momentum_tracking, stocks_data):
    """
    Calculate smart score for a stock based on confluence across 3 lists

    Returns: {
        'total_score': int,
        'breakdown': {
            'top10_score': int,
            'volume_score': int,
            'momentum_score': int,
            'confluence_bonus': int
        },
        'signal_strength': str,
        'lists_present': list,
        'stock_data': dict
    }
    """
    score_breakdown = {
        'top10_score': 0,
        'volume_score': 0,
        'momentum_score': 0,
        'confluence_bonus': 0
    }
    lists_present = []

    # 1. Check Top 10 Stocks (by Net Flow)
    top10_scores = {1: 30, 2: 25, 3: 25, 4: 20, 5: 20, 6: 15, 7: 15, 8: 10, 9: 10, 10: 10}
    for rank, (name, data) in enumerate(top_10_stocks, 1):
        if name == stock_name:
            score_breakdown['top10_score'] = top10_scores.get(rank, 10)
            lists_present.append('Top 10 Stocks')
            break

    # 2. Check Volume Spikes (by Total Activity)
    volume_scores = {1: 30, 2: 25, 3: 25, 4: 20, 5: 20, 6: 15, 7: 15, 8: 10, 9: 10, 10: 10}
    for rank, (name, data) in enumerate(volume_spikes, 1):
        if name == stock_name:
            score_breakdown['volume_score'] = volume_scores.get(rank, 10)
            lists_present.append('Volume Spikes')
            break

    # 3. Check Momentum Stocks
    if stock_name in momentum_tracking:
        bullish_count = momentum_tracking[stock_name].get('bullish', 0)
        bearish_count = momentum_tracking[stock_name].get('bearish', 0)
        max_count = max(bullish_count, bearish_count)

        if max_count >= 5:
            score_breakdown['momentum_score'] = 30
        elif max_count >= 3:
            score_breakdown['momentum_score'] = 25
        elif max_count == 2:
            score_breakdown['momentum_score'] = 20
        elif max_count == 1:
            score_breakdown['momentum_score'] = 15

        if max_count > 0:
            lists_present.append('Momentum')

    # 4. Calculate Confluence Bonus
    num_lists = len(lists_present)
    if num_lists == 3:
        score_breakdown['confluence_bonus'] = 50  # ALL 3 LISTS!
    elif num_lists == 2:
        score_breakdown['confluence_bonus'] = 20  # 2 LISTS

    # 5. Calculate Total Score
    total_score = (score_breakdown['top10_score'] +
                   score_breakdown['volume_score'] +
                   score_breakdown['momentum_score'] +
                   score_breakdown['confluence_bonus'])

    # 6. Determine Signal Strength
    if total_score >= 100:
        signal_strength = '🚨🔥 SUPER STRONG'
    elif total_score >= 70:
        signal_strength = '⚡💪 VERY STRONG'
    elif total_score >= 50:
        signal_strength = '💪 STRONG'
    else:
        signal_strength = '✅ GOOD'

    # 7. Get stock data
    stock_data = stocks_data.get(stock_name, {})

    return {
        'total_score': total_score,
        'breakdown': score_breakdown,
        'signal_strength': signal_strength,
        'lists_present': lists_present,
        'stock_data': stock_data,
        'num_lists': num_lists
    }

def calculate_entry_exit_levels(stock_price, change_pct, signal_strength, net_flow):
    """
    Calculate entry/exit levels based on signal strength and price action

    Returns: {
        'entry': float,
        'target': float,
        'stop_loss': float,
        'risk_reward': str
    }
    """
    if stock_price is None:
        return None

    # Determine direction
    is_bullish = net_flow > 0

    # Calculate levels based on signal strength and price
    if signal_strength == '🚨🔥 SUPER STRONG':
        # Aggressive levels for super strong signals
        sl_percent = 1.0  # 1% stop loss
        target_percent = 3.0 if is_bullish else -3.0  # 3% target
    elif signal_strength == '⚡💪 VERY STRONG':
        sl_percent = 1.2  # 1.2% stop loss
        target_percent = 2.5 if is_bullish else -2.5  # 2.5% target
    else:  # STRONG
        sl_percent = 1.5  # 1.5% stop loss
        target_percent = 2.0 if is_bullish else -2.0  # 2% target

    if is_bullish:
        entry = stock_price
        target = stock_price * (1 + target_percent / 100)
        stop_loss = stock_price * (1 - sl_percent / 100)
    else:
        entry = stock_price
        target = stock_price * (1 + target_percent / 100)  # Lower for bearish
        stop_loss = stock_price * (1 + sl_percent / 100)  # Higher for bearish

    # Calculate risk-reward ratio
    risk = abs(entry - stop_loss)
    reward = abs(target - entry)
    rr_ratio = reward / risk if risk > 0 else 0

    return {
        'entry': entry,
        'target': target,
        'stop_loss': stop_loss,
        'risk_reward': f"1:{rr_ratio:.1f}"
    }

def create_smart_alert_message(stock_name, score_result, momentum_data, volume_spike_data, top10_rank):
    """
    Create comprehensive Telegram alert message with scoring and levels
    """
    stock_data = score_result['stock_data']
    breakdown = score_result['breakdown']

    price = stock_data.get('price')
    change_pct = stock_data.get('change_pct')
    net_flow = stock_data.get('net_flow', 0)

    if price is None:
        return None

    # Price formatting
    change_emoji = "🟢" if change_pct and change_pct > 0 else "🔴" if change_pct and change_pct < 0 else "⚪"
    change_str = f"{change_pct:+.2f}%" if change_pct is not None else "N/A"

    # Direction
    direction = "BULLISH" if net_flow > 0 else "BEARISH"
    direction_emoji = "🟢" if net_flow > 0 else "🔴"

    # Calculate entry/exit levels
    levels = calculate_entry_exit_levels(price, change_pct, score_result['signal_strength'], net_flow)

    # Build message
    message = f"<b>{score_result['signal_strength']} SIGNAL (Score: {score_result['total_score']}/140)</b>\n\n"
    message += f"<b>{stock_name}</b> - ₹{price:,.2f} {change_emoji} {change_str}\n\n"

    # List presence with scores
    if breakdown['top10_score'] > 0:
        message += f"✅ Top 10 Stocks: #{top10_rank} ({breakdown['top10_score']} pts)\n"
    else:
        message += f"❌ Top 10 Stocks: Not in list (0 pts)\n"

    if breakdown['volume_score'] > 0:
        vol_rank = "N/A"  # Will be filled by caller
        message += f"✅ Volume Spikes: #{vol_rank} ({breakdown['volume_score']} pts)\n"
    else:
        message += f"❌ Volume Spikes: Not in list (0 pts)\n"

    if breakdown['momentum_score'] > 0:
        bullish_count = momentum_data.get('bullish', 0)
        bearish_count = momentum_data.get('bearish', 0)
        mom_type = "Bullish" if bullish_count > bearish_count else "Bearish"
        mom_count = max(bullish_count, bearish_count)
        message += f"✅ Momentum: {mom_type}({mom_count}) ({breakdown['momentum_score']} pts)\n"
    else:
        message += f"❌ Momentum: Not in list (0 pts)\n"

    # Confluence bonus
    if score_result['num_lists'] == 3:
        message += f"🎯 <b>Confluence Bonus: +{breakdown['confluence_bonus']} pts (ALL 3 LISTS!)</b>\n\n"
    elif score_result['num_lists'] == 2:
        message += f"🎯 Confluence Bonus: +{breakdown['confluence_bonus']} pts (2 LISTS)\n\n"
    else:
        message += f"\n"

    # Analysis section
    message += f"📊 <b>Analysis:</b>\n"
    message += f"• Direction: {direction_emoji} <b>{direction}</b>\n"
    message += f"• Net Flow: {net_flow:+,.0f}\n"

    if volume_spike_data:
        ce_flow = volume_spike_data.get('ce_flow', 0)
        pe_flow = volume_spike_data.get('pe_flow', 0)
        total_vol = ce_flow + pe_flow
        message += f"• Total Volume: {total_vol:,.0f} (CE: {ce_flow:,.0f}, PE: {pe_flow:,.0f})\n"

    # Entry/Exit Levels
    if levels:
        message += f"\n💰 <b>Trade Levels:</b>\n"
        message += f"• Entry: ₹{levels['entry']:,.2f}\n"
        message += f"• Target: ₹{levels['target']:,.2f}\n"
        message += f"• Stop Loss: ₹{levels['stop_loss']:,.2f}\n"
        message += f"• Risk:Reward = {levels['risk_reward']}\n"

    # Recommendation
    message += f"\n💡 <b>Recommendation:</b> "
    if score_result['total_score'] >= 100:
        message += f"SUPER STRONG {direction} SIGNAL\n"
        message += f"High conviction trade setup. Consider immediate action.\n"
    elif score_result['total_score'] >= 70:
        message += f"VERY STRONG {direction} SIGNAL\n"
        message += f"Strong setup with good confluence. Recommended trade.\n"
    else:
        message += f"STRONG {direction} SIGNAL\n"
        message += f"Good setup. Wait for confirmation or scale in.\n"

    # Hashtags
    hashtag_strength = score_result['signal_strength'].split()[0].replace('🚨🔥', 'SuperStrong').replace('⚡💪', 'VeryStrong').replace('💪', 'Strong')
    message += f"\n#{hashtag_strength} #{stock_name} #{direction}"

    return message

def generate_daily_summary(all_scores, stocks_data):
    """
    Generate end-of-day summary of top scoring stocks
    """
    if not all_scores:
        return None

    # Sort by score
    sorted_scores = sorted(all_scores, key=lambda x: x['score'], reverse=True)[:5]

    current_time = datetime.now().strftime('%I:%M %p')

    message = f"<b>📊 DAILY SUMMARY - {datetime.now().strftime('%d %b %Y')}</b>\n"
    message += f"<b>Market Close Report - {current_time}</b>\n\n"
    message += f"<b>🏆 TOP 5 HIGH-SCORING STOCKS TODAY:</b>\n\n"

    for i, score_data in enumerate(sorted_scores, 1):
        stock_name = score_data['stock_name']
        total_score = score_data['score']
        signal_strength = score_data['signal_strength']

        stock_info = stocks_data.get(stock_name, {})
        price = stock_info.get('price')
        change_pct = stock_info.get('change_pct')
        net_flow = stock_info.get('net_flow', 0)

        change_emoji = "🟢" if change_pct and change_pct > 0 else "🔴"
        change_str = f"{change_pct:+.2f}%" if change_pct is not None else "N/A"
        direction = "Bullish" if net_flow > 0 else "Bearish"

        message += f"<b>{i}. {stock_name}</b> - Score: {total_score}/140\n"
        message += f"   {signal_strength}\n"
        message += f"   ₹{price:,.2f} {change_emoji} {change_str} | {direction}\n"
        message += f"   Lists: {score_data['num_lists']}/3\n\n"

    message += f"<b>Market Statistics:</b>\n"
    message += f"• Total stocks analyzed: {len(stocks_data)}\n"
    message += f"• Stocks with score ≥50: {len([s for s in all_scores if s['score'] >= 50])}\n"
    message += f"• Triple confluence: {len([s for s in all_scores if s['num_lists'] == 3])}\n\n"

    message += f"#DailySummary #MarketClose #TopScorers"

    return message

# =========================
# NIFTY MOMENTUM SCORING SYSTEM
# =========================

def calculate_nifty_momentum_score(indices_data, stocks_data, volume_state, vwap_st_strategy):
    """
    Calculate comprehensive NIFTY momentum score (0-100 scale, can be negative)
    Combines multiple parameters for precise market momentum classification

    Returns: {
        'total_score': int (-100 to +100),
        'breakdown': dict of individual scores,
        'momentum_class': str (STRONG BULLISH, BULLISH, SIDEWAYS, BEARISH, STRONG BEARISH),
        'confidence': str (HIGH, MEDIUM, LOW)
    }
    """
    score_breakdown = {
        'ce_pe_flow': 0,          # 10 points
        'session_spikes': 0,      # 15 points
        'ce_pe_race': 0,          # 10 points
        'live_sentiment': 0,      # 10 points
        'nifty_net_flow': 0,      # 10 points
        'indices_net_flow': 0,    # 10 points
        'indices_performance': 0, # 10 points
        'vwap_supertrend': 0,     # 15 points
        'stocks_performance': 0   # 10 points
    }

    # 1. CE/PE Flow Ratio (10 points)
    nifty_data = indices_data.get('NIFTY', {})
    ce_flow = nifty_data.get('ce_flow', 0)
    pe_flow = nifty_data.get('pe_flow', 0)

    if ce_flow > pe_flow:
        score_breakdown['ce_pe_flow'] = 10
    elif pe_flow > ce_flow:
        score_breakdown['ce_pe_flow'] = -10

    # 2. Session Summary - Spikes (15 points)
    # Check spike queue for CE vs PE spikes since 9:15 AM
    ce_spikes = 0
    pe_spikes = 0
    ce_total_vol = 0
    pe_total_vol = 0
    ce_largest = 0
    pe_largest = 0

    if hasattr(volume_state, 'spike_queue') and volume_state.spike_queue:
        for spike in volume_state.spike_queue:
            if spike.option_type == 'CE':
                ce_spikes += 1
                ce_total_vol += spike.volume
                ce_largest = max(ce_largest, spike.spike_ratio)
            elif spike.option_type == 'PE':
                pe_spikes += 1
                pe_total_vol += spike.volume
                pe_largest = max(pe_largest, spike.spike_ratio)

    # CE vs PE spike analysis
    spike_score = 0
    if ce_spikes > pe_spikes:
        spike_score += 4
    elif pe_spikes > ce_spikes:
        spike_score -= 4

    if ce_total_vol > pe_total_vol:
        spike_score += 4
    elif pe_total_vol > ce_total_vol:
        spike_score -= 4

    # Average volume
    ce_avg_vol = ce_total_vol / ce_spikes if ce_spikes > 0 else 0
    pe_avg_vol = pe_total_vol / pe_spikes if pe_spikes > 0 else 0
    if ce_avg_vol > pe_avg_vol:
        spike_score += 4
    elif pe_avg_vol > ce_avg_vol:
        spike_score -= 4

    if ce_largest > pe_largest:
        spike_score += 3
    elif pe_largest > ce_largest:
        spike_score -= 3

    score_breakdown['session_spikes'] = spike_score

    # 3. CE vs PE Race (10 points)
    race_data = create_ce_pe_race_chart()
    if race_data:
        if race_data['bias'] == 'BULLISH':
            score_breakdown['ce_pe_race'] = 10
        elif race_data['bias'] == 'BEARISH':
            score_breakdown['ce_pe_race'] = -10

    # 4. Live Momentum Tracker Sentiment (10 points)
    # Get from composite score calculation
    total_indices_ce = sum(d.get("ce_flow", 0) for d in indices_data.values())
    total_indices_pe = sum(d.get("pe_flow", 0) for d in indices_data.values())
    total_stocks_ce = sum(d.get("ce_flow", 0) for d in stocks_data.values())
    total_stocks_pe = sum(d.get("pe_flow", 0) for d in stocks_data.values())
    total_ce = total_indices_ce + total_stocks_ce
    total_pe = total_indices_pe + total_stocks_pe
    net_flow = total_ce - total_pe

    if abs(net_flow) < 10000:
        score_breakdown['live_sentiment'] = 0  # Sideways
    elif net_flow > 0:
        composite_score = min(100, 50 + (net_flow / 1000))
        if composite_score > 65:
            score_breakdown['live_sentiment'] = 10  # Bullish
        else:
            score_breakdown['live_sentiment'] = 5   # Mild Bullish
    else:
        composite_score = max(0, 50 - (abs(net_flow) / 1000))
        if composite_score < 35:
            score_breakdown['live_sentiment'] = -10  # Bearish
        else:
            score_breakdown['live_sentiment'] = -5   # Mild Bearish

    # 5. NIFTY Net Flow (10 points)
    nifty_net = nifty_data.get('net_flow', 0)
    if nifty_net > 100000:
        score_breakdown['nifty_net_flow'] = 10
    elif nifty_net > 50000:
        score_breakdown['nifty_net_flow'] = 7
    elif nifty_net > 0:
        score_breakdown['nifty_net_flow'] = 3
    elif nifty_net < -100000:
        score_breakdown['nifty_net_flow'] = -10
    elif nifty_net < -50000:
        score_breakdown['nifty_net_flow'] = -7
    elif nifty_net < 0:
        score_breakdown['nifty_net_flow'] = -3

    # 6. Other Indices Net Flow (10 points)
    indices_positive = 0
    indices_negative = 0
    for idx_name, idx_data in indices_data.items():
        if idx_name != 'NIFTY':
            idx_net = idx_data.get('net_flow', 0)
            if idx_net > 0:
                indices_positive += 1
            elif idx_net < 0:
                indices_negative += 1

    total_other_indices = indices_positive + indices_negative
    if total_other_indices > 0:
        positive_pct = (indices_positive / total_other_indices) * 100
        if positive_pct > 70:
            score_breakdown['indices_net_flow'] = 10
        elif positive_pct > 60:
            score_breakdown['indices_net_flow'] = 7
        elif positive_pct > 50:
            score_breakdown['indices_net_flow'] = 3
        elif positive_pct < 30:
            score_breakdown['indices_net_flow'] = -10
        elif positive_pct < 40:
            score_breakdown['indices_net_flow'] = -7
        elif positive_pct < 50:
            score_breakdown['indices_net_flow'] = -3

    # 7. Indices-Wide Performance (% change) (10 points)
    indices_up = 0
    indices_down = 0
    for idx_name, idx_data in indices_data.items():
        change_pct = idx_data.get('change_pct')
        if change_pct is not None:
            if change_pct > 0:
                indices_up += 1
            elif change_pct < 0:
                indices_down += 1

    total_indices = indices_up + indices_down
    if total_indices > 0:
        up_pct = (indices_up / total_indices) * 100
        if up_pct > 60:
            score_breakdown['indices_performance'] = 10
        elif up_pct > 50:
            score_breakdown['indices_performance'] = 5
        elif up_pct < 40:
            score_breakdown['indices_performance'] = -10
        elif up_pct < 50:
            score_breakdown['indices_performance'] = -5

    # 8. VWAP & SuperTrend Strategy (15 points)
    if vwap_st_strategy:
        signal = vwap_st_strategy.get('signal', 'NEUTRAL')
        if signal == 'BULLISH':
            score_breakdown['vwap_supertrend'] = 15
        elif signal == 'BEARISH':
            score_breakdown['vwap_supertrend'] = -15

    # 9. Market-Wide Stock Performance (10 points)
    stocks_up = 0
    stocks_down = 0
    for stock_name, stock_data in stocks_data.items():
        change_pct = stock_data.get('change_pct')
        if change_pct is not None:
            if change_pct > 0:
                stocks_up += 1
            elif change_pct < 0:
                stocks_down += 1

    total_stocks = stocks_up + stocks_down
    if total_stocks > 0:
        stocks_up_pct = (stocks_up / total_stocks) * 100
        if stocks_up_pct > 65:
            score_breakdown['stocks_performance'] = 10
        elif stocks_up_pct > 55:
            score_breakdown['stocks_performance'] = 7
        elif stocks_up_pct > 50:
            score_breakdown['stocks_performance'] = 3
        elif stocks_up_pct < 35:
            score_breakdown['stocks_performance'] = -10
        elif stocks_up_pct < 45:
            score_breakdown['stocks_performance'] = -7
        elif stocks_up_pct < 50:
            score_breakdown['stocks_performance'] = -3

    # Calculate total score
    total_score = sum(score_breakdown.values())

    # Classify momentum
    if total_score >= 70:
        momentum_class = 'STRONG BULLISH'
        confidence = 'HIGH'
    elif total_score >= 40:
        momentum_class = 'BULLISH'
        confidence = 'MEDIUM' if total_score >= 55 else 'LOW'
    elif total_score > -40:
        momentum_class = 'SIDEWAYS'
        confidence = 'LOW'
    elif total_score > -70:
        momentum_class = 'BEARISH'
        confidence = 'MEDIUM' if total_score <= -55 else 'LOW'
    else:
        momentum_class = 'STRONG BEARISH'
        confidence = 'HIGH'

    return {
        'total_score': total_score,
        'breakdown': score_breakdown,
        'momentum_class': momentum_class,
        'confidence': confidence,
        'nifty_price': nifty_data.get('price'),
        'nifty_change_pct': nifty_data.get('change_pct'),
        'stocks_up_pct': (stocks_up / total_stocks * 100) if total_stocks > 0 else 0,
        'indices_up_pct': (indices_up / total_indices * 100) if total_indices > 0 else 0
    }

def create_nifty_momentum_alert(score_result, is_reversal=False, previous_class=None):
    """
    Create comprehensive NIFTY momentum alert message
    """
    momentum_class = score_result['momentum_class']
    total_score = score_result['total_score']
    confidence = score_result['confidence']
    breakdown = score_result['breakdown']
    nifty_price = score_result['nifty_price']
    nifty_change_pct = score_result['nifty_change_pct']

    # Emoji based on momentum
    if 'STRONG BULLISH' in momentum_class:
        emoji = '🚀🟢'
        color = 'GREEN'
    elif 'BULLISH' in momentum_class:
        emoji = '🟢'
        color = 'GREEN'
    elif 'SIDEWAYS' in momentum_class:
        emoji = '⚪'
        color = 'YELLOW'
    elif 'STRONG BEARISH' in momentum_class:
        emoji = '📉🔴'
        color = 'RED'
    else:
        emoji = '🔴'
        color = 'RED'

    # Header
    message = ""
    if is_reversal:
        message = f"<b>🔄 NIFTY MOMENTUM REVERSAL ALERT</b>\n"
        message += f"<b>{previous_class}</b> → <b>{emoji} {momentum_class}</b>\n\n"
    else:
        message = f"<b>{emoji} NIFTY MOMENTUM ALERT</b>\n"
        message += f"<b>Status: {momentum_class}</b>\n\n"

    # Score and confidence
    message += f"📊 <b>Momentum Score: {total_score:+d}/100</b>\n"
    message += f"🎯 <b>Confidence: {confidence}</b>\n\n"

    # NIFTY price
    if nifty_price and nifty_change_pct is not None:
        change_emoji = "🟢" if nifty_change_pct > 0 else "🔴"
        message += f"💹 <b>NIFTY: ₹{nifty_price:,.2f} {change_emoji} {nifty_change_pct:+.2f}%</b>\n\n"

    # Score breakdown
    message += f"<b>📈 Score Breakdown:</b>\n"
    message += f"• CE/PE Flow: {breakdown['ce_pe_flow']:+d}/10\n"
    message += f"• Session Spikes: {breakdown['session_spikes']:+d}/15\n"
    message += f"• CE vs PE Race: {breakdown['ce_pe_race']:+d}/10\n"
    message += f"• Live Sentiment: {breakdown['live_sentiment']:+d}/10\n"
    message += f"• NIFTY Net Flow: {breakdown['nifty_net_flow']:+d}/10\n"
    message += f"• Indices Net Flow: {breakdown['indices_net_flow']:+d}/10\n"
    message += f"• Indices Performance: {breakdown['indices_performance']:+d}/10\n"
    message += f"• VWAP+SuperTrend: {breakdown['vwap_supertrend']:+d}/15\n"
    message += f"• Stocks Performance: {breakdown['stocks_performance']:+d}/10\n\n"

    # Market statistics
    message += f"<b>📊 Market Statistics:</b>\n"
    message += f"• Stocks Up: {score_result['stocks_up_pct']:.1f}%\n"
    message += f"• Indices Up: {score_result['indices_up_pct']:.1f}%\n\n"

    # Trading recommendation
    message += f"<b>💡 Trading Recommendation:</b>\n"
    if 'STRONG BULLISH' in momentum_class:
        message += f"🟢 <b>Strong Buy Signal</b>\n"
        message += f"Consider aggressive long positions. High conviction setup.\n"
        message += f"Focus on CE options with nearby strikes.\n"
    elif 'BULLISH' in momentum_class:
        message += f"🟢 <b>Buy Signal</b>\n"
        message += f"Consider long positions with proper risk management.\n"
        message += f"Watch for continuation signals.\n"
    elif 'SIDEWAYS' in momentum_class:
        message += f"⚪ <b>No Clear Direction</b>\n"
        message += f"Stay cautious. Wait for clearer signals.\n"
        message += f"Consider range-bound strategies or stay out.\n"
    elif 'STRONG BEARISH' in momentum_class:
        message += f"🔴 <b>Strong Sell Signal</b>\n"
        message += f"Consider aggressive short positions. High conviction setup.\n"
        message += f"Focus on PE options with nearby strikes.\n"
    else:
        message += f"🔴 <b>Sell Signal</b>\n"
        message += f"Consider short positions with proper risk management.\n"
        message += f"Watch for breakdown continuation.\n"

    # Timestamp and hashtags
    message += f"\n⏰ {datetime.now().strftime('%I:%M:%S %p')}\n"
    message += f"\n#{momentum_class.replace(' ', '')} #NIFTY #MomentumAlert #{confidence}Confidence"

    return message

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

# =========================
# CHARTINK GMAIL INTEGRATION
# =========================

class StockNameParser(HTMLParser):
    """HTML parser to extract stock names from Chartink email body"""
    def __init__(self):
        super().__init__()
        self.stock_names = []
        self.in_link = False

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.in_link = True

    def handle_endtag(self, tag):
        if tag == 'a':
            self.in_link = False

    def handle_data(self, data):
        if self.in_link:
            # Stock names are typically all caps and alphanumeric
            cleaned = data.strip()
            if cleaned and cleaned.isupper() and cleaned.isalnum():
                self.stock_names.append(cleaned)

def connect_gmail():
    """Connect to Gmail via IMAP using credentials from .env"""
    gmail_user = os.getenv('GMAIL_USER')
    gmail_password = os.getenv('GMAIL_APP_PASSWORD')

    if not gmail_user or not gmail_password:
        print("❌ Gmail credentials not found in .env file")
        print("   Required: GMAIL_USER and GMAIL_APP_PASSWORD")
        return None

    try:
        # Connect to Gmail via IMAP SSL
        mail = imaplib.IMAP4_SSL('imap.gmail.com', 993)
        mail.login(gmail_user, gmail_password)
        print(f"✅ Connected to Gmail: {gmail_user}")
        return mail
    except Exception as e:
        print(f"❌ Gmail connection failed: {e}")
        return None

def classify_alert_direction(subject):
    """
    Classify alert direction based on subject (case-insensitive)

    Returns:
        'LONG' if bullish (Weekly close=high)
        'SHORT' if bearish (Weekly close=low)
        None if not a momentum alert
    """
    subject_lower = subject.lower()

    if 'weekly close=high' in subject_lower:
        return 'LONG'
    elif 'weekly close=low' in subject_lower:
        return 'SHORT'
    else:
        return None

def parse_chartink_email(msg):
    """
    Parse Chartink email to extract stock names and metadata

    Returns:
        {
            'stocks': [list of stock names],
            'subject': email subject,
            'date': email date,
            'direction': 'LONG' or 'SHORT' or None
        }
    """
    result = {
        'stocks': [],
        'subject': '',
        'date': '',
        'direction': None
    }

    # Get subject
    subject = msg.get('Subject', '')
    if subject:
        # Decode if needed
        decoded = decode_header(subject)
        subject = ''.join([
            part.decode(encoding or 'utf-8') if isinstance(part, bytes) else part
            for part, encoding in decoded
        ])
    result['subject'] = subject

    # Get date
    result['date'] = msg.get('Date', '')

    # Classify direction
    result['direction'] = classify_alert_direction(subject)

    # Parse email body for stock names
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == 'text/html':
                try:
                    html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    parser = StockNameParser()
                    parser.feed(html_body)
                    result['stocks'] = parser.stock_names
                    break
                except Exception as e:
                    print(f"⚠️ Error parsing HTML: {e}")
    else:
        # Single part message
        try:
            html_body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            parser = StockNameParser()
            parser.feed(html_body)
            result['stocks'] = parser.stock_names
        except Exception as e:
            print(f"⚠️ Error parsing HTML: {e}")

    return result

def fetch_chartink_alerts(mode='LIVE'):
    """
    Fetch and parse Chartink momentum alerts from Gmail

    Args:
        mode: 'LIVE' or 'TEST'

    LIVE mode:
        - Fetches only UNSEEN emails
        - Marks processed emails as SEEN
        - For real-time alert processing during market hours

    TEST mode:
        - Fetches emails from last 30 days
        - Does NOT mark as seen
        - For debugging/replaying historical alerts

    Returns:
        List of parsed alerts with structure:
        [
            {
                'stocks': ['STOCK1', 'STOCK2'],
                'subject': 'Alert for Weekly close=high',
                'date': 'Wed, Dec 24, 9:16 AM',
                'direction': 'LONG' or 'SHORT',
                'timestamp': datetime object
            },
            ...
        ]
    """
    # Create debug log file
    debug_dir = Path(r'D:\Stocks Analysis\Apex Nifty Trading\Logs')
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_file = debug_dir / f"chartink_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    def log_debug(message):
        """Write to both console and debug file"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] {message}"
        print(log_msg)
        try:
            with open(debug_file, 'a', encoding='utf-8') as f:
                f.write(log_msg + '\n')
        except Exception as e:
            print(f"Failed to write to debug file: {e}")

    log_debug("="*80)
    log_debug(f"CHARTINK GMAIL INTEGRATION - {mode} MODE")
    log_debug("="*80)

    # Check credentials
    gmail_user = os.getenv('GMAIL_USER')
    gmail_password = os.getenv('GMAIL_APP_PASSWORD')

    log_debug(f"Gmail User: {gmail_user if gmail_user else 'NOT SET'}")
    log_debug(f"Gmail Password: {'SET (length={})'.format(len(gmail_password)) if gmail_password else 'NOT SET'}")

    if not gmail_user or not gmail_password:
        log_debug("❌ FAILED: Gmail credentials not found in .env file")
        log_debug("Required: GMAIL_USER and GMAIL_APP_PASSWORD")
        return []

    # Connect to Gmail
    log_debug("\n--- Connecting to Gmail ---")
    mail = connect_gmail()
    if not mail:
        log_debug("❌ FAILED: Could not connect to Gmail")
        return []

    log_debug("✅ Connected to Gmail successfully")

    alerts = []

    try:
        # Select inbox
        log_debug("\n--- Selecting INBOX ---")
        status, data = mail.select('INBOX')
        log_debug(f"Select status: {status}")
        log_debug(f"Mailbox data: {data}")

        # Build search criteria based on mode
        # IMPORTANT: Filter by SUBJECT at IMAP level (not in Python)
        if mode == 'LIVE':
            # LIVE: Only unseen emails with specific subjects
            search_criteria_high = '(UNSEEN FROM "Chartink" SUBJECT "Weekly close=high")'
            search_criteria_low = '(UNSEEN FROM "Chartink" SUBJECT "Weekly close=low")'
            log_debug(f"\n🔴 LIVE MODE: Searching for UNSEEN momentum alerts (high/low)...")
        else:  # TEST mode
            # TEST: Last 30 days, matching specific subjects only
            since_date = (datetime.now() - timedelta(days=30)).strftime("%d-%b-%Y")
            search_criteria_high = f'(SINCE {since_date} FROM "Chartink" SUBJECT "Weekly close=high")'
            search_criteria_low = f'(SINCE {since_date} FROM "Chartink" SUBJECT "Weekly close=low")'
            log_debug(f"\n🧪 TEST MODE: Searching for momentum alerts (high/low) since {since_date}...")

        log_debug(f"Search criteria HIGH: {search_criteria_high}")
        log_debug(f"Search criteria LOW: {search_criteria_low}")

        # Search emails - TWO searches (one for high, one for low)
        log_debug("\n--- Searching emails ---")

        # Search for "Weekly close=high"
        status_high, message_ids_high = mail.search(None, search_criteria_high)
        log_debug(f"Search HIGH status: {status_high}")
        email_ids_high = message_ids_high[0].split() if status_high == 'OK' else []
        log_debug(f"📬 Found {len(email_ids_high)} 'Weekly close=high' emails")

        # Search for "Weekly close=low"
        status_low, message_ids_low = mail.search(None, search_criteria_low)
        log_debug(f"Search LOW status: {status_low}")
        email_ids_low = message_ids_low[0].split() if status_low == 'OK' else []
        log_debug(f"📬 Found {len(email_ids_low)} 'Weekly close=low' emails")

        # Combine results (remove duplicates)
        email_ids = list(set(email_ids_high + email_ids_low))
        log_debug(f"📬 Total momentum alerts: {len(email_ids)}")
        log_debug(f"Email IDs: {email_ids}")

        if len(email_ids) == 0:
            log_debug("\n⚠️ No emails found matching criteria")
            log_debug("Possible reasons:")
            log_debug("  1. No Chartink emails in last 30 days")
            log_debug("  2. All emails already read (in LIVE mode)")
            log_debug("  3. Sender name in Gmail is different (not 'Chartink')")

            # Try broader search to debug
            log_debug("\n--- Trying broader search (all Chartink emails) ---")
            status2, message_ids2 = mail.search(None, 'FROM "Chartink"')
            email_ids2 = message_ids2[0].split()
            log_debug(f"Total Chartink emails (all time): {len(email_ids2)}")

            if len(email_ids2) > 0:
                log_debug("Found Chartink emails! Issue might be:")
                log_debug("  - In LIVE mode: All emails already marked as READ")
                log_debug("  - In TEST mode: No emails in last 30 days")
            else:
                log_debug("No Chartink emails found at all!")
                log_debug("Possible issues:")
                log_debug("  - Sender name might be different (check actual sender)")
                log_debug("  - Wrong Gmail account")
                log_debug("  - No Chartink alerts received yet")

        # Process each email
        log_debug("\n--- Processing emails ---")
        for idx, email_id in enumerate(email_ids, 1):
            try:
                log_debug(f"\n[Email {idx}/{len(email_ids)}] Processing ID: {email_id}")

                # Fetch email
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                log_debug(f"  Fetch status: {status}")

                if status != 'OK':
                    log_debug(f"  ⚠️ Failed to fetch email")
                    continue

                # Parse email
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Get subject and sender for debugging
                subject = msg.get('Subject', '')
                sender = msg.get('From', '')
                date = msg.get('Date', '')

                log_debug(f"  From: {sender}")
                log_debug(f"  Subject: {subject}")
                log_debug(f"  Date: {date}")

                # Parse Chartink email
                parsed = parse_chartink_email(msg)
                log_debug(f"  Parsed stocks: {parsed['stocks']}")
                log_debug(f"  Direction: {parsed['direction']}")

                # Safety check (should never be None since IMAP already filtered by subject)
                if parsed['direction'] is None:
                    log_debug(f"  ⚠️ WARNING: IMAP returned an email but direction is None!")
                    log_debug(f"  ⚠️ This shouldn't happen - IMAP filter may not be working correctly")
                    continue

                log_debug(f"  ✅ Momentum alert confirmed | Direction: {parsed['direction']}")

                # Add timestamp
                try:
                    parsed['timestamp'] = email.utils.parsedate_to_datetime(parsed['date'])
                except Exception as e:
                    log_debug(f"  ⚠️ Could not parse date: {e}")
                    parsed['timestamp'] = datetime.now()

                # Add to alerts list
                alerts.append(parsed)
                log_debug(f"  ✅ Alert added!")

                # Print to console
                direction_emoji = "🟢" if parsed['direction'] == 'LONG' else "🔴"
                stocks_str = ', '.join(parsed['stocks']) if parsed['stocks'] else 'None'
                summary = f"{direction_emoji} {parsed['direction']:5s} | {parsed['date'][:25]:25s} | Stocks: {stocks_str}"
                log_debug(f"  {summary}")

                # Mark as seen ONLY in LIVE mode
                if mode == 'LIVE':
                    mail.store(email_id, '+FLAGS', '\\Seen')
                    log_debug(f"  📧 Marked as SEEN (LIVE mode)")

            except Exception as e:
                log_debug(f"  ❌ Error processing email {email_id}: {e}")
                import traceback
                log_debug(f"  Traceback: {traceback.format_exc()}")
                continue

        # Close connection
        log_debug("\n--- Closing connection ---")
        mail.close()
        mail.logout()
        log_debug("✅ Connection closed")

        log_debug(f"\n{'='*80}")
        log_debug(f"SUMMARY: Processed {len(alerts)} momentum alerts")
        log_debug(f"{'='*80}")
        log_debug(f"\nDebug log saved to: {debug_file}")

        # SAVE TO JSON FILE immediately (before returning)
        # This ensures alerts persist even if page reloads before st.rerun()
        import json
        alerts_dir = Path(r'D:\Stocks Analysis\Apex Nifty Trading\Logs')
        alerts_file = alerts_dir / "chartink_alerts.json"
        try:
            # Convert datetime to string for JSON serialization
            alerts_json = []
            for alert in alerts:
                alert_copy = alert.copy()
                if 'timestamp' in alert_copy and hasattr(alert_copy['timestamp'], 'strftime'):
                    alert_copy['timestamp'] = alert_copy['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                alerts_json.append(alert_copy)

            alerts_dir.mkdir(parents=True, exist_ok=True)
            with open(alerts_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'alerts': alerts_json,
                    'last_fetch': datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'),
                    'count': len(alerts_json),
                    'mode': mode
                }, f, indent=2)
            log_debug(f"\n✅ SAVED {len(alerts)} alerts to: {alerts_file}")
        except Exception as e:
            log_debug(f"\n❌ ERROR saving JSON: {e}")
            import traceback
            log_debug(f"Traceback: {traceback.format_exc()}")

    except Exception as e:
        log_debug(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        log_debug(f"Traceback:\n{traceback.format_exc()}")
        try:
            mail.close()
            mail.logout()
        except:
            pass

    return alerts

# =========================
# TELEGRAM ALERTS
# =========================

def is_market_hours() -> bool:
    """Check if current time is within market hours (09:15 AM - 3:30 PM)"""
    now = datetime.now()
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close

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


# ============================================
# ENHANCED ALERT SYSTEM WITH PRIORITY & FILTERING
# ============================================

def add_alert_enhanced(message, alert_type="info", priority="MEDIUM", category="GENERAL", metadata=None):
    """
    Enhanced alert system with priority levels, categories, and metadata

    Priority Levels:
    - CRITICAL: Immediate action required (e.g., major breakouts, confluence signals)
    - HIGH: Important signals (e.g., volume spikes >5x, pattern matches)
    - MEDIUM: Notable events (e.g., Top 10 entries, range breaks)
    - LOW: Informational (e.g., sentiment changes)

    Categories:
    - PATTERN: AI pattern detection alerts
    - VOLUME: Volume spike alerts
    - CONFLUENCE: Triple confluence signals
    - COMPREHENSIVE: NIFTY momentum scoring
    - STOCK: Individual stock alerts
    - RANGE: Range breakout alerts
    - GENERAL: Other alerts
    """
    timestamp = datetime.now()

    # Create enhanced alert object
    alert_obj = {
        "time": timestamp.strftime("%H:%M:%S"),
        "timestamp": timestamp,
        "message": message,
        "type": alert_type,
        "priority": priority,
        "category": category,
        "metadata": metadata or {},
        "read": False
    }

    # Add to alerts queue
    alerts.appendleft(alert_obj)

    # Also save to persistent alert history
    if 'alert_history' not in st.session_state:
        st.session_state.alert_history = []

    st.session_state.alert_history.append(alert_obj)

    # Limit history to last 1000 alerts (prevent memory bloat)
    if len(st.session_state.alert_history) > 1000:
        st.session_state.alert_history = st.session_state.alert_history[-1000:]

    # Send to Telegram for CRITICAL and HIGH priority
    if priority in ["CRITICAL", "HIGH"]:
        # Add priority indicator to telegram message
        priority_emoji = {"CRITICAL": "🚨🚨🚨", "HIGH": "⚠️"}
        telegram_msg = f"{priority_emoji[priority]} <b>{priority} PRIORITY</b>\n\n{message}"

        # Apply cooldown for non-critical alerts
        if priority != "CRITICAL":
            import hashlib
            message_hash = hashlib.md5(message.encode()).hexdigest()[:8]

            now = datetime.now()
            if message_hash in engine.last_stock_alert:
                last_time = engine.last_stock_alert[message_hash]
                minutes_passed = (now - last_time).total_seconds() / 60
                if minutes_passed < 10:
                    return  # Skip telegram for repeated high-priority alerts

            engine.last_stock_alert[message_hash] = now

        send_telegram_alert(telegram_msg)


def get_alert_statistics():
    """Calculate statistics from alert history"""
    if 'alert_history' not in st.session_state or not st.session_state.alert_history:
        return {
            "total": 0,
            "by_priority": {},
            "by_category": {},
            "by_hour": {},
            "critical_count": 0,
            "high_count": 0
        }

    alerts_list = st.session_state.alert_history

    # Count by priority
    priority_counts = {}
    for alert in alerts_list:
        p = alert.get('priority', 'MEDIUM')
        priority_counts[p] = priority_counts.get(p, 0) + 1

    # Count by category
    category_counts = {}
    for alert in alerts_list:
        c = alert.get('category', 'GENERAL')
        category_counts[c] = category_counts.get(c, 0) + 1

    # Count by hour
    hour_counts = {}
    for alert in alerts_list:
        if 'timestamp' in alert and hasattr(alert['timestamp'], 'hour'):
            hour = alert['timestamp'].hour
            hour_counts[hour] = hour_counts.get(hour, 0) + 1

    return {
        "total": len(alerts_list),
        "by_priority": priority_counts,
        "by_category": category_counts,
        "by_hour": hour_counts,
        "critical_count": priority_counts.get('CRITICAL', 0),
        "high_count": priority_counts.get('HIGH', 0)
    }


def export_alerts_to_csv():
    """Export alert history to CSV file"""
    import csv
    from io import StringIO

    if 'alert_history' not in st.session_state or not st.session_state.alert_history:
        return None

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=['timestamp', 'priority', 'category', 'type', 'message'])
    writer.writeheader()

    for alert in st.session_state.alert_history:
        writer.writerow({
            'timestamp': alert.get('timestamp', '').strftime('%Y-%m-%d %H:%M:%S') if hasattr(alert.get('timestamp'), 'strftime') else str(alert.get('timestamp', '')),
            'priority': alert.get('priority', 'MEDIUM'),
            'category': alert.get('category', 'GENERAL'),
            'type': alert.get('type', 'info'),
            'message': alert.get('message', '')
        })

    return output.getvalue()


# ============================================
# WATCHLIST MANAGEMENT
# ============================================

def add_to_watchlist(stock_name):
    """Add stock to watchlist"""
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = set()

    st.session_state.watchlist.add(stock_name.upper())
    save_watchlist()


def remove_from_watchlist(stock_name):
    """Remove stock from watchlist"""
    if 'watchlist' in st.session_state and stock_name.upper() in st.session_state.watchlist:
        st.session_state.watchlist.remove(stock_name.upper())
        save_watchlist()


def get_watchlist():
    """Get current watchlist"""
    if 'watchlist' not in st.session_state:
        load_watchlist()

    return sorted(list(st.session_state.watchlist)) if 'watchlist' in st.session_state else []


def save_watchlist():
    """Save watchlist to file"""
    try:
        watchlist_file = Path('.cache/watchlist.json')
        watchlist_file.parent.mkdir(parents=True, exist_ok=True)

        import json
        with open(watchlist_file, 'w') as f:
            json.dump(list(st.session_state.watchlist), f)
    except Exception as e:
        print(f"Error saving watchlist: {e}")


def load_watchlist():
    """Load watchlist from file"""
    try:
        watchlist_file = Path('.cache/watchlist.json')
        if watchlist_file.exists():
            import json
            with open(watchlist_file, 'r') as f:
                stocks = json.load(f)
                st.session_state.watchlist = set(stocks)
        else:
            st.session_state.watchlist = set()
    except Exception as e:
        print(f"Error loading watchlist: {e}")
        st.session_state.watchlist = set()


# ============================================
# PERFORMANCE METRICS & SESSION SUMMARY
# ============================================

def get_session_metrics():
    """Calculate session performance metrics"""
    metrics = {
        "session_start": st.session_state.get('session_start_time'),
        "total_alerts": 0,
        "critical_alerts": 0,
        "patterns_detected": 0,
        "volume_spikes": 0,
        "confluence_signals": 0,
        "top10_entries": 0,
        "polls_completed": st.session_state.get('poll_count', 0),
        "uptime_minutes": 0
    }

    if 'alert_history' in st.session_state:
        metrics["total_alerts"] = len(st.session_state.alert_history)

        # Count by category
        for alert in st.session_state.alert_history:
            if alert.get('priority') == 'CRITICAL':
                metrics["critical_alerts"] += 1
            if alert.get('category') == 'PATTERN':
                metrics["patterns_detected"] += 1
            elif alert.get('category') == 'VOLUME':
                metrics["volume_spikes"] += 1
            elif alert.get('category') == 'CONFLUENCE':
                metrics["confluence_signals"] += 1
            elif alert.get('category') == 'STOCK':
                metrics["top10_entries"] += 1

    # Calculate uptime
    if metrics["session_start"]:
        uptime_seconds = (datetime.now() - metrics["session_start"]).total_seconds()
        metrics["uptime_minutes"] = int(uptime_seconds / 60)

    return metrics


def generate_session_summary():
    """Generate comprehensive session summary report"""
    metrics = get_session_metrics()
    stats = get_alert_statistics()

    summary = []
    summary.append("=" * 60)
    summary.append("📊 SESSION SUMMARY REPORT")
    summary.append("=" * 60)
    summary.append("")

    # Session info
    if metrics["session_start"]:
        summary.append(f"🕒 Session Start: {metrics['session_start'].strftime('%I:%M:%S %p')}")
        summary.append(f"⏱️ Uptime: {metrics['uptime_minutes']} minutes")
    summary.append(f"🔄 Polls Completed: {metrics['polls_completed']}")
    summary.append("")

    # Alert summary
    summary.append("🚨 ALERTS SUMMARY:")
    summary.append(f"   Total Alerts: {stats['total']}")
    summary.append(f"   Critical: {stats['critical_count']}")
    summary.append(f"   High Priority: {stats['high_count']}")
    summary.append("")

    # Breakdown by category
    summary.append("📂 ALERTS BY CATEGORY:")
    for category, count in stats['by_category'].items():
        summary.append(f"   {category}: {count}")
    summary.append("")

    # Key highlights
    summary.append("🎯 KEY HIGHLIGHTS:")
    summary.append(f"   AI Patterns Detected: {metrics['patterns_detected']}")
    summary.append(f"   Volume Spikes (>5x): {metrics['volume_spikes']}")
    summary.append(f"   Confluence Signals: {metrics['confluence_signals']}")
    summary.append(f"   Top 10 Stock Entries: {metrics['top10_entries']}")
    summary.append("")

    # Performance
    if metrics['uptime_minutes'] > 0:
        alerts_per_hour = (stats['total'] / metrics['uptime_minutes']) * 60
        summary.append(f"📈 Performance: {alerts_per_hour:.1f} alerts/hour")
        summary.append("")

    summary.append("=" * 60)

    return "\n".join(summary)


def send_stock_alert(stock_name, alert_type, price, change_pct, net_flow, volume_ratio=None):
    """
    Send stock alerts via Telegram with cooldown and momentum validation

    Alert Types & Cooldowns:
    - BULLISH: 5-min cooldown per stock
    - BEARISH: 5-min cooldown per stock

    Momentum Filter:
    - For repeat alerts, BOTH % change AND net flow must be HIGHER than previous alert
    - This ensures we only alert on ACCELERATING momentum, not weakening moves
    """
    # CHECK MARKET HOURS: Only send alerts between 09:15 AM - 3:30 PM
    if not is_market_hours():
        return False  # Silently skip alerts outside market hours

    now = datetime.now()

    # Check cooldown and momentum based on alert type
    cooldown_key = f"{stock_name}_{alert_type}"

    if cooldown_key in engine.last_stock_alert:
        last_alert_data = engine.last_stock_alert[cooldown_key]
        last_alert_time = last_alert_data['time']
        last_change_pct = last_alert_data['change_pct']
        last_net_flow = last_alert_data['net_flow']

        time_diff = (now - last_alert_time).total_seconds() / 60  # minutes

        # Apply 5-minute cooldown
        if time_diff < 5:
            return False

        # MOMENTUM VALIDATION: Both % and flow must be HIGHER than previous alert
        # This filters out weakening momentum and only catches accelerating moves
        if abs(change_pct) <= abs(last_change_pct):
            print(f"⚠️ {stock_name} momentum filter: % not higher ({abs(change_pct):.2f}% vs {abs(last_change_pct):.2f}%)")
            return False

        if abs(net_flow) <= abs(last_net_flow):
            print(f"⚠️ {stock_name} momentum filter: Flow not higher ({abs(net_flow):.0f}M vs {abs(last_net_flow):.0f}M)")
            return False

        # If we reach here, momentum is ACCELERATING - allow alert!
        print(f"✅ {stock_name} momentum ACCELERATING: {abs(last_change_pct):.2f}%→{abs(change_pct):.2f}%, {abs(last_net_flow):.0f}M→{abs(net_flow):.0f}M")

    # Get NIFTY market context
    nifty_pct = get_nifty_daily_change(kite=engine.kite)
    market_ctx = get_market_context(alert_type, nifty_pct)

    # Format alert message with market context
    if alert_type == "BULLISH":
        base_interpretation = "Price rising + Strong call buying"
    elif alert_type == "BEARISH":
        base_interpretation = "Price falling + Strong put buying"
    else:
        return False  # Only BULLISH/BEARISH alerts allowed

    # Use market context for emoji, signal, and interpretation
    emoji = market_ctx['emoji']
    signal = market_ctx['upgraded_signal']
    tag = market_ctx['tag']

    interpretation = base_interpretation + market_ctx['interpretation_suffix']

    # Format price and flow
    price_str = f"₹{price:,.2f}"
    change_emoji = "🟢" if change_pct > 0 else "🔴"
    change_str = f"{change_emoji}{change_pct:+.2f}%"
    flow_emoji = "🟢" if net_flow > 0 else "🔴"
    flow_str = f"{flow_emoji}{format_number(net_flow)}"

    # Get sector performance
    sector_info = get_sector_performance(stock_name, kite=engine.kite, sector_map=engine.sector_mapping)

    # Build message with market context
    telegram_message = f"{emoji} {signal} - {stock_name} {tag}\n"
    telegram_message += f"{price_str} {change_str} | Flow {flow_str}\n"

    if sector_info:
        telegram_message += f"{sector_info}\n"
    telegram_message += f"{market_ctx['nifty_line']}\n"
    telegram_message += f"{interpretation}"

    # Send to Telegram
    try:
        send_telegram_alert(telegram_message)
        print(f"📱 Stock Alert: {stock_name} - {signal}")

        # Store alert data for momentum validation
        engine.last_stock_alert[cooldown_key] = {
            'time': now,
            'change_pct': change_pct,
            'net_flow': net_flow
        }

        # Save to alert history for next-day follow-up tracking
        save_alert_to_history(
            stock=stock_name,
            alert_type=alert_type,
            score=0,  # This function doesn't have score, so use 0
            price=price
        )

        # Check for recurring alert pattern (last 7 days)
        recurring_data = check_recurring_alert(stock_name, alert_type, 0)
        if recurring_data:
            send_recurring_alert(stock_name, alert_type, 0, recurring_data)

        # Check for milestone achievement (3, 5, 10, 15, 20...)
        milestone_data = check_milestone_alert(stock_name)
        if milestone_data:
            send_milestone_alert(stock_name, milestone_data, kite=engine.kite)

        # 🚀 TRIGGER ROCKET ANIMATION (Stars for stocks)
        # Fixed count of 4 stars/sparkles for stock alerts
        if 'rocket_triggers' not in st.session_state:
            st.session_state.rocket_triggers = []

        st.session_state.rocket_triggers.append({
            'type': 'STOCK',
            'direction': 'UP' if alert_type == 'BULLISH' else 'DOWN',
            'count': 4,  # Fixed count for stock alerts
            'priority': 'NORMAL'
        })

        return True
    except Exception as e:
        print(f"Error sending stock alert: {e}")
        return False

def send_nifty_enhanced_alert(score_result):
    """
    Enhanced NIFTY alert system with 3-minute confirmation and divergence detection

    Features:
    - 3-minute confirmation period (3 consecutive readings)
    - Score persistence check (must stay above threshold)
    - Price validation (must move in same direction)
    - Divergence detection (flow vs price mismatch)
    - Reversal warnings (weakening signals)
    - Universal cooldown (30 min for any alert)

    Alert Categories:
    - STRONG BULLISH: Score >75 for 3 min + Price up >0.1%
    - BULLISH: Score 60-75 for 3 min + Price up >0%
    - STRONG BEARISH: Score <-75 for 3 min + Price down >0.1%
    - BEARISH: Score -60 to -75 for 3 min + Price down >0%
    - BEARISH DIVERGENCE: Score >60 but price down >0.15%
    - BULLISH DIVERGENCE: Score <-60 but price up >0.15%
    - REVERSAL WARNING: Previous strong signal weakening
    """
    # CHECK MARKET HOURS: Only send alerts between 09:15 AM - 3:30 PM
    if not is_market_hours():
        return False

    now = datetime.now()
    total_score = score_result['total_score']
    current_price = score_result.get('nifty_price', 0)

    if not current_price:
        return False

    # Update buffers (keep last 3 readings = 3 minutes with 60s refresh)
    engine.nifty_score_buffer.append(total_score)
    engine.nifty_price_buffer.append(current_price)

    # Keep only last 3 readings
    if len(engine.nifty_score_buffer) > 3:
        engine.nifty_score_buffer.pop(0)
    if len(engine.nifty_price_buffer) > 3:
        engine.nifty_price_buffer.pop(0)

    # Need at least 3 readings for confirmation (3 minutes)
    if len(engine.nifty_score_buffer) < 3:
        print(f"⏳ Building confirmation buffer: {len(engine.nifty_score_buffer)}/3 readings")
        return False

    # Get price change from 3 minutes ago
    start_price = engine.nifty_price_buffer[0]
    price_change_pct = ((current_price - start_price) / start_price) * 100 if start_price > 0 else 0

    # Check universal cooldown (30 minutes for ANY alert)
    if engine.nifty_universal_cooldown:
        time_since_last = (now - engine.nifty_universal_cooldown).total_seconds() / 60
        if time_since_last < 30:
            return False

    # ==================================================================
    # DIVERGENCE DETECTION (Immediate alerts - no confirmation needed)
    # ==================================================================

    # BEARISH DIVERGENCE: Bullish flow but price falling
    if total_score >= 60 and price_change_pct < -0.15:
        alert_type = "BEARISH_DIVERGENCE"
        emoji = "⚠️"
        signal_text = "BEARISH DIVERGENCE"
        description = "Bullish options flow but price falling - Reversal risk!"
        confidence = "🔴 HIGH RISK"

        message = f"⚠️ <b>NIFTY ALERT - {signal_text}</b>\n\n"
        message += f"📊 <b>Score:</b> {total_score:+d}/100 (Bullish flow)\n"
        message += f"📉 <b>Price:</b> ₹{current_price:.2f} 🔴{price_change_pct:+.2f}% (3-min)\n\n"
        message += f"⚠️ <b>WARNING:</b> {description}\n"
        message += f"Options traders are bullish BUT price is falling.\n"
        message += f"This often signals:\n"
        message += f"• Trapped longs / Smart money selling\n"
        message += f"• Possible bearish reversal ahead\n\n"
        message += f"💰 <b>Current:</b> ₹{current_price:.2f}\n"
        message += f"⏰ {now.strftime('%I:%M:%S %p')}\n"
        message += f"#Nifty #Divergence #BearishRisk"

        try:
            send_telegram_alert(message)
            print(f"📱 {signal_text}: Score {total_score:+d}, Price {price_change_pct:+.2f}%")
            engine.nifty_universal_cooldown = now
            engine.nifty_last_alert_type = alert_type
            engine.nifty_last_alert_score = total_score

            # Trigger rockets for divergence
            if 'rocket_triggers' not in st.session_state:
                st.session_state.rocket_triggers = []
            st.session_state.rocket_triggers.append({
                'type': 'NIFTY',
                'direction': 'DOWN',
                'count': 3,
                'priority': 'CRITICAL'
            })
            return True
        except Exception as e:
            print(f"Error sending divergence alert: {e}")
            return False

    # BULLISH DIVERGENCE: Bearish flow but price rising
    if total_score <= -60 and price_change_pct > 0.15:
        alert_type = "BULLISH_DIVERGENCE"
        emoji = "⚠️"
        signal_text = "BULLISH DIVERGENCE"
        description = "Bearish options flow but price rising - Reversal opportunity!"
        confidence = "🟢 OPPORTUNITY"

        message = f"⚠️ <b>NIFTY ALERT - {signal_text}</b>\n\n"
        message += f"📊 <b>Score:</b> {total_score:+d}/100 (Bearish flow)\n"
        message += f"📈 <b>Price:</b> ₹{current_price:.2f} 🟢{price_change_pct:+.2f}% (3-min)\n\n"
        message += f"✨ <b>OPPORTUNITY:</b> {description}\n"
        message += f"Options traders are bearish BUT price is rising.\n"
        message += f"This often signals:\n"
        message += f"• Trapped shorts / Smart money buying\n"
        message += f"• Possible bullish continuation\n\n"
        message += f"💰 <b>Current:</b> ₹{current_price:.2f}\n"
        message += f"⏰ {now.strftime('%I:%M:%S %p')}\n"
        message += f"#Nifty #Divergence #BullishOpportunity"

        try:
            send_telegram_alert(message)
            print(f"📱 {signal_text}: Score {total_score:+d}, Price {price_change_pct:+.2f}%")
            engine.nifty_universal_cooldown = now
            engine.nifty_last_alert_type = alert_type
            engine.nifty_last_alert_score = total_score

            # Trigger rockets for divergence
            if 'rocket_triggers' not in st.session_state:
                st.session_state.rocket_triggers = []
            st.session_state.rocket_triggers.append({
                'type': 'NIFTY',
                'direction': 'UP',
                'count': 3,
                'priority': 'CRITICAL'
            })
            return True
        except Exception as e:
            print(f"Error sending divergence alert: {e}")
            return False

    # ==================================================================
    # REVERSAL WARNING (Previous strong signal weakening)
    # ==================================================================

    if engine.nifty_last_alert_type in ['STRONG_BULLISH', 'STRONG_BEARISH']:
        # Check if signal is weakening
        if engine.nifty_last_alert_type == 'STRONG_BULLISH' and total_score < 50:
            alert_type = "REVERSAL_WARNING"
            message = f"🔄 <b>NIFTY MOMENTUM WEAKENING</b>\n\n"
            message += f"Previous: STRONG BULLISH ({engine.nifty_last_alert_score:+d})\n"
            message += f"Current: {total_score:+d}/100\n\n"
            message += f"⚠️ Bullish momentum fading - Consider exits\n"
            message += f"💰 Price: ₹{current_price:.2f} 🔴{price_change_pct:+.2f}%\n"
            message += f"⏰ {now.strftime('%I:%M:%S %p')}"

            try:
                send_telegram_alert(message)
                print(f"📱 REVERSAL WARNING: BULLISH weakening to {total_score:+d}")
                engine.nifty_last_alert_type = alert_type
                return True
            except Exception as e:
                print(f"Error sending reversal warning: {e}")

        elif engine.nifty_last_alert_type == 'STRONG_BEARISH' and total_score > -50:
            alert_type = "REVERSAL_WARNING"
            message = f"🔄 <b>NIFTY MOMENTUM WEAKENING</b>\n\n"
            message += f"Previous: STRONG BEARISH ({engine.nifty_last_alert_score:+d})\n"
            message += f"Current: {total_score:+d}/100\n\n"
            message += f"⚠️ Bearish momentum fading - Consider exits\n"
            message += f"💰 Price: ₹{current_price:.2f} 🟢{price_change_pct:+.2f}%\n"
            message += f"⏰ {now.strftime('%I:%M:%S %p')}"

            try:
                send_telegram_alert(message)
                print(f"📱 REVERSAL WARNING: BEARISH weakening to {total_score:+d}")
                engine.nifty_last_alert_type = alert_type
                return True
            except Exception as e:
                print(f"Error sending reversal warning: {e}")

    # ==================================================================
    # CONFIRMED SIGNALS (3-minute persistence required)
    # ==================================================================

    # Check score persistence (all 3 readings must meet threshold)
    scores = engine.nifty_score_buffer

    # STRONG BULLISH: Score >75 for all 3 readings + Price up >0.1%
    if all(s > 75 for s in scores) and price_change_pct > 0.1:
        alert_type = "STRONG_BULLISH"
        emoji = "🟢"
        signal_text = "STRONG BULLISH"
        confidence = "🔴 VERY HIGH"
        rocket_count = 5

    # BULLISH: Score 60-75 for all 3 readings + Price up >0%
    elif all(s >= 60 for s in scores) and price_change_pct > 0:
        alert_type = "BULLISH"
        emoji = "🟢"
        signal_text = "BULLISH"
        confidence = "🟠 HIGH" if all(s > 70 for s in scores) else "🟡 MEDIUM"
        rocket_count = 4 if all(s > 70 for s in scores) else 3

    # STRONG BEARISH: Score <-75 for all 3 readings + Price down >0.1%
    elif all(s < -75 for s in scores) and price_change_pct < -0.1:
        alert_type = "STRONG_BEARISH"
        emoji = "🔴"
        signal_text = "STRONG BEARISH"
        confidence = "🔴 VERY HIGH"
        rocket_count = 5

    # BEARISH: Score -60 to -75 for all 3 readings + Price down >0%
    elif all(s <= -60 for s in scores) and price_change_pct < 0:
        alert_type = "BEARISH"
        emoji = "🔴"
        signal_text = "BEARISH"
        confidence = "🟠 HIGH" if all(s < -70 for s in scores) else "🟡 MEDIUM"
        rocket_count = 4 if all(s < -70 for s in scores) else 3

    else:
        # No confirmed signal yet
        return False

    # Build alert message
    breakdown = score_result['breakdown']

    message = f"🚨 <b>NIFTY CONFIRMED SIGNAL {emoji}</b>\n\n"
    message += f"📊 <b>{signal_text} MOMENTUM</b>\n"
    message += f"Score: <b>{total_score:+d}/100</b> {confidence}\n"
    message += f"✅ <b>3-Minute Confirmation</b> (Scores: {scores[0]:+d} → {scores[1]:+d} → {scores[2]:+d})\n\n"

    # Price movement
    price_emoji = "🟢" if price_change_pct > 0 else "🔴"
    message += f"💰 <b>Price Movement:</b>\n"
    message += f"   3 min ago: ₹{start_price:.2f}\n"
    message += f"   Now: ₹{current_price:.2f} {price_emoji}{price_change_pct:+.2f}%\n\n"

    # Key conditions (show only strong signals)
    message += "✅ <b>Key Signals:</b>\n"
    if abs(breakdown.get('ce_pe_flow', 0)) >= 10:
        flow_type = "CE" if breakdown['ce_pe_flow'] > 0 else "PE"
        message += f"• {flow_type} Flow dominance ✓\n"
    if abs(breakdown.get('session_spikes', 0)) >= 8:
        spike_type = "CE" if breakdown['session_spikes'] > 0 else "PE"
        message += f"• {spike_type} Spikes ahead ✓\n"
    if abs(breakdown.get('vwap_supertrend', 0)) >= 15:
        tech_signal = "BULLISH" if breakdown['vwap_supertrend'] > 0 else "BEARISH"
        message += f"• VWAP/ST: {tech_signal} ✓\n"
    if abs(breakdown.get('nifty_net_flow', 0)) >= 7:
        flow_sign = "+ve" if breakdown['nifty_net_flow'] > 0 else "-ve"
        message += f"• Nifty Net Flow: {flow_sign} ✓\n"

    message += f"\n⏰ {now.strftime('%I:%M:%S %p')}\n"
    message += f"#Nifty #{alert_type.replace('_', '')}"

    # Send alert
    try:
        send_telegram_alert(message)
        print(f"📱 NIFTY {signal_text}: Score {total_score:+d}, Price {price_change_pct:+.2f}% (3-min confirmed)")

        # Update state
        engine.nifty_universal_cooldown = now
        engine.nifty_last_alert_type = alert_type
        engine.nifty_last_alert_score = total_score

        # Trigger rockets
        direction = 'UP' if 'BULLISH' in alert_type else 'DOWN'
        priority = 'CRITICAL' if 'STRONG' in alert_type else 'NORMAL'

        if 'rocket_triggers' not in st.session_state:
            st.session_state.rocket_triggers = []
        st.session_state.rocket_triggers.append({
            'type': 'NIFTY',
            'direction': direction,
            'count': rocket_count,
            'priority': priority
        })

        return True

    except Exception as e:
        print(f"Error sending NIFTY enhanced alert: {e}")
        return False

def send_nifty_comprehensive_alert(score_result):
    """
    Send comprehensive NIFTY alert based on 8-criteria scoring
    Alert Threshold: +60 (BULLISH) / -60 (BEARISH)
    Confidence: Medium (60-69), High (70-84), Very High (85-100)
    Cooldown: 15 minutes per signal type
    """
    # CHECK MARKET HOURS: Only send alerts between 09:15 AM - 3:30 PM
    if not is_market_hours():
        return False

    total_score = score_result['total_score']
    breakdown = score_result['breakdown']

    # Check if score meets threshold
    if abs(total_score) < 60:
        return False  # Not strong enough to alert

    now = datetime.now()
    signal_type = 'BULLISH' if total_score > 0 else 'BEARISH'
    cooldown_key = f"NIFTY_COMPREHENSIVE_{signal_type}"

    # Check cooldown (15 minutes)
    if cooldown_key in engine.last_stock_alert:
        last_alert_time = engine.last_stock_alert[cooldown_key]
        time_diff = (now - last_alert_time).total_seconds() / 60
        if time_diff < 15:
            return False

    # Determine confidence level
    abs_score = abs(total_score)
    if abs_score >= 85:
        confidence = "🔴 VERY HIGH"
        confidence_text = "EXTREMELY STRONG"
    elif abs_score >= 70:
        confidence = "🟠 HIGH"
        confidence_text = "STRONG"
    else:  # 60-69
        confidence = "🟡 MEDIUM"
        confidence_text = ""

    # Format alert message
    if signal_type == 'BULLISH':
        emoji = "🟢"
        direction = "BULLISH"
        full_signal = f"{confidence_text} {direction}".strip()
    else:
        emoji = "🔴"
        direction = "BEARISH"
        full_signal = f"{confidence_text} {direction}".strip()

    telegram_message = f"🚨 <b>NIFTY COMPREHENSIVE SIGNAL {emoji}</b>\n\n"
    telegram_message += f"📊 <b>{full_signal} MOMENTUM</b>\n"
    telegram_message += f"Score: <b>{total_score:+d}/100</b> {confidence}\n\n"

    # List conditions with check marks
    telegram_message += "✅ <b>Key Conditions:</b>\n"

    # CE/PE Flow
    if breakdown['ce_pe_flow'] > 0:
        telegram_message += "• CE Flow dominance ✓\n"
    elif breakdown['ce_pe_flow'] < 0:
        telegram_message += "• PE Flow dominance ✓\n"

    # Session Spikes
    spike_score = breakdown['session_spikes']
    if abs(spike_score) >= 12:
        telegram_message += f"• {'CE' if spike_score > 0 else 'PE'} Spikes: Strong dominance ✓\n"
    elif abs(spike_score) >= 8:
        telegram_message += f"• {'CE' if spike_score > 0 else 'PE'} Spikes: Ahead ✓\n"

    # CE vs PE Race
    if breakdown['ce_pe_race'] != 0:
        telegram_message += f"• CE vs PE Race: {'BULLISH' if breakdown['ce_pe_race'] > 0 else 'BEARISH'} ✓\n"

    # Live Sentiment
    if abs(breakdown['live_sentiment']) >= 8:
        telegram_message += f"• Market Sentiment: {'BULLISH' if breakdown['live_sentiment'] > 0 else 'BEARISH'} ✓\n"

    # Nifty Net Flow
    if abs(breakdown['nifty_net_flow']) >= 7:
        nifty_flow_text = f"+ve (Strong)" if breakdown['nifty_net_flow'] > 0 else "-ve (Strong)"
        telegram_message += f"• Nifty Net Flow: {nifty_flow_text} ✓\n"

    # Indices metrics
    indices_up_pct = score_result.get('indices_up_pct', 0)
    stocks_up_pct = score_result.get('stocks_up_pct', 0)

    if abs(breakdown['indices_net_flow']) >= 7:
        telegram_message += f"• Indices: {indices_up_pct:.0f}% positive ✓\n"

    if abs(breakdown['stocks_performance']) >= 7:
        telegram_message += f"• F&O Stocks: {stocks_up_pct:.0f}% positive ✓\n"

    # Add price info if available
    nifty_price = score_result.get('nifty_price')
    nifty_change = score_result.get('nifty_change_pct')
    if nifty_price:
        change_emoji = "🟢" if nifty_change and nifty_change > 0 else "🔴"
        telegram_message += f"\n💰 <b>Nifty:</b> ₹{nifty_price:.2f} {change_emoji}{nifty_change:+.2f}%\n"

    # Timestamp
    telegram_message += f"\n⏰ {now.strftime('%I:%M:%S %p')}\n"
    telegram_message += f"#Nifty #{direction}"

    # Send alert
    try:
        send_telegram_alert(telegram_message)
        print(f"📱 NIFTY Comprehensive Alert: {full_signal} (Score: {total_score:+d})")
        engine.last_stock_alert[cooldown_key] = now

        # 🚀 TRIGGER ROCKET ANIMATION
        # Calculate rocket count based on score (3-5 rockets)
        if abs_score >= 85:
            rocket_count = 5  # VERY HIGH confidence
        elif abs_score >= 70:
            rocket_count = 4  # HIGH confidence
        else:  # 60-69
            rocket_count = 3  # MEDIUM confidence

        # Store rocket trigger in session state
        if 'rocket_triggers' not in st.session_state:
            st.session_state.rocket_triggers = []

        st.session_state.rocket_triggers.append({
            'type': 'NIFTY',
            'direction': 'UP' if signal_type == 'BULLISH' else 'DOWN',
            'count': rocket_count,
            'priority': 'CRITICAL' if abs_score >= 85 else 'NORMAL'
        })

        return True
    except Exception as e:
        print(f"Error sending NIFTY comprehensive alert: {e}")
        return False

def send_stock_confluence_alert(confluence_stocks):
    """
    Send comprehensive stock confluence alert
    confluence_stocks: dict of {stock_name: count}
    Sends alert on ANY change to the list
    """
    # CHECK MARKET HOURS: Only send alerts between 09:15 AM - 3:30 PM
    if not is_market_hours():
        return False

    if not confluence_stocks:
        return False

    telegram_message = "🔥 <b>STOCK CONFLUENCE ALERTS</b>\n\n"
    telegram_message += f"✅ <b>Stocks in ALL 3 Systems:</b>\n"

    # Sort by count (highest first), then alphabetically
    sorted_stocks = sorted(confluence_stocks.items(), key=lambda x: (-x[1], x[0]))

    for stock_name, count in sorted_stocks:
        if count >= 4:
            telegram_message += f"• <b>{stock_name}</b> ({count}) ⚡ VERY STRONG\n"
        elif count >= 2:
            telegram_message += f"• <b>{stock_name}</b> ({count}) - Sustained\n"
        else:  # count == 1
            telegram_message += f"• <b>{stock_name}</b> (1) - NEW\n"

    telegram_message += f"\n📊 {len(confluence_stocks)} stock(s) with full alignment\n"
    telegram_message += f"⏰ {datetime.now().strftime('%I:%M:%S %p')}"

    # Send alert
    try:
        send_telegram_alert(telegram_message)
        print(f"📱 Stock Confluence Alert: {len(confluence_stocks)} stocks")
        return True
    except Exception as e:
        print(f"Error sending stock confluence alert: {e}")
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
        # Cache valid for 7 days (604800 seconds) to show historical data when markets closed
        if (now - cached_at).total_seconds() < 604800:
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

# =========================
# WEEKLY EXPIRY TRACKING SYSTEM
# =========================

def get_next_nifty_expiries(ins_df: pd.DataFrame, num_expiries=4) -> list:
    """
    Get next N NIFTY option expiries dynamically from instruments data

    Returns: List of expiry dates (datetime objects) sorted by date
    Example: [datetime(2024, 12, 24), datetime(2024, 12, 31), ...]
    """
    try:
        # Filter NIFTY options
        nifty_options = ins_df[
            (ins_df['name'] == 'NIFTY') &
            (ins_df['instrument_type'].isin(['CE', 'PE'])) &
            (ins_df['segment'].isin(DERIV_OPT_SEGMENTS))
        ].copy()

        if nifty_options.empty:
            print("⚠️ No NIFTY options found in instruments")
            return []

        # Get unique expiry dates
        expiries = nifty_options['expiry'].dropna().unique()
        expiries = pd.to_datetime(expiries)

        # Filter future expiries only
        today = pd.Timestamp.now().normalize()
        future_expiries = expiries[expiries >= today]

        # Sort and take next N
        future_expiries = sorted(future_expiries)[:num_expiries]

        print(f"📅 Next {len(future_expiries)} NIFTY expiries:")
        for i, exp in enumerate(future_expiries, 1):
            print(f"   Week {i}: {exp.strftime('%d-%b-%Y (%A)')}")

        return future_expiries

    except Exception as e:
        print(f"❌ Error getting NIFTY expiries: {e}")
        return []

def get_atm_strike(current_price: float, strike_gap=50) -> int:
    """
    Calculate ATM strike based on current NIFTY price

    Args:
        current_price: Current NIFTY spot price
        strike_gap: Strike interval (default 50 for NIFTY)

    Returns: ATM strike price
    Example: If price is 26075, ATM = 26100
    """
    return round(current_price / strike_gap) * strike_gap

def get_strikes_for_expiry(ins_df: pd.DataFrame, expiry_date, atm_strike: int, range_strikes=20) -> dict:
    """
    Get ATM ± N strikes for a specific expiry

    Args:
        ins_df: Instruments DataFrame
        expiry_date: Expiry date to filter
        atm_strike: ATM strike price
        range_strikes: Number of strikes above and below ATM (default 20)

    Returns: Dict with strike -> {ce_token, pe_token, strike}
    """
    try:
        # Filter NIFTY options for this expiry
        expiry_options = ins_df[
            (ins_df['name'] == 'NIFTY') &
            (ins_df['instrument_type'].isin(['CE', 'PE'])) &
            (ins_df['expiry'] == expiry_date) &
            (ins_df['segment'].isin(DERIV_OPT_SEGMENTS))
        ].copy()

        if expiry_options.empty:
            return {}

        # Get all available strikes
        all_strikes = sorted(expiry_options['strike'].dropna().unique())

        # Find ATM position
        atm_idx = None
        for i, strike in enumerate(all_strikes):
            if strike >= atm_strike:
                atm_idx = i
                break

        if atm_idx is None:
            atm_idx = len(all_strikes) - 1

        # Get ATM ± range_strikes
        start_idx = max(0, atm_idx - range_strikes)
        end_idx = min(len(all_strikes), atm_idx + range_strikes + 1)
        selected_strikes = all_strikes[start_idx:end_idx]

        # Build strike mapping with CE/PE tokens
        strike_map = {}
        for strike in selected_strikes:
            ce_data = expiry_options[
                (expiry_options['strike'] == strike) &
                (expiry_options['instrument_type'] == 'CE')
            ]
            pe_data = expiry_options[
                (expiry_options['strike'] == strike) &
                (expiry_options['instrument_type'] == 'PE')
            ]

            strike_map[strike] = {
                'strike': strike,
                'ce_token': ce_data['instrument_token'].iloc[0] if not ce_data.empty else None,
                'pe_token': pe_data['instrument_token'].iloc[0] if not pe_data.empty else None,
                'ce_symbol': ce_data['tradingsymbol'].iloc[0] if not ce_data.empty else None,
                'pe_symbol': pe_data['tradingsymbol'].iloc[0] if not pe_data.empty else None
            }

        print(f"   Found {len(strike_map)} strikes (ATM: {atm_strike})")
        return strike_map

    except Exception as e:
        print(f"❌ Error getting strikes for expiry: {e}")
        return {}

def collect_weekly_expiry_data(kite: KiteConnect, ins_df: pd.DataFrame, expiry_date, strike_map: dict) -> pd.DataFrame:
    """
    Collect options data for all strikes of an expiry

    Returns: DataFrame with columns:
    - strike, type (CE/PE), last_price, volume, oi, oi_change,
      bid, ask, net_flow, iv, delta, theta, gamma, vega
    """
    print(f"   🔍 collect_weekly_expiry_data() STARTED")
    try:
        # Collect all tokens
        tokens = []
        for strike_data in strike_map.values():
            if strike_data['ce_token']:
                tokens.append(strike_data['ce_token'])
            if strike_data['pe_token']:
                tokens.append(strike_data['pe_token'])

        print(f"   🔍 Collected {len(tokens)} tokens from strike_map")

        if not tokens:
            print(f"   ❌ No tokens found in strike_map!")
            return pd.DataFrame()

        print(f"   🔍 Calling kite.quote() with {len(tokens)} tokens...")
        # Fetch quotes
        quotes = kite.quote([f"NFO:{token}" for token in tokens])
        print(f"   🔍 kite.quote() returned successfully")

        # DEBUG: Check if quotes were fetched
        print(f"   📊 Fetched {len(quotes) if quotes else 0} quotes from Kite API")
        if not quotes:
            print(f"   ❌ No quotes returned! Token count: {len(tokens)}")
            return pd.DataFrame()

        # DEBUG: Show sample quote key format
        if quotes:
            sample_key = list(quotes.keys())[0] if quotes else None
            print(f"   Sample quote key: {sample_key}")

        # Build dataframe
        rows = []
        for strike, strike_data in strike_map.items():
            # CE data
            if strike_data['ce_token']:
                ce_key = f"NFO:{strike_data['ce_token']}"
                if ce_key in quotes:
                    q = quotes[ce_key]
                    rows.append({
                        'strike': strike,
                        'type': 'CE',
                        'symbol': strike_data['ce_symbol'],
                        'token': strike_data['ce_token'],
                        'last_price': q.get('last_price', 0),
                        'volume': q.get('volume', 0),
                        'oi': q.get('oi', 0),
                        'oi_day_high': q.get('oi_day_high', 0),
                        'oi_day_low': q.get('oi_day_low', 0),
                        'bid': q.get('depth', {}).get('buy', [{}])[0].get('price', 0) if q.get('depth') else 0,
                        'ask': q.get('depth', {}).get('sell', [{}])[0].get('price', 0) if q.get('depth') else 0,
                    })

            # PE data
            if strike_data['pe_token']:
                pe_key = f"NFO:{strike_data['pe_token']}"
                if pe_key in quotes:
                    q = quotes[pe_key]
                    rows.append({
                        'strike': strike,
                        'type': 'PE',
                        'symbol': strike_data['pe_symbol'],
                        'token': strike_data['pe_token'],
                        'last_price': q.get('last_price', 0),
                        'volume': q.get('volume', 0),
                        'oi': q.get('oi', 0),
                        'oi_day_high': q.get('oi_day_high', 0),
                        'oi_day_low': q.get('oi_day_low', 0),
                        'bid': q.get('depth', {}).get('buy', [{}])[0].get('price', 0) if q.get('depth') else 0,
                        'ask': q.get('depth', {}).get('sell', [{}])[0].get('price', 0) if q.get('depth') else 0,
                    })

        df = pd.DataFrame(rows)

        if not df.empty:
            # Calculate net flow (volume * last_price for options)
            df['net_flow'] = df['volume'] * df['last_price']
            # For PE, make flow negative
            df.loc[df['type'] == 'PE', 'net_flow'] *= -1

            # Calculate OI change
            df['oi_change'] = df['oi'] - df['oi_day_low']  # Approximation

            # Placeholder for Greeks (would need Greeks API or calculation)
            df['iv'] = 0  # Implied Volatility
            df['delta'] = 0
            df['theta'] = 0
            df['gamma'] = 0
            df['vega'] = 0

        return df

    except Exception as e:
        print(f"❌ Error collecting weekly expiry data: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()

def save_cumulative_expiry_data(expiry_date, daily_df: pd.DataFrame, data_dir="data/weekly_expiry"):
    """
    Save or update cumulative expiry data to CSV

    Logic:
    - Day 1: Save fresh data
    - Day 2+: Load previous, add today's data, save cumulative
    """
    try:
        # Create data directory
        Path(data_dir).mkdir(parents=True, exist_ok=True)

        # CSV filename based on expiry date
        expiry_str = expiry_date.strftime('%d%b%Y').upper()
        csv_file = Path(data_dir) / f"nifty_{expiry_str}.csv"

        # Calculate current day of week (for tracking)
        today = datetime.now().date()

        if csv_file.exists():
            # Load previous cumulative data
            prev_df = pd.read_csv(csv_file)

            # Merge with today's data (sum volumes, flows, OI changes)
            # Group by strike + type
            if not prev_df.empty and not daily_df.empty:
                # Merge on strike + type
                cumulative_df = prev_df.merge(
                    daily_df[['strike', 'type', 'net_flow', 'volume', 'oi_change']],
                    on=['strike', 'type'],
                    how='outer',
                    suffixes=('_prev', '_today')
                )

                # Calculate cumulative values
                cumulative_df['cumulative_flow'] = (
                    cumulative_df['cumulative_flow'].fillna(0) +
                    cumulative_df['net_flow_today'].fillna(0)
                )
                cumulative_df['cumulative_volume'] = (
                    cumulative_df['cumulative_volume'].fillna(0) +
                    cumulative_df['volume_today'].fillna(0)
                )
                cumulative_df['cumulative_oi_change'] = (
                    cumulative_df['cumulative_oi_change'].fillna(0) +
                    cumulative_df['oi_change_today'].fillna(0)
                )

                # Update latest values
                cumulative_df['last_price'] = daily_df['last_price']
                cumulative_df['oi'] = daily_df['oi']
                cumulative_df['daily_flow'] = daily_df['net_flow']
                cumulative_df['daily_volume'] = daily_df['volume']

                # Keep symbol and token
                cumulative_df['symbol'] = daily_df['symbol']
                cumulative_df['token'] = daily_df['token']

            else:
                cumulative_df = prev_df
        else:
            # First day - initialize cumulative columns
            cumulative_df = daily_df.copy()
            cumulative_df['cumulative_flow'] = cumulative_df['net_flow']
            cumulative_df['cumulative_volume'] = cumulative_df['volume']
            cumulative_df['cumulative_oi_change'] = cumulative_df['oi_change']
            cumulative_df['daily_flow'] = cumulative_df['net_flow']
            cumulative_df['daily_volume'] = cumulative_df['volume']

        # Save updated cumulative data
        cumulative_df.to_csv(csv_file, index=False)
        print(f"✅ Saved cumulative data to {csv_file}")

        return cumulative_df

    except Exception as e:
        print(f"❌ Error saving cumulative data: {e}")
        import traceback
        traceback.print_exc()
        return daily_df

# ============================================
# STOCK MONTHLY EXPIRY TRACKING FUNCTIONS
# ============================================

def get_stock_expiry(ins_df: pd.DataFrame, symbol: str) -> datetime:
    """
    Get current month expiry for a stock from live options data.
    Returns the nearest future expiry date.
    """
    try:
        stock_options = ins_df[
            (ins_df['name'] == symbol) &
            (ins_df['instrument_type'] == 'CE') &
            (ins_df['segment'].isin(DERIV_OPT_SEGMENTS))
        ].copy()

        if stock_options.empty:
            return None

        # Get unique expiry dates
        expiries = pd.to_datetime(stock_options['expiry']).dt.date.unique()
        expiries = sorted([e for e in expiries if e >= datetime.now().date()])

        if expiries:
            return datetime.combine(expiries[0], datetime.min.time())
        return None

    except Exception as e:
        print(f"❌ Error getting expiry for {symbol}: {e}")
        return None

def get_stock_atm_strike(current_price: float, symbol: str = None) -> int:
    """
    Calculate ATM strike for a stock.
    Strike gap varies by stock price range.
    """
    if current_price < 500:
        strike_gap = 10  # Stocks under 500: 10 gap
    elif current_price < 1000:
        strike_gap = 20  # Stocks 500-1000: 20 gap
    elif current_price < 2500:
        strike_gap = 50  # Stocks 1000-2500: 50 gap
    else:
        strike_gap = 100  # Stocks above 2500: 100 gap

    return round(current_price / strike_gap) * strike_gap

def get_stock_strikes_for_expiry(ins_df: pd.DataFrame, symbol: str, expiry_date: datetime,
                                 atm_strike: int, range_strikes: int = 10) -> dict:
    """
    Get ATM ± range_strikes for a stock expiry.
    Returns dict: strike -> {ce_token, pe_token, ce_symbol, pe_symbol}
    """
    try:
        expiry_str = expiry_date.strftime('%Y-%m-%d')

        # Filter options for this stock and expiry
        stock_opts = ins_df[
            (ins_df['name'] == symbol) &
            (ins_df['expiry'] == expiry_str) &
            (ins_df['segment'].isin(DERIV_OPT_SEGMENTS))
        ].copy()

        if stock_opts.empty:
            return {}

        # Determine strike gap
        if atm_strike < 500:
            strike_gap = 10
        elif atm_strike < 1000:
            strike_gap = 20
        elif atm_strike < 2500:
            strike_gap = 50
        else:
            strike_gap = 100

        # Generate ATM ± range strikes
        strikes = [atm_strike + (i * strike_gap) for i in range(-range_strikes, range_strikes + 1)]

        strike_map = {}
        for strike in strikes:
            ce_row = stock_opts[(stock_opts['strike'] == strike) & (stock_opts['instrument_type'] == 'CE')]
            pe_row = stock_opts[(stock_opts['strike'] == strike) & (stock_opts['instrument_type'] == 'PE')]

            if not ce_row.empty and not pe_row.empty:
                strike_map[strike] = {
                    'ce_token': ce_row.iloc[0]['instrument_token'],
                    'pe_token': pe_row.iloc[0]['instrument_token'],
                    'ce_symbol': ce_row.iloc[0]['tradingsymbol'],
                    'pe_symbol': pe_row.iloc[0]['tradingsymbol']
                }

        return strike_map

    except Exception as e:
        print(f"❌ Error getting strikes for {symbol}: {e}")
        return {}

def collect_stock_expiry_data(kite, ins_df: pd.DataFrame, symbol: str, expiry_date: datetime,
                               strike_map: dict) -> pd.DataFrame:
    """
    Collect live options data for a stock expiry.
    Returns DataFrame with cumulative flow and volume for CE/PE.
    """
    try:
        if not strike_map:
            return pd.DataFrame()

        # Collect all tokens
        all_tokens = []
        for strike_data in strike_map.values():
            all_tokens.extend([strike_data['ce_token'], strike_data['pe_token']])

        # Fetch quotes
        quotes = kite.quote([f"NFO:{token}" for token in all_tokens])

        # DEBUG: Check quote fetch
        if not quotes:
            print(f"   ❌ {symbol}: No quotes returned")
            return pd.DataFrame()

        rows = []
        for strike, strike_data in strike_map.items():
            ce_token = f"NFO:{strike_data['ce_token']}"
            pe_token = f"NFO:{strike_data['pe_token']}"

            ce_quote = quotes.get(ce_token, {})
            pe_quote = quotes.get(pe_token, {})

            # CE row
            ce_price = ce_quote.get('last_price', 0)
            ce_volume = ce_quote.get('volume', 0)
            ce_oi = ce_quote.get('oi', 0)
            ce_flow = ce_volume * ce_price

            rows.append({
                'strike': strike,
                'type': 'CE',
                'last_price': ce_price,
                'volume': ce_volume,
                'oi': ce_oi,
                'net_flow': ce_flow
            })

            # PE row
            pe_price = pe_quote.get('last_price', 0)
            pe_volume = pe_quote.get('volume', 0)
            pe_oi = pe_quote.get('oi', 0)
            pe_flow = -(pe_volume * pe_price)  # Negative for PE

            rows.append({
                'strike': strike,
                'type': 'PE',
                'last_price': pe_price,
                'volume': pe_volume,
                'oi': pe_oi,
                'net_flow': pe_flow
            })

        return pd.DataFrame(rows)

    except Exception as e:
        print(f"❌ Error collecting data for {symbol}: {e}")
        return pd.DataFrame()

def save_cumulative_stock_expiry_data(symbol: str, expiry_date: datetime, daily_df: pd.DataFrame,
                                      data_dir: str = "data/stock_expiry") -> pd.DataFrame:
    """
    Save stock expiry data with cumulative tracking.
    Day 1: Save fresh data
    Day 2+: Load previous + add today's values
    """
    try:
        os.makedirs(data_dir, exist_ok=True)

        expiry_str = expiry_date.strftime('%d%b%Y').upper()
        csv_file = Path(data_dir) / f"{symbol}_{expiry_str}.csv"

        # Add daily columns
        daily_df['daily_flow'] = daily_df['net_flow']
        daily_df['daily_volume'] = daily_df['volume']

        if csv_file.exists():
            # Load previous cumulative data
            prev_df = pd.read_csv(csv_file)

            # Merge on strike and type
            merged = prev_df.merge(
                daily_df[['strike', 'type', 'daily_flow', 'daily_volume', 'last_price', 'oi']],
                on=['strike', 'type'],
                how='outer',
                suffixes=('', '_today')
            )

            # Update cumulative values
            merged['cumulative_flow'] = merged['cumulative_flow'].fillna(0) + merged['daily_flow'].fillna(0)
            merged['cumulative_volume'] = merged['cumulative_volume'].fillna(0) + merged['daily_volume'].fillna(0)

            # Update latest price and OI
            merged['last_price'] = merged['last_price_today'].fillna(merged['last_price'])
            merged['oi'] = merged['oi_today'].fillna(merged['oi'])

            cumulative_df = merged[['strike', 'type', 'cumulative_flow', 'cumulative_volume',
                                   'daily_flow', 'daily_volume', 'last_price', 'oi']]
        else:
            # First day - initialize cumulative columns
            cumulative_df = daily_df.copy()
            cumulative_df['cumulative_flow'] = cumulative_df['daily_flow']
            cumulative_df['cumulative_volume'] = cumulative_df['daily_volume']
            cumulative_df = cumulative_df[['strike', 'type', 'cumulative_flow', 'cumulative_volume',
                                          'daily_flow', 'daily_volume', 'last_price', 'oi']]

        # Save updated CSV
        cumulative_df.to_csv(csv_file, index=False)
        return cumulative_df

    except Exception as e:
        print(f"❌ Error saving stock data for {symbol}: {e}")
        return daily_df

def get_top_stocks_by_flow(data_dir: str = "data/stock_expiry", top_n: int = 10) -> pd.DataFrame:
    """
    Read all stock expiry CSVs and return top N stocks by absolute net flow.
    Sorted by |CE Flow + PE Flow| descending.
    """
    try:
        data_path = Path(data_dir)
        if not data_path.exists():
            return pd.DataFrame()

        csv_files = list(data_path.glob("*.csv"))
        if not csv_files:
            return pd.DataFrame()

        stock_summaries = []

        for csv_file in csv_files:
            try:
                # Extract symbol and expiry from filename: RELIANCE_30JAN2025.csv
                filename = csv_file.stem
                parts = filename.rsplit('_', 1)
                if len(parts) != 2:
                    continue

                symbol = parts[0]
                expiry_str = parts[1]

                # Load data
                df = pd.read_csv(csv_file)
                if df.empty:
                    continue

                # Calculate totals
                ce_flow = df[df['type'] == 'CE']['cumulative_flow'].sum()
                pe_flow = df[df['type'] == 'PE']['cumulative_flow'].sum()
                ce_vol = df[df['type'] == 'CE']['cumulative_volume'].sum()
                pe_vol = df[df['type'] == 'PE']['cumulative_volume'].sum()

                net_flow = ce_flow + pe_flow
                abs_net_flow = abs(net_flow)

                stock_summaries.append({
                    'symbol': symbol,
                    'expiry': expiry_str,
                    'ce_flow': ce_flow,
                    'pe_flow': pe_flow,
                    'ce_volume': ce_vol,
                    'pe_volume': pe_vol,
                    'net_flow': net_flow,
                    'abs_net_flow': abs_net_flow
                })

            except Exception as e:
                print(f"❌ Error processing {csv_file}: {e}")
                continue

        if not stock_summaries:
            return pd.DataFrame()

        # Create DataFrame and sort by absolute net flow
        summary_df = pd.DataFrame(stock_summaries)
        summary_df = summary_df.sort_values('abs_net_flow', ascending=False).head(top_n)

        return summary_df

    except Exception as e:
        print(f"❌ Error getting top stocks: {e}")
        return pd.DataFrame()

# ============================================
# ALERT FOLLOW-UP TRACKER FUNCTIONS
# ============================================

def save_alert_to_history(stock: str, alert_type: str, score: int, price: float, data_dir: str = "data"):
    """
    Save stock alert to history for next-day tracking.

    Args:
        stock: Stock symbol (e.g., "RELIANCE")
        alert_type: "BULLISH" or "BEARISH"
        score: Alert score
        price: Stock price at alert time
    """
    try:
        os.makedirs(data_dir, exist_ok=True)
        history_file = Path(data_dir) / "alert_history.csv"

        # Prepare new alert entry
        new_alert = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': datetime.now().strftime('%H:%M:%S'),
            'stock': stock,
            'alert_type': alert_type,
            'score': score,
            'alert_price': price,
            'followed_up': False  # Will be set to True after 9:20 AM check
        }

        # Load existing history or create new
        if history_file.exists():
            df = pd.read_csv(history_file)
            # Append new alert
            df = pd.concat([df, pd.DataFrame([new_alert])], ignore_index=True)
        else:
            df = pd.DataFrame([new_alert])

        # Keep only last 30 days
        df['date'] = pd.to_datetime(df['date'])
        cutoff_date = datetime.now() - timedelta(days=30)
        df = df[df['date'] >= cutoff_date]

        # Save
        df.to_csv(history_file, index=False)
        print(f"✅ Saved {stock} alert to history")

    except Exception as e:
        print(f"❌ Error saving alert to history: {e}")

def get_yesterday_alerts() -> pd.DataFrame:
    """
    Get all stock alerts from yesterday that haven't been followed up yet.

    Returns:
        DataFrame with columns: stock, alert_type, score, alert_price
    """
    try:
        history_file = Path("data/alert_history.csv")

        if not history_file.exists():
            return pd.DataFrame()

        df = pd.read_csv(history_file)
        df['date'] = pd.to_datetime(df['date'])

        # Get yesterday's date
        yesterday = (datetime.now() - timedelta(days=1)).date()

        # Filter yesterday's alerts that haven't been followed up
        yesterday_alerts = df[
            (df['date'].dt.date == yesterday) &
            (df['followed_up'] == False)
        ]

        return yesterday_alerts[['stock', 'alert_type', 'score', 'alert_price']]

    except Exception as e:
        print(f"❌ Error getting yesterday alerts: {e}")
        return pd.DataFrame()

def check_opening_momentum(kite, stocks_list: list) -> list:
    """
    Check opening momentum for list of stocks at 9:20 AM.
    Returns stocks with >1% or <-1% opening change.

    Args:
        kite: KiteConnect instance
        stocks_list: List of stock symbols

    Returns:
        List of dicts with stock, opening_pct, signal
    """
    try:
        if not stocks_list:
            return []

        momentum_stocks = []

        for stock in stocks_list:
            try:
                # Get stock quote
                quote = kite.quote(f"NSE:{stock}")

                if f"NSE:{stock}" in quote:
                    q = quote[f"NSE:{stock}"]

                    current_price = q.get('last_price', 0)
                    open_price = q.get('ohlc', {}).get('open', 0)
                    prev_close = q.get('ohlc', {}).get('close', 0)

                    if prev_close > 0 and open_price > 0:
                        # Calculate opening % change from previous close
                        opening_pct = ((open_price - prev_close) / prev_close) * 100
                        current_pct = ((current_price - prev_close) / prev_close) * 100

                        # Check if opening > ±1%
                        if abs(opening_pct) >= 1.0:
                            signal = "BULLISH" if opening_pct > 0 else "BEARISH"

                            momentum_stocks.append({
                                'stock': stock,
                                'opening_pct': opening_pct,
                                'current_pct': current_pct,
                                'current_price': current_price,
                                'prev_close': prev_close,
                                'signal': signal
                            })

            except Exception as e:
                print(f"❌ Error checking {stock}: {e}")
                continue

        return momentum_stocks

    except Exception as e:
        print(f"❌ Error in check_opening_momentum: {e}")
        return []

def send_followup_alert(stock: str, opening_pct: float, current_pct: float, current_price: float, signal: str):
    """
    Send priority Telegram alert for follow-up opportunity.
    """
    # CHECK MARKET HOURS: Only send alerts between 09:15 AM - 3:30 PM
    if not is_market_hours():
        return False

    try:
        emoji = "🟢" if signal == "BULLISH" else "🔴"
        action = "BUY" if signal == "BULLISH" else "AVOID/SHORT"

        message = f"""
🔥 **ALERT FOLLOW-UP - MOMENTUM DETECTED**

{emoji} **{stock}** - {signal}

📊 **Opening:** {opening_pct:+.2f}%
📈 **Current:** {current_pct:+.2f}%
💰 **Price:** ₹{current_price:.2f}

⚡ **Action:** {action}

This stock triggered alert yesterday and now showing strong {signal.lower()} momentum at market open!
"""

        send_telegram_message(message)
        print(f"📱 Sent follow-up alert for {stock}")

    except Exception as e:
        print(f"❌ Error sending follow-up alert: {e}")

def mark_alerts_followed_up(stocks_list: list):
    """
    Mark yesterday's alerts as followed up to avoid duplicate alerts.
    """
    try:
        history_file = Path("data/alert_history.csv")

        if not history_file.exists():
            return

        df = pd.read_csv(history_file)
        df['date'] = pd.to_datetime(df['date'])

        yesterday = (datetime.now() - timedelta(days=1)).date()

        # Mark as followed up
        df.loc[
            (df['date'].dt.date == yesterday) &
            (df['stock'].isin(stocks_list)),
            'followed_up'
        ] = True

        df.to_csv(history_file, index=False)

    except Exception as e:
        print(f"❌ Error marking alerts as followed up: {e}")

# ============================================
# RECURRING ALERT DETECTION FUNCTIONS
# ============================================

def check_recurring_alert(stock: str, alert_type: str, score: int, data_dir: str = "data") -> dict:
    """
    Check if stock was alerted in the last 7 days.

    Args:
        stock: Stock symbol
        alert_type: Current alert type (BULLISH/BEARISH)
        score: Current alert score

    Returns:
        dict with: is_recurring, days_since_last, total_count, last_alert, all_alerts, trend
        Returns None if not a recurring alert
    """
    try:
        history_file = Path(data_dir) / "alert_history.csv"

        if not history_file.exists():
            return None

        df = pd.read_csv(history_file)
        df['date'] = pd.to_datetime(df['date'])

        # Get last 7 days of alerts for this stock
        seven_days_ago = datetime.now() - timedelta(days=7)
        today = datetime.now().date()

        stock_alerts = df[
            (df['stock'] == stock) &
            (df['date'] >= seven_days_ago) &
            (df['date'].dt.date < today)  # Exclude today
        ].copy()

        if stock_alerts.empty:
            return None  # No previous alerts in last 7 days

        # Sort by date descending (most recent first)
        stock_alerts = stock_alerts.sort_values('date', ascending=False)

        # Get most recent alert
        last_alert = stock_alerts.iloc[0]
        last_alert_date = last_alert['date'].date()

        # Calculate days since last alert
        days_since = (today - last_alert_date).days

        # Count total alerts in last 7 days
        total_count = len(stock_alerts)

        # Analyze trend (all same signal or mixed?)
        signal_types = stock_alerts['alert_type'].unique()
        if len(signal_types) == 1 and signal_types[0] == alert_type:
            # All same signal as current
            trend = f"All {alert_type}"
        elif len(signal_types) == 1 and signal_types[0] != alert_type:
            # Signal reversal
            trend = f"REVERSAL: Was {signal_types[0]}, now {alert_type}"
        else:
            # Mixed signals
            trend = "Mixed signals"

        # Analyze score trend (if we have scores)
        score_trend = None
        if not stock_alerts['score'].isna().all():
            prev_scores = stock_alerts['score'].dropna().tolist()
            if prev_scores and score > 0:
                if len(prev_scores) >= 2:
                    # Compare average of previous scores with current
                    avg_prev_score = sum(prev_scores) / len(prev_scores)
                    if score > avg_prev_score * 1.1:  # 10% higher
                        score_trend = "UP"
                    elif score < avg_prev_score * 0.9:  # 10% lower
                        score_trend = "DOWN"
                    else:
                        score_trend = "STABLE"
                elif len(prev_scores) == 1:
                    if score > prev_scores[0] * 1.1:
                        score_trend = "UP"
                    elif score < prev_scores[0] * 0.9:
                        score_trend = "DOWN"
                    else:
                        score_trend = "STABLE"

        return {
            'is_recurring': True,
            'days_since_last': days_since,
            'total_count': total_count,
            'last_alert': {
                'date': last_alert_date,
                'type': last_alert['alert_type'],
                'score': last_alert['score'] if not pd.isna(last_alert['score']) else 0
            },
            'all_alerts': stock_alerts[['date', 'alert_type', 'score']].to_dict('records'),
            'trend': trend,
            'score_trend': score_trend
        }

    except Exception as e:
        print(f"❌ Error checking recurring alert: {e}")
        return None

def send_recurring_alert(stock: str, current_alert_type: str, current_score: int, recurring_data: dict):
    """
    Send Telegram alert for recurring pattern detection.

    Args:
        stock: Stock symbol
        current_alert_type: Current alert type (BULLISH/BEARISH)
        current_score: Current alert score
        recurring_data: Data from check_recurring_alert()
    """
    # CHECK MARKET HOURS: Only send alerts between 09:15 AM - 3:30 PM
    if not is_market_hours():
        return False

    try:
        if not recurring_data or not recurring_data.get('is_recurring'):
            return

        days_since = recurring_data['days_since_last']
        total_count = recurring_data['total_count']
        last_alert = recurring_data['last_alert']
        trend = recurring_data['trend']
        score_trend = recurring_data['score_trend']

        # Build time descriptor
        if days_since == 1:
            time_desc = "Yesterday"
        elif days_since == 2:
            time_desc = "2 days ago"
        elif days_since == 3:
            time_desc = "3 days ago"
        else:
            time_desc = f"{days_since} days ago"

        # Build alert message
        emoji = "🔥" if total_count >= 3 else "🔄"

        message = f"{emoji} <b>RECURRING ALERT - {stock}</b>\n\n"

        # Current alert
        message += f"<b>Today:</b> {current_alert_type}"
        if current_score > 0:
            message += f" (Score: {current_score})"
        message += "\n"

        # Last alert
        message += f"<b>Last alert:</b> {time_desc} - {last_alert['type']}"
        if last_alert['score'] > 0:
            message += f" (Score: {int(last_alert['score'])})"
        message += "\n\n"

        # Frequency
        message += f"🔄 <b>{total_count} alerts</b> in last 7 days\n"

        # Get sector performance
        sector_info = get_sector_performance(stock, kite=engine.kite, sector_map=engine.sector_mapping)
        if sector_info:
            message += f"{sector_info}\n"

        # Get NIFTY market context
        nifty_pct = get_nifty_daily_change(kite=engine.kite)
        market_ctx = get_market_context(current_alert_type, nifty_pct)
        message += f"{market_ctx['nifty_line']}\n"

        # Trend analysis
        if "All" in trend:
            message += f"📊 {trend} - <b>Strong trend!</b>\n"
        elif "REVERSAL" in trend:
            message += f"⚠️ {trend}\n"
        else:
            message += f"📊 {trend}\n"

        # Score trend
        if score_trend:
            if score_trend == "UP":
                message += f"📈 Score trending <b>UP</b>\n"
            elif score_trend == "DOWN":
                message += f"📉 Score trending <b>DOWN</b>\n"
            else:
                message += f"📊 Score <b>STABLE</b>\n"

        message += "\n"

        # Action recommendation
        if total_count >= 3 and "All" in trend:
            message += "⚡ <b>High conviction - Sustained momentum!</b>\n"
        elif "REVERSAL" in trend:
            message += "⚠️ <b>Caution - Signal changed direction!</b>\n"
        else:
            message += "👀 <b>Monitor closely - Building pattern</b>\n"

        message += f"\n⏰ {datetime.now().strftime('%I:%M:%S %p')}"

        # Send alert
        send_telegram_message(message, parse_mode='HTML')
        print(f"🔥 RECURRING ALERT sent for {stock} ({total_count} alerts in 7 days)")

    except Exception as e:
        print(f"❌ Error sending recurring alert: {e}")

# ============================================
# MILESTONE ALERT FUNCTIONS
# Real-time alerts when stock hits alert milestones (3, 5, 10, 15, 20...)
# ============================================

def check_milestone_alert(stock: str, data_dir: str = "data") -> dict:
    """
    Check if stock has hit an alert milestone (3, 5, 10, 15, 20, 25, 30...).

    Args:
        stock: Stock symbol
        data_dir: Data directory path

    Returns:
        dict with milestone info if milestone hit, None otherwise
    """
    try:
        history_file = Path(data_dir) / "alert_history.csv"

        if not history_file.exists():
            return None

        df = pd.read_csv(history_file)
        df['date'] = pd.to_datetime(df['date'])

        # Get all alerts for this stock
        stock_alerts = df[df['stock'] == stock].copy()

        if stock_alerts.empty:
            return None

        total_count = len(stock_alerts)

        # Define milestones (3, 5, 10, 15, 20, 25, 30, 40, 50...)
        milestones = [3, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100]

        # Check if current count is a milestone
        if total_count not in milestones:
            return None

        # Get first and last alert
        stock_alerts = stock_alerts.sort_values('date')
        first_alert = stock_alerts.iloc[0]
        last_alert = stock_alerts.iloc[-1]

        # Calculate time span
        first_date = first_alert['date']
        last_date = last_alert['date']
        days_span = (last_date - first_date).days

        # Analyze pattern
        signal_types = stock_alerts['alert_type'].value_counts()
        if len(signal_types) == 1:
            pattern = f"All {signal_types.index[0]}"
        else:
            bullish_count = signal_types.get('BULLISH', 0)
            bearish_count = signal_types.get('BEARISH', 0)
            pattern = f"{bullish_count} BULLISH, {bearish_count} BEARISH"

        # Analyze score trend (if scores available)
        score_trend = None
        if not stock_alerts['score'].isna().all():
            scores = stock_alerts['score'].dropna()
            if len(scores) >= 3:
                recent_avg = scores.tail(3).mean()
                older_avg = scores.head(3).mean()

                if recent_avg > older_avg * 1.15:
                    score_trend = "UP"
                elif recent_avg < older_avg * 0.85:
                    score_trend = "DOWN"
                else:
                    score_trend = "STABLE"

        # Get recent alerts (last 3 days)
        three_days_ago = datetime.now() - timedelta(days=3)
        recent_alerts = stock_alerts[stock_alerts['date'] >= three_days_ago]
        recent_count = len(recent_alerts)

        return {
            'milestone': total_count,
            'first_alert': {
                'date': first_date.strftime('%b %d, %I:%M %p'),
                'type': first_alert['alert_type'],
                'score': first_alert['score'] if not pd.isna(first_alert['score']) else 0
            },
            'last_alert': {
                'date': last_date.strftime('%b %d, %I:%M %p'),
                'type': last_alert['alert_type'],
                'score': last_alert['score'] if not pd.isna(last_alert['score']) else 0
            },
            'days_span': days_span,
            'pattern': pattern,
            'score_trend': score_trend,
            'recent_count': recent_count
        }

    except Exception as e:
        print(f"❌ Error checking milestone alert: {e}")
        return None

def send_milestone_alert(stock: str, milestone_data: dict, kite=None):
    """
    Send Telegram alert for milestone achievement with live stock data.

    Args:
        stock: Stock symbol
        milestone_data: Milestone information from check_milestone_alert()
        kite: Kite instance for fetching live stock data
    """
    # CHECK MARKET HOURS: Only send alerts between 09:15 AM - 3:30 PM
    if not is_market_hours():
        return False

    try:
        milestone = milestone_data['milestone']

        # Get milestone emoji
        if milestone >= 20:
            emoji = "🔥🔥🔥"
        elif milestone >= 10:
            emoji = "🔥🔥"
        else:
            emoji = "🎯"

        # Build message header
        message = f"{emoji} <b>MILESTONE ALERT - {stock}</b>\n\n"
        message += f"🎯 <b>This is the {milestone}th alert for {stock}!</b>\n\n"

        # Live stock data (if kite available)
        if kite:
            try:
                quote = kite.quote(f"NSE:{stock}")
                if f"NSE:{stock}" in quote:
                    q = quote[f"NSE:{stock}"]
                    current_price = q.get('last_price', 0)
                    ohlc = q.get('ohlc', {})
                    prev_close = ohlc.get('close', 0)
                    volume = q.get('volume', 0)
                    avg_volume = q.get('average_price', 0)

                    if prev_close > 0:
                        change_pct = ((current_price - prev_close) / prev_close) * 100
                        change_emoji = "🟢" if change_pct > 0 else "🔴"

                        # Get NIFTY market context for milestone alert
                        stock_direction = "BULLISH" if change_pct > 0 else "BEARISH"
                        nifty_pct = get_nifty_daily_change(kite=kite)
                        market_ctx = get_market_context(stock_direction, nifty_pct)

                        message += f"💰 <b>Live Data:</b>\n"
                        message += f"Price: ₹{current_price:,.2f} {change_emoji}{change_pct:+.2f}%\n"

                        if volume > 0:
                            message += f"Volume: {volume:,}\n"

                        # Get sector performance
                        sector_info = get_sector_performance(stock, kite=kite, sector_map=engine.sector_mapping)
                        if sector_info:
                            message += f"{sector_info}\n"

                        # Add NIFTY market context
                        message += f"{market_ctx['nifty_line']}\n"

                        message += "\n"
            except Exception as e:
                print(f"⚠️ Could not fetch live data: {e}")

        # Timeline
        message += f"📅 <b>Timeline:</b>\n"
        message += f"• 1st alert: {milestone_data['first_alert']['date']}\n"
        message += f"• {milestone}th alert: {milestone_data['last_alert']['date']}\n"

        if milestone_data['days_span'] == 0:
            message += f"• Span: <b>Same day</b>\n\n"
        elif milestone_data['days_span'] == 1:
            message += f"• Span: <b>1 day</b>\n\n"
        else:
            message += f"• Span: <b>{milestone_data['days_span']} days</b>\n\n"

        # Pattern analysis
        message += f"📊 <b>Pattern:</b> {milestone_data['pattern']}\n"

        # Score trend
        if milestone_data['score_trend']:
            if milestone_data['score_trend'] == "UP":
                message += f"📈 Score trending <b>UP</b> 🔥\n"
            elif milestone_data['score_trend'] == "DOWN":
                message += f"📉 Score trending <b>DOWN</b>\n"
            else:
                message += f"📊 Score <b>STABLE</b>\n"

        # Recent activity
        if milestone_data['recent_count'] >= 5:
            message += f"⚡ <b>{milestone_data['recent_count']} alerts in last 3 days!</b>\n"

        message += "\n"

        # Action recommendation based on milestone
        if milestone >= 20:
            message += "🔥 <b>EXTREME HIGH CONVICTION!</b>\n"
            message += "💡 This stock is showing exceptional momentum\n"
        elif milestone >= 10:
            message += "⚡ <b>HIGH CONVICTION PATTERN!</b>\n"
            message += "💡 Monitor closely - sustained momentum\n"
        elif milestone >= 5:
            message += "👀 <b>Building strong pattern</b>\n"
            message += "💡 Watch for continuation\n"
        else:
            message += "🎯 <b>Pattern emerging</b>\n"
            message += "💡 Track this stock closely\n"

        message += f"\n⏰ {datetime.now().strftime('%I:%M:%S %p')}"

        # Send alert
        send_telegram_message(message, parse_mode='HTML')
        print(f"🎯 MILESTONE ALERT sent for {stock} ({milestone} alerts)")

    except Exception as e:
        print(f"❌ Error sending milestone alert: {e}")

# ============================================
# STOCK FLOW TRACKING TO CSV
# Daily tracking of all stocks with significant moves (±2%)
# ============================================

def save_stock_flow_snapshot(stocks_data: dict, sector_mapping: dict, data_dir: str = "data/flow_tracking"):
    """
    Save snapshot of all stocks with abs(change_pct) >= 2.0% to daily CSV file.

    Updates every 5 minutes during market hours to track:
    - Which high % moves had low flow (missed opportunities)
    - Flow patterns for different market caps
    - Optimal threshold analysis

    File: stock_flow_tracking_YYYY-MM-DD.csv
    """
    try:
        # Only track during market hours
        if not is_market_hours():
            return

        now = datetime.now()
        date_str = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M:%S')
        timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')

        # Create directory if needed
        os.makedirs(data_dir, exist_ok=True)

        # Daily file
        csv_file = Path(data_dir) / f"stock_flow_tracking_{date_str}.csv"

        # Check if file exists to determine if we need headers
        file_exists = csv_file.exists()

        # Prepare rows for stocks meeting criteria
        rows_to_save = []

        # Calculate rankings
        sorted_by_flow = sorted(stocks_data.items(), key=lambda x: abs(x[1].get("net_flow", 0)), reverse=True)
        stock_ranks = {name: idx + 1 for idx, (name, _) in enumerate(sorted_by_flow)}
        top_10_stocks = set([name for name, _ in sorted_by_flow[:10]])

        for stock_name, data in stocks_data.items():
            change_pct = data.get('change_pct')

            # Only save if abs(change_pct) >= 2.0
            if change_pct is None or abs(change_pct) < 2.0:
                continue

            price = data.get('price', 0)
            ce_flow = data.get('ce_flow', 0)
            pe_flow = data.get('pe_flow', 0)
            net_flow = data.get('net_flow', 0)
            sector = sector_mapping.get(stock_name.upper(), 'N/A')
            rank = stock_ranks.get(stock_name, 999)
            in_top_10 = stock_name in top_10_stocks

            # Check if alert was sent (would have been sent if conditions met)
            alerted = False
            alert_type = ''

            if change_pct > 1.0 and net_flow > 100:
                alerted = True
                alert_type = 'BULLISH'
            elif change_pct < -1.0 and net_flow < -50:
                alerted = True
                alert_type = 'BEARISH'

            # Calculate CE/PE ratio: IF(pe_flow>0, ce_flow/pe_flow, IF(ce_flow>0, 999, 0))
            if pe_flow > 0:
                ce_pe_ratio = ce_flow / pe_flow
            elif ce_flow > 0:
                ce_pe_ratio = 999
            else:
                ce_pe_ratio = 0

            row = {
                'timestamp': timestamp_str,
                'date': date_str,
                'time': time_str,
                'stock': stock_name,
                'price': f"{price:.2f}",
                'change_pct': f"{change_pct:.2f}",
                'ce_flow': f"{ce_flow:.1f}",
                'pe_flow': f"{pe_flow:.1f}",
                'net_flow': f"{net_flow:.1f}",
                'sector': sector,
                'rank': rank,
                'in_top_10': in_top_10,
                'alerted': alerted,
                'alert_type': alert_type,
                'ce_pe_ratio': f"{ce_pe_ratio:.2f}"
            }
            rows_to_save.append(row)

        # Write to CSV
        if rows_to_save:
            import csv

            with open(csv_file, 'a', newline='') as f:
                fieldnames = ['timestamp', 'date', 'time', 'stock', 'price', 'change_pct',
                             'ce_flow', 'pe_flow', 'net_flow', 'sector', 'rank',
                             'in_top_10', 'alerted', 'alert_type', 'ce_pe_ratio']
                writer = csv.DictWriter(f, fieldnames=fieldnames)

                # Write header only if new file
                if not file_exists:
                    writer.writeheader()

                # Write all rows
                writer.writerows(rows_to_save)

            print(f"📊 Flow tracking: Saved {len(rows_to_save)} stocks with ±2% moves to {csv_file.name}")

    except Exception as e:
        print(f"❌ Error saving stock flow snapshot: {e}")

# ============================================
# VOLUME HISTORY TRACKING FOR UNUSUAL ACTIVITY DETECTION
# Stores 10-day rolling volume to identify relative spikes
# ============================================

def save_daily_volume_snapshot(stocks_data: dict, data_dir: str = "data/volume_history"):
    """
    Save end-of-day volume snapshot for each stock to calculate rolling averages.

    File: volume_history.json
    Structure: {
        "RELIANCE": {
            "2026-01-07": {"ce_vol": 150000, "pe_vol": 50000, "total_vol": 200000},
            "2026-01-06": {"ce_vol": 180000, "pe_vol": 60000, "total_vol": 240000},
            ...
        }
    }

    Called at end of market day to snapshot today's final volumes.
    """
    try:
        os.makedirs(data_dir, exist_ok=True)
        history_file = Path(data_dir) / "volume_history.json"

        # Load existing history
        if history_file.exists():
            with open(history_file, 'r') as f:
                history = json.load(f)
        else:
            history = {}

        date_str = datetime.now().strftime('%Y-%m-%d')

        # Update history for each stock
        for stock_name, data in stocks_data.items():
            ce_vol = abs(data.get('ce_flow', 0))
            pe_vol = abs(data.get('pe_flow', 0))
            total_vol = ce_vol + pe_vol

            # Initialize stock if not exists
            if stock_name not in history:
                history[stock_name] = {}

            # Save today's volume
            history[stock_name][date_str] = {
                'ce_vol': ce_vol,
                'pe_vol': pe_vol,
                'total_vol': total_vol
            }

            # Keep only last 15 days (for 10-day rolling avg with buffer)
            dates = sorted(history[stock_name].keys(), reverse=True)
            if len(dates) > 15:
                for old_date in dates[15:]:
                    del history[stock_name][old_date]

        # Save updated history
        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2)

        print(f"📊 Volume history: Saved snapshots for {len(stocks_data)} stocks")

    except Exception as e:
        print(f"❌ Error saving volume history: {e}")

def load_volume_history(data_dir: str = "data/volume_history") -> dict:
    """Load volume history from JSON file."""
    try:
        history_file = Path(data_dir) / "volume_history.json"

        if history_file.exists():
            with open(history_file, 'r') as f:
                return json.load(f)
        else:
            return {}
    except Exception as e:
        print(f"❌ Error loading volume history: {e}")
        return {}

def fetch_historical_volume_from_kite(stock_name: str, kite, token_meta, days: int = 10) -> float:
    """
    Fetch last N days of volume data from Kite API for a stock's options.

    Returns: Average daily volume over the period, or 0 if data unavailable.
    """
    try:
        from_date = datetime.now() - timedelta(days=days+2)  # Extra buffer for weekends
        to_date = datetime.now() - timedelta(days=1)  # Yesterday (exclude today)

        # Get all option tokens for this stock
        stock_options = token_meta[
            (token_meta["name"] == stock_name) &
            (token_meta["instrument_type"].isin(["CE", "PE"]))
        ].copy()

        if stock_options.empty:
            return 0

        # Take sample of strikes to avoid too many API calls (ATM ±5 strikes)
        # Limit to 20 strikes max (10 CE + 10 PE)
        ce_options = stock_options[stock_options["instrument_type"] == "CE"].head(10)
        pe_options = stock_options[stock_options["instrument_type"] == "PE"].head(10)
        sample_options = pd.concat([ce_options, pe_options])

        daily_volumes = {}  # {date: total_volume}

        for _, option in sample_options.iterrows():
            try:
                token = int(option["instrument_token"])

                # Fetch historical data
                hist_data = kite.historical_data(
                    instrument_token=token,
                    from_date=from_date,
                    to_date=to_date,
                    interval="day"
                )

                if not hist_data:
                    continue

                # Aggregate volumes by date
                for candle in hist_data:
                    date_str = candle['date'].strftime('%Y-%m-%d') if isinstance(candle['date'], datetime) else str(candle['date'])
                    volume = candle.get('volume', 0)

                    if date_str not in daily_volumes:
                        daily_volumes[date_str] = 0
                    daily_volumes[date_str] += volume

            except Exception as e:
                # Skip individual strikes that fail
                continue

        if not daily_volumes:
            return 0

        # Calculate average daily volume
        volumes = list(daily_volumes.values())
        avg_volume = sum(volumes) / len(volumes) if volumes else 0

        return avg_volume

    except Exception as e:
        print(f"❌ Error fetching historical volume for {stock_name}: {e}")
        return 0

def calculate_volume_spike_ratio(stocks_data: dict, volume_history: dict, kite=None, token_meta=None) -> list:
    """
    Calculate volume spike ratio for each stock (today vs 10-day average).

    Fallback logic:
    1. Try local volume_history first (fast)
    2. If insufficient (<5 days), fetch from Kite API (immediate, works day 1)

    Returns list of stocks with unusual volume (ratio > 2.0x) sorted by ratio.
    """
    try:
        unusual_stocks = []
        today_date = datetime.now().strftime('%Y-%m-%d')

        for stock_name, data in stocks_data.items():
            # Today's volume
            ce_vol_today = abs(data.get('ce_flow', 0))
            pe_vol_today = abs(data.get('pe_flow', 0))
            total_vol_today = ce_vol_today + pe_vol_today

            # Skip if no volume today
            if total_vol_today == 0:
                continue

            # Get historical data from local storage
            stock_history = volume_history.get(stock_name, {})

            # Calculate 10-day average (excluding today)
            historical_volumes = []
            for date_str, vol_data in stock_history.items():
                if date_str != today_date:  # Exclude today
                    historical_volumes.append(vol_data.get('total_vol', 0))

            # FALLBACK: If insufficient local history, fetch from Kite API
            avg_volume = 0
            if len(historical_volumes) >= 5:
                # Use local history (fast path)
                recent_volumes = historical_volumes[-10:] if len(historical_volumes) >= 10 else historical_volumes
                avg_volume = sum(recent_volumes) / len(recent_volumes)
            elif kite and token_meta is not None:
                # Fetch from Kite API (works from day 1!)
                print(f"📡 Fetching historical volume for {stock_name} from Kite API...")
                avg_volume = fetch_historical_volume_from_kite(stock_name, kite, token_meta, days=10)
            else:
                # No data available
                continue

            # Avoid division by zero
            if avg_volume == 0:
                continue

            # Calculate spike ratio
            spike_ratio = total_vol_today / avg_volume

            # Only include if unusual (>2.0x normal)
            if spike_ratio >= 2.0:
                unusual_stocks.append({
                    'stock': stock_name,
                    'today_volume': total_vol_today,
                    'avg_volume': avg_volume,
                    'spike_ratio': spike_ratio,
                    'price': data.get('price'),
                    'change_pct': data.get('change_pct'),
                    'ce_flow': data.get('ce_flow', 0),
                    'pe_flow': data.get('pe_flow', 0),
                    'net_flow': data.get('net_flow', 0)
                })

        # Sort by spike ratio (highest relative spike first)
        unusual_stocks.sort(key=lambda x: x['spike_ratio'], reverse=True)

        return unusual_stocks

    except Exception as e:
        print(f"❌ Error calculating volume spike ratios: {e}")
        return []

# ============================================
# STOCK ENTRY TRACKING FUNCTIONS
# Track how many times stocks enter Top 10 & Volume Spikes lists
# ============================================

def load_stock_entry_tracking(data_dir: str = "data"):
    """
    Load stock entry tracking data from JSON file.
    Tracks separate counters for Top 10 Stocks and Volume Spikes lists.
    """
    try:
        tracking_file = Path(data_dir) / "stock_entry_tracking.json"

        if tracking_file.exists():
            with open(tracking_file, 'r') as f:
                data = json.load(f)
            return data
        else:
            # Initialize new tracking structure
            return {
                "top10_stocks": {},      # {stock: {count: int, in_list: bool, last_seen: str}}
                "volume_spikes": {},     # {stock: {count: int, in_list: bool, last_seen: str}}
                "last_expiry_reset": None,
                "current_expiry": None
            }
    except Exception as e:
        print(f"❌ Error loading stock entry tracking: {e}")
        return {
            "top10_stocks": {},
            "volume_spikes": {},
            "last_expiry_reset": None,
            "current_expiry": None
        }

def save_stock_entry_tracking(tracking_data: dict, data_dir: str = "data"):
    """Save stock entry tracking data to JSON file."""
    try:
        os.makedirs(data_dir, exist_ok=True)
        tracking_file = Path(data_dir) / "stock_entry_tracking.json"

        with open(tracking_file, 'w') as f:
            json.dump(tracking_data, f, indent=2)
    except Exception as e:
        print(f"❌ Error saving stock entry tracking: {e}")

def get_current_month_expiry(ins_df: pd.DataFrame) -> Optional[datetime]:
    """
    Get current month NIFTY expiry date from live options data.
    Returns the nearest upcoming expiry (current month).
    """
    try:
        if ins_df.empty:
            return None

        # Get NIFTY options data
        nifty_options = ins_df[
            (ins_df['name'] == 'NIFTY') &
            (ins_df['instrument_type'] == 'OPT')
        ].copy()

        if nifty_options.empty:
            return None

        # Get unique expiry dates
        expiries = pd.to_datetime(nifty_options['expiry']).unique()
        expiries = sorted([exp for exp in expiries if exp >= datetime.now()])

        if expiries:
            # First expiry is current month
            return expiries[0]

        return None
    except Exception as e:
        print(f"❌ Error getting current month expiry: {e}")
        return None

def check_and_reset_if_expired(tracking_data: dict, ins_df: pd.DataFrame) -> dict:
    """
    Check if current month expiry has passed and reset counters if needed.
    Updates current_expiry from live data.
    """
    try:
        current_expiry = get_current_month_expiry(ins_df)

        if not current_expiry:
            return tracking_data

        current_expiry_date = current_expiry.date()
        today = datetime.now().date()

        # Store current expiry in tracking data
        tracking_data["current_expiry"] = current_expiry_date.isoformat()

        # Check if we need to reset (expiry has passed)
        last_reset = tracking_data.get("last_expiry_reset")

        if last_reset:
            last_reset_date = datetime.fromisoformat(last_reset).date()

            # If today > expiry AND we haven't reset since last expiry
            if today > current_expiry_date and last_reset_date <= current_expiry_date:
                print(f"🔄 Monthly expiry passed ({current_expiry_date}) - Resetting stock entry counters")
                tracking_data["top10_stocks"] = {}
                tracking_data["volume_spikes"] = {}
                tracking_data["last_expiry_reset"] = today.isoformat()
        else:
            # First time setup - no reset needed, just store the date
            tracking_data["last_expiry_reset"] = today.isoformat()

        return tracking_data
    except Exception as e:
        print(f"❌ Error checking expiry reset: {e}")
        return tracking_data

def update_stock_entry_count(tracking_data: dict, list_type: str, current_stocks: list) -> dict:
    """
    Update stock entry counts for a specific list.

    Args:
        tracking_data: Current tracking data
        list_type: "top10_stocks" or "volume_spikes"
        current_stocks: List of stock symbols currently in the list

    Returns:
        Updated tracking data
    """
    try:
        if list_type not in tracking_data:
            tracking_data[list_type] = {}

        list_data = tracking_data[list_type]
        current_time = datetime.now().isoformat()

        # Convert current_stocks to set for faster lookup
        current_stocks_set = set(current_stocks)

        # Check each stock currently in the list
        for stock in current_stocks:
            if stock not in list_data:
                # New stock - initialize
                list_data[stock] = {
                    "count": 1,
                    "in_list": True,
                    "last_seen": current_time
                }
                print(f"📊 {list_type}: {stock} entered list (count: 1)")
            else:
                # Stock exists in tracking
                if not list_data[stock]["in_list"]:
                    # Stock was OUT, now it's IN - increment count
                    list_data[stock]["count"] += 1
                    list_data[stock]["in_list"] = True
                    list_data[stock]["last_seen"] = current_time
                    print(f"📊 {list_type}: {stock} re-entered list (count: {list_data[stock]['count']})")
                else:
                    # Stock was IN, still IN - no change, just update timestamp
                    list_data[stock]["last_seen"] = current_time

        # Mark stocks that are no longer in the list
        for stock in list_data:
            if stock not in current_stocks_set and list_data[stock]["in_list"]:
                list_data[stock]["in_list"] = False
                print(f"📊 {list_type}: {stock} exited list")

        tracking_data[list_type] = list_data
        return tracking_data
    except Exception as e:
        print(f"❌ Error updating stock entry count: {e}")
        return tracking_data

def get_stock_display_name(stock: str, list_type: str, tracking_data: dict) -> str:
    """
    Get stock display name with entry count in parentheses.

    Args:
        stock: Stock symbol
        list_type: "top10_stocks" or "volume_spikes"
        tracking_data: Current tracking data

    Returns:
        Formatted string like "SAIL (3)" or "SAIL" if no tracking data
    """
    try:
        if list_type in tracking_data and stock in tracking_data[list_type]:
            count = tracking_data[list_type][stock]["count"]
            return f"{stock} ({count})"
        else:
            return stock
    except Exception as e:
        return stock

def discover_indices_with_fo(ins_df: pd.DataFrame) -> list:
    """
    Discover all whitelisted indices from instruments data.
    Includes indices with F&O, options only, or spot data.
    """
    discovered_indices = set()

    # Check futures segments (for F&O indices)
    fut = ins_df[ins_df["segment"].isin(DERIV_FUT_SEGMENTS)].copy()
    if not fut.empty:
        fut_names = set(fut["name"].dropna().unique().tolist())
        discovered_indices.update(fut_names)

    # Check options segments (for indices with only options)
    opt = ins_df[ins_df["segment"].isin(DERIV_OPT_SEGMENTS)].copy()
    if not opt.empty:
        # Get index names from options data
        opt_names = set(opt["name"].dropna().unique().tolist())
        discovered_indices.update(opt_names)

    # Check spot/index segments (for indices without derivatives)
    spot_segments = {"NSE", "BSE", "INDICES"}
    spot = ins_df[ins_df["segment"].isin(spot_segments)].copy()
    if not spot.empty:
        spot_names = set(spot["name"].dropna().unique().tolist())
        discovered_indices.update(spot_names)

    # Filter to only whitelisted indices
    whitelisted = [n for n in discovered_indices if n in INDEX_NAME_WHITELIST]

    print(f"📊 Discovered {len(whitelisted)} indices from whitelist: {sorted(whitelisted)}")

    return sorted(whitelisted)

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

def get_sector_emoji(sector_name: str) -> str:
    """Get emoji for sector based on name."""
    sector_emojis = {
        "NIFTY BANK": "🏦",
        "NIFTY IT": "💻",
        "NIFTY PHARMA": "💊",
        "NIFTY METAL": "🏭",
        "NIFTY AUTO": "🚗",
        "NIFTY FMCG": "🛒",
        "NIFTY ENERGY": "⚡",
        "NIFTY OIL & GAS": "🛢️",
        "NIFTY REALTY": "🏢",
        "NIFTY PSU BANK": "🏛️",
        "NIFTY INFRA": "🏗️",
        "NIFTY MEDIA": "📺",
        "NIFTY HEALTHCARE": "🏥",
        "NIFTY FIN SERVICE": "💰",
        "NIFTY MIDCAP 50": "📊",
        "NIFTY 50": "📈"
    }

    # Try exact match first
    if sector_name in sector_emojis:
        return sector_emojis[sector_name]

    # Try partial match
    for key, emoji in sector_emojis.items():
        if key in sector_name or sector_name in key:
            return emoji

    # Default
    return "📊"

def get_sector_display_name(sector_name: str) -> str:
    """Get clean display name for sector."""
    # Remove "NIFTY" prefix for cleaner display
    if sector_name.startswith("NIFTY "):
        return sector_name[6:]  # Remove "NIFTY "
    return sector_name

def get_sector_performance(stock_name: str, kite=None, sector_map=None) -> str:
    """
    Get sector performance for a stock.

    Args:
        stock_name: Stock symbol (e.g., "RELIANCE")
        kite: Kite instance for fetching live data
        sector_map: Sector mapping dictionary

    Returns:
        Formatted string like "🏭 Sector: Metals & Mining (🟢+1.2%)" or ""
    """
    try:
        if not kite or not sector_map:
            return ""

        # Get sector for stock
        sector_index = sector_map.get(stock_name.upper(), None)
        if not sector_index:
            return ""

        # Fetch sector index performance
        try:
            quote = kite.quote(f"NSE:{sector_index}")
            if f"NSE:{sector_index}" in quote:
                q = quote[f"NSE:{sector_index}"]
                ohlc = q.get('ohlc', {})
                last_price = q.get('last_price', 0)
                prev_close = ohlc.get('close', 0)

                if prev_close > 0:
                    sector_pct = ((last_price - prev_close) / prev_close) * 100
                    emoji = get_sector_emoji(sector_index)
                    display_name = get_sector_display_name(sector_index)
                    change_emoji = "🟢" if sector_pct >= 0 else "🔴"

                    return f"{emoji} Sector: {display_name} ({change_emoji}{sector_pct:+.2f}%)"
        except Exception as e:
            # Sector index might not be available, return basic info
            emoji = get_sector_emoji(sector_index)
            display_name = get_sector_display_name(sector_index)
            return f"{emoji} Sector: {display_name}"

    except Exception as e:
        print(f"⚠️ Error getting sector performance for {stock_name}: {e}")

    return ""

def get_nifty_daily_change(kite=None) -> float:
    """
    Get NIFTY 50 daily % change.

    Returns:
        Float with NIFTY daily change % (e.g., 0.35 for +0.35%)
        Returns 0.0 if unable to fetch
    """
    try:
        if not kite:
            return 0.0

        # Fetch NIFTY 50 spot index
        quote = kite.quote("NSE:NIFTY 50")
        if "NSE:NIFTY 50" in quote:
            q = quote["NSE:NIFTY 50"]
            last_price = q.get('last_price', 0)
            ohlc = q.get('ohlc', {})
            prev_close = ohlc.get('close', 0)

            if prev_close > 0:
                nifty_pct = ((last_price - prev_close) / prev_close) * 100
                return nifty_pct

    except Exception as e:
        print(f"⚠️ Error getting NIFTY daily change: {e}")

    return 0.0

def get_market_context(stock_alert_type: str, nifty_pct: float) -> dict:
    """
    Determine market context for stock alert based on NIFTY movement.

    Args:
        stock_alert_type: "BULLISH" or "BEARISH"
        nifty_pct: NIFTY daily change % (e.g., 0.35 for +0.35%)

    Returns:
        dict with:
        - upgraded_signal: "MORE BULLISH", "MORE BEARISH", or original
        - emoji: Alert emoji with modifications
        - tag: Market context tag (e.g., "[Market Tailwind]")
        - nifty_line: Formatted NIFTY info line
        - interpretation_suffix: Additional interpretation text
    """
    THRESHOLD = 0.10  # 0.10% threshold

    context = {
        'upgraded_signal': '',
        'emoji': '',
        'tag': '',
        'nifty_line': '',
        'interpretation_suffix': ''
    }

    # Format NIFTY line
    nifty_emoji = "📈" if nifty_pct >= 0 else "📉"
    nifty_color = "🟢" if nifty_pct >= 0 else "🔴"
    context['nifty_line'] = f"{nifty_emoji} NIFTY: {nifty_color}{nifty_pct:+.2f}%"

    if stock_alert_type == "BULLISH":
        if nifty_pct >= THRESHOLD:
            # Market confirming bullish move
            context['upgraded_signal'] = "MORE BULLISH"
            context['emoji'] = "🟢🟢"
            context['tag'] = "[Market Tailwind]"
            context['nifty_line'] += " ✓ Market supporting"
            context['interpretation_suffix'] = " + Market momentum"
        elif nifty_pct <= -THRESHOLD:
            # Stock bullish despite bearish market
            context['upgraded_signal'] = "STRONG BULLISH"
            context['emoji'] = "🟢💪"
            context['tag'] = "[Against Market!]"
            context['nifty_line'] += " 💪 Strong independent move!"
            context['interpretation_suffix'] = " + Fighting market"
        else:
            # Stock outperforming flat market
            context['upgraded_signal'] = "STRONG BULLISH"
            context['emoji'] = "🟢⭐"
            context['tag'] = "[Relative Strength]"
            context['nifty_line'] += " ⚠️ Stock outperforming"
            context['interpretation_suffix'] = " + Relative strength"

    elif stock_alert_type == "BEARISH":
        if nifty_pct <= -THRESHOLD:
            # Market confirming bearish move
            context['upgraded_signal'] = "MORE BEARISH"
            context['emoji'] = "🔴🔴"
            context['tag'] = "[Market Confirming]"
            context['nifty_line'] += " ✓ Market confirming downtrend"
            context['interpretation_suffix'] = " + Market weakness"
        elif nifty_pct >= THRESHOLD:
            # Stock bearish despite bullish market
            context['upgraded_signal'] = "STRONG BEARISH"
            context['emoji'] = "🔴⚠️"
            context['tag'] = "[Against Market!]"
            context['nifty_line'] += " ⚠️ Weak despite market strength!"
            context['interpretation_suffix'] = " + Relative weakness"
        else:
            # Stock underperforming flat market
            context['upgraded_signal'] = "STRONG BEARISH"
            context['emoji'] = "🔴⚠️"
            context['tag'] = "[Relative Weakness]"
            context['nifty_line'] += " ⚠️ Stock underperforming"
            context['interpretation_suffix'] = " + Relative weakness"

    return context


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

def auto_backup_after_market_close():
    """
    Automatically create backup after market closes
    - Runs once per day after 3:30 PM
    - Only on weekdays (Monday-Friday)
    - Checks if backup already exists for today
    """
    now = datetime.now()

    # Only on weekdays (0=Monday, 4=Friday)
    if now.weekday() > 4:
        return False

    # Only after 3:30 PM (market closes at 3:30 PM)
    if now.hour < 15 or (now.hour == 15 and now.minute < 30):
        return False

    # Check if backup already exists for today
    backup_dir = Path.home() / "trading_backups"
    today_str = now.strftime("%Y-%m-%d")

    if backup_dir.exists():
        # Check if any backup exists for today
        existing_backups = list(backup_dir.glob(f"trading_backup_{today_str}_*.tar.gz"))
        if existing_backups:
            # Backup already done today
            return False

    # Create backup
    try:
        print("\n" + "="*50)
        print("🤖 AUTO-BACKUP: Market closed, creating backup...")
        print("="*50)

        # Create backup directory
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Timestamp for filename
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        backup_file = backup_dir / f"trading_backup_{timestamp}.tar.gz"

        # Items to backup
        backup_items = []
        data_dir = Path("data")
        cache_dir = Path(".cache")

        if data_dir.exists():
            backup_items.append("data")
        if cache_dir.exists():
            backup_items.append(".cache")

        if not backup_items:
            print("⚠️ No data to backup yet")
            return False

        # Create backup using tar
        import subprocess
        cmd = ["tar", "-czf", str(backup_file)] + backup_items
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            backup_size = backup_file.stat().st_size / (1024 * 1024)  # MB
            print(f"✅ Backup created successfully!")
            print(f"   Location: {backup_file}")
            print(f"   Size: {backup_size:.1f} MB")

            # Clean up old backups (keep last 30)
            all_backups = sorted(backup_dir.glob("trading_backup_*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
            if len(all_backups) > 30:
                for old_backup in all_backups[30:]:
                    old_backup.unlink()
                    print(f"🗑️ Removed old backup: {old_backup.name}")

            print(f"📊 Total backups: {min(len(all_backups), 30)}")
            print("="*50 + "\n")
            return True
        else:
            print(f"❌ Backup failed: {result.stderr}")
            return False

    except Exception as e:
        print(f"❌ Auto-backup error: {e}")
        import traceback
        traceback.print_exc()
        return False

def polling_loop():
    print("\n" + "="*50)
    print("STARTING LIVE MOMENTUM TRACKER")
    print("Polling every 10 seconds with actionable alerts")
    print("="*50 + "\n")

    current_date = datetime.now().date()
    daily_summary_sent = False  # Track if daily summary sent today

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

                # Reset smart alert tracking for new day
                engine.alert_cooldowns.clear()
                engine.daily_score_history.clear()
                engine.nifty_momentum_state = None
                engine.nifty_momentum_last_alert = None
                daily_summary_sent = False
                print("✅ Smart alert tracking reset for new day")

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

                # ====================
                # MOMENTUM STOCKS TRACKING
                # ====================
                momentum_tracking = load_momentum_tracking()

                # Check each stock for momentum conditions
                for stock_name, stock_data in stocks_data.items():
                    stock_price = stock_data.get('price')
                    if stock_price is None:
                        continue

                    # Check momentum condition
                    momentum_signal = check_momentum_conditions(stock_name, stock_price)

                    if momentum_signal:
                        # Initialize tracking for this stock if needed
                        if stock_name not in momentum_tracking:
                            momentum_tracking[stock_name] = {'bullish': 0, 'bearish': 0}

                        # Increment count based on signal
                        if momentum_signal == 'BULLISH':
                            momentum_tracking[stock_name]['bullish'] += 1
                            print(f"🟢 MOMENTUM: {stock_name} Bullish count = {momentum_tracking[stock_name]['bullish']}")
                        elif momentum_signal == 'BEARISH':
                            momentum_tracking[stock_name]['bearish'] += 1
                            print(f"🔴 MOMENTUM: {stock_name} Bearish count = {momentum_tracking[stock_name]['bearish']}")

                # Save updated tracking
                if momentum_tracking:
                    save_momentum_tracking(momentum_tracking)

                # Store in session state for UI
                st.session_state.momentum_tracking = momentum_tracking

                # ====================
                # SMART SCORING ALERT SYSTEM
                # ====================
                # Build Top 10 Stocks list (sorted by net_flow)
                top_10_stocks = sorted(
                    [(name, data) for name, data in stocks_data.items() if data.get('net_flow') is not None],
                    key=lambda x: abs(x[1]['net_flow']),
                    reverse=True
                )[:10]

                # Build Volume Spikes list (stocks by total activity: ce_flow + pe_flow)
                volume_spikes = sorted(
                    [(name, data) for name, data in stocks_data.items()
                     if data.get('ce_flow') is not None and data.get('pe_flow') is not None],
                    key=lambda x: x[1]['ce_flow'] + x[1]['pe_flow'],
                    reverse=True
                )[:10]

                # ============================================
                # STOCK ENTRY TRACKING (Top 10 & Volume Spikes)
                # ============================================
                # Track how many times stocks enter these lists (resets at monthly expiry)
                try:
                    # Load tracking data
                    stock_entry_tracking = load_stock_entry_tracking()

                    # Check if monthly expiry passed and reset if needed
                    stock_entry_tracking = check_and_reset_if_expired(stock_entry_tracking, engine.ins_df)

                    # Update Top 10 Stocks tracking
                    top_10_stock_names = [name for name, _ in top_10_stocks]
                    stock_entry_tracking = update_stock_entry_count(
                        stock_entry_tracking,
                        "top10_stocks",
                        top_10_stock_names
                    )

                    # Update Volume Spikes tracking
                    volume_spike_names = [name for name, _ in volume_spikes]
                    stock_entry_tracking = update_stock_entry_count(
                        stock_entry_tracking,
                        "volume_spikes",
                        volume_spike_names
                    )

                    # Save tracking data
                    save_stock_entry_tracking(stock_entry_tracking)

                    # Store in session state for UI access
                    st.session_state.stock_entry_tracking = stock_entry_tracking

                except Exception as e:
                    print(f"❌ Error in stock entry tracking: {e}")
                    import traceback
                    traceback.print_exc()

                # ============================================
                # STOCK CONFLUENCE TRACKING (3/3 Sections)
                # ============================================
                # Initialize confluence tracking in session state
                if 'stock_confluence_counts' not in st.session_state:
                    st.session_state.stock_confluence_counts = {}

                # Get stocks in all 3 sections
                top_10_names = set([name for name, _ in top_10_stocks])
                volume_spike_names = set([name for name, _ in volume_spikes])

                # Get Chartink alert stocks (from Gmail)
                chartink_stocks = set()
                if hasattr(st.session_state, 'chartink_alerts') and st.session_state.chartink_alerts:
                    for alert in st.session_state.chartink_alerts:
                        # Each alert has 'stocks' field which is a list
                        if 'stocks' in alert and alert['stocks']:
                            chartink_stocks.update(alert['stocks'])

                # Find stocks in ALL 3 sections
                confluence_stocks = top_10_names & volume_spike_names & chartink_stocks

                # Update counts
                current_counts = {}
                for stock_name in confluence_stocks:
                    if stock_name in st.session_state.stock_confluence_counts:
                        # Increment count
                        current_counts[stock_name] = st.session_state.stock_confluence_counts[stock_name] + 1
                    else:
                        # New stock
                        current_counts[stock_name] = 1

                # Check if list has changed
                list_changed = (set(current_counts.keys()) != set(st.session_state.stock_confluence_counts.keys())) or \
                               any(current_counts.get(s) != st.session_state.stock_confluence_counts.get(s) for s in current_counts)

                # Update session state
                st.session_state.stock_confluence_counts = current_counts

                # Send alert if list changed (Option 1: Alert on EVERY change)
                if list_changed and current_counts:
                    send_stock_confluence_alert(current_counts)

                # Calculate scores for all stocks
                all_scores = []
                now = datetime.now()

                for stock_name, stock_data in stocks_data.items():
                    # Skip if missing price or change_pct
                    if stock_data.get('price') is None or stock_data.get('change_pct') is None:
                        continue

                    # Calculate score
                    score_result = calculate_stock_score(
                        stock_name,
                        top_10_stocks,
                        volume_spikes,
                        momentum_tracking,
                        stocks_data
                    )

                    # Store score for daily summary
                    all_scores.append({
                        'stock_name': stock_name,
                        'score': score_result['total_score'],
                        'signal_strength': score_result['signal_strength'],
                        'num_lists': score_result['num_lists'],
                        'timestamp': now
                    })

                    # Check if score meets alert threshold (≥50)
                    if score_result['total_score'] >= 50:
                        # Check cooldown (5 minutes = 300 seconds)
                        last_alert_time = engine.alert_cooldowns.get(stock_name)
                        if last_alert_time:
                            time_since_alert = (now - last_alert_time).total_seconds()
                            if time_since_alert < 300:  # 5 minutes
                                continue  # Skip - still in cooldown

                        # Get momentum data for this stock
                        momentum_data = momentum_tracking.get(stock_name, {'bullish': 0, 'bearish': 0})

                        # Get volume spike data if present
                        volume_spike_data = None
                        for name, data in volume_spikes:
                            if name == stock_name:
                                volume_spike_data = data
                                break

                        # Get rank in top 10 stocks
                        top10_rank = None
                        for idx, (name, _) in enumerate(top_10_stocks, 1):
                            if name == stock_name:
                                top10_rank = idx
                                break

                        # Create alert message
                        alert_message = create_smart_alert_message(
                            stock_name,
                            score_result,
                            momentum_data,
                            volume_spike_data,
                            top10_rank
                        )

                        # Send Telegram alert
                        try:
                            send_telegram_message(alert_message, parse_mode='HTML')
                            print(f"📢 SMART ALERT: {stock_name} - Score: {score_result['total_score']:.0f} ({score_result['signal_strength']})")

                            # Determine alert type from signal strength
                            alert_type = "BULLISH" if score_result['signal_strength'] in ['VERY STRONG', 'STRONG'] else "NEUTRAL"

                            # Save to alert history for next-day follow-up tracking
                            save_alert_to_history(
                                stock=stock_name,
                                alert_type=alert_type,
                                score=int(score_result['total_score']),
                                price=stock_data.get('price', 0)
                            )

                            # Check for recurring alert pattern (last 7 days)
                            recurring_data = check_recurring_alert(
                                stock_name,
                                alert_type,
                                int(score_result['total_score'])
                            )
                            if recurring_data:
                                send_recurring_alert(
                                    stock_name,
                                    alert_type,
                                    int(score_result['total_score']),
                                    recurring_data
                                )

                            # Check for milestone achievement (3, 5, 10, 15, 20...)
                            milestone_data = check_milestone_alert(stock_name)
                            if milestone_data:
                                send_milestone_alert(stock_name, milestone_data, kite=kite)

                            # Update cooldown
                            engine.alert_cooldowns[stock_name] = now
                        except Exception as e:
                            print(f"❌ Failed to send smart alert for {stock_name}: {e}")

                # Store scores in session state and engine
                st.session_state.smart_scores = all_scores
                engine.daily_score_history.extend(all_scores)

                # ====================
                # DAILY SUMMARY AT MARKET CLOSE
                # ====================
                # Send daily summary at 3:30 PM (market close) - only once per day
                if not daily_summary_sent and now.hour == 15 and now.minute >= 30:
                    if engine.daily_score_history:
                        try:
                            summary_message = generate_daily_summary(engine.daily_score_history, stocks_data)
                            send_telegram_message(summary_message, parse_mode='HTML')
                            print(f"📊 DAILY SUMMARY sent at {now.strftime('%H:%M:%S')}")
                            daily_summary_sent = True
                        except Exception as e:
                            print(f"❌ Failed to send daily summary: {e}")

                # ====================
                # NIFTY MOMENTUM ALERT SYSTEM
                # ====================
                # Calculate NIFTY momentum score and send alerts for state changes
                try:
                    # Get VWAP/SuperTrend strategy data
                    vwap_st_strategy = st.session_state.get('vwap_st_strategy', None)

                    # Calculate momentum score
                    momentum_score = calculate_nifty_momentum_score(
                        indices_data,
                        stocks_data,
                        volume_state,
                        vwap_st_strategy
                    )

                    current_momentum_class = momentum_score['momentum_class']
                    previous_momentum_class = engine.nifty_momentum_state

                    # Check if momentum changed (reversal detection)
                    is_reversal = False
                    if previous_momentum_class and previous_momentum_class != current_momentum_class:
                        is_reversal = True

                    # Check cooldown (15 minutes for momentum alerts)
                    should_send_alert = False
                    if engine.nifty_momentum_last_alert:
                        time_since_alert = (now - engine.nifty_momentum_last_alert).total_seconds()
                        # For reversals, send immediately. For same state, wait 15 minutes
                        if is_reversal:
                            should_send_alert = True
                        elif time_since_alert >= 900:  # 15 minutes
                            should_send_alert = True
                    else:
                        # First alert
                        should_send_alert = True

                    # Send alert if conditions met
                    if should_send_alert:
                        alert_message = create_nifty_momentum_alert(
                            momentum_score,
                            is_reversal=is_reversal,
                            previous_class=previous_momentum_class
                        )

                        try:
                            send_telegram_message(alert_message, parse_mode='HTML')
                            print(f"📢 NIFTY MOMENTUM: {current_momentum_class} (Score: {momentum_score['total_score']:+d}/100)")
                            if is_reversal:
                                print(f"   🔄 REVERSAL: {previous_momentum_class} → {current_momentum_class}")

                            # Update state
                            engine.nifty_momentum_state = current_momentum_class
                            engine.nifty_momentum_last_alert = now
                        except Exception as e:
                            print(f"❌ Failed to send NIFTY momentum alert: {e}")
                    else:
                        # Just update state, no alert
                        engine.nifty_momentum_state = current_momentum_class
                        print(f"📊 NIFTY Momentum: {current_momentum_class} (Score: {momentum_score['total_score']:+d}/100) [Cooldown: {int(900 - time_since_alert)}s]")

                    # Store in session state for UI
                    st.session_state.nifty_momentum_score = momentum_score

                except Exception as e:
                    print(f"❌ Error in NIFTY momentum calculation: {e}")
                    import traceback
                    traceback.print_exc()

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
                # VWAP & SUPERTREND STRATEGY CALCULATION
                # ============================================
                vwap_st_strategy = None
                try:
                    # Fetch 15-min candles for strategy
                    candles_15min = fetch_nifty_futures_15min_candles()

                    if candles_15min and len(candles_15min) >= 8:
                        # Calculate VWAP
                        vwap = calculate_vwap(candles_15min)

                        # Calculate SuperTrend (ATR=7, Multiplier=3.0)
                        supertrend_value, supertrend_trend = calculate_supertrend(candles_15min, atr_period=7, multiplier=3.0)

                        # Detect signal
                        signal = detect_vwap_supertrend_signal(candles_15min, vwap, supertrend_value, supertrend_trend)

                        # Get last candle and current price
                        last_candle = candles_15min[-1]
                        ltp = nifty_futures_data['price'] if nifty_futures_data else last_candle['close']

                        vwap_st_strategy = {
                            'vwap': vwap,
                            'supertrend_value': supertrend_value,
                            'supertrend_trend': supertrend_trend,
                            'signal': signal,
                            'last_candle': last_candle,
                            'ltp': ltp,
                            'candles_count': len(candles_15min)
                        }

                        # Store in session state
                        st.session_state.vwap_st_strategy = vwap_st_strategy

                        print(f"✓ VWAP & SuperTrend: Signal={signal}, VWAP=₹{vwap:.2f}, ST=₹{supertrend_value:.2f} ({supertrend_trend})")

                        # Check for signal change and send Telegram alert
                        previous_signal = st.session_state.get('vwap_st_previous_signal', 'NEUTRAL')

                        if signal != previous_signal and signal != 'NEUTRAL':
                            # Signal changed to BULLISH or BEARISH
                            st.session_state.vwap_st_previous_signal = signal

                            # Send Telegram alert
                            if signal == 'BULLISH':
                                telegram_msg = (
                                    "🚨 <b>NIFTY FUTURES - BULLISH SIGNAL 🟢</b>\n\n"
                                    f"📈 <b>Strategy:</b> VWAP + SuperTrend (15-min)\n"
                                    f"⏰ <b>Time:</b> {datetime.now().strftime('%H:%M:%S')}\n\n"
                                    "<b>✅ Entry Conditions Met:</b>\n"
                                    f"• SuperTrend: 🟢 GREEN (₹{supertrend_value:.2f})\n"
                                    f"• VWAP: ₹{vwap:.2f} (Above ST)\n"
                                    f"• Candle: 🟢 GREEN (₹{last_candle['close']:.2f})\n"
                                    f"• Position: Above VWAP ✓\n\n"
                                    f"💡 <b>Recommendation:</b> GO LONG\n"
                                    f"📊 <b>LTP:</b> ₹{ltp:.2f}\n"
                                    f"🎯 <b>Watch for:</b> Price sustaining above VWAP\n\n"
                                    "#NiftyFutures #Bullish #VWAP #SuperTrend"
                                )
                            else:  # BEARISH
                                telegram_msg = (
                                    "🚨 <b>NIFTY FUTURES - BEARISH SIGNAL 🔴</b>\n\n"
                                    f"📉 <b>Strategy:</b> VWAP + SuperTrend (15-min)\n"
                                    f"⏰ <b>Time:</b> {datetime.now().strftime('%H:%M:%S')}\n\n"
                                    "<b>✅ Entry Conditions Met:</b>\n"
                                    f"• SuperTrend: 🔴 RED (₹{supertrend_value:.2f})\n"
                                    f"• VWAP: ₹{vwap:.2f} (Below ST)\n"
                                    f"• Candle: 🔴 RED (₹{last_candle['close']:.2f})\n"
                                    f"• Position: Below VWAP ✓\n\n"
                                    f"💡 <b>Recommendation:</b> GO SHORT\n"
                                    f"📊 <b>LTP:</b> ₹{ltp:.2f}\n"
                                    f"🎯 <b>Watch for:</b> Price sustaining below VWAP\n\n"
                                    "#NiftyFutures #Bearish #VWAP #SuperTrend"
                                )

                            send_telegram_alert(telegram_msg)
                            print(f"📱 Telegram Alert Sent: {signal} Signal")

                    else:
                        print("⏳ VWAP & SuperTrend: Waiting for sufficient candles (need 8+)")

                except Exception as e:
                    print(f"❌ Error calculating VWAP & SuperTrend strategy: {e}")
                    import traceback
                    traceback.print_exc()

                # ============================================
                # NIFTY COMPREHENSIVE ALERT (9 Criteria Scoring)
                # ============================================
                try:
                    # Calculate comprehensive score using all 9 criteria
                    score_result = calculate_nifty_momentum_score(
                        indices_data=indices_data,
                        stocks_data=stocks_data,
                        volume_state=volume_state,
                        vwap_st_strategy=vwap_st_strategy
                    )

                    # Send enhanced alert with 3-minute confirmation and divergence detection
                    send_nifty_enhanced_alert(score_result)

                except Exception as e:
                    print(f"❌ Error calculating NIFTY comprehensive alert: {e}")
                    import traceback
                    traceback.print_exc()

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

                        # BEARISH Alert: Price < -1% AND Net Flow < -50M
                        elif change_pct < -1.0 and net_flow < -50:
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
                    # Include all 209 F&O stocks for heat bar analysis
                    "stocks_data": stocks_data if stocks_data else {},
                    "deltas": deltas,
                    "nifty_futures_data": nifty_futures_data,
                    "vwap_st_strategy": vwap_st_strategy,
                    "last_update": datetime.now().isoformat()
                }
                save_dashboard_cache(cache_data)

                # ============================================
                # STOCK FLOW TRACKING TO CSV (Every 5 mins)
                # ============================================
                # Track all stocks with ±2% moves for analysis
                if stocks_data:
                    save_stock_flow_snapshot(stocks_data, engine.sector_mapping)

                # ============================================
                # VOLUME HISTORY SNAPSHOT - 3:25 PM (End of Day)
                # ============================================
                # Save end-of-day volume snapshot for 10-day rolling average
                current_time = datetime.now()

                # Initialize volume snapshot flag if not exists
                if not hasattr(engine, 'volume_snapshot_saved_today'):
                    engine.volume_snapshot_saved_today = False

                # Reset flag at midnight
                if current_time.hour == 0 and current_time.minute == 0:
                    engine.volume_snapshot_saved_today = False

                # Execute at 3:25 PM (5 mins before close, ±2 minute window) once per day
                if (current_time.hour == 15 and 25 <= current_time.minute <= 27 and
                    not engine.volume_snapshot_saved_today and stocks_data):
                    try:
                        print("📊 Saving end-of-day volume snapshot for historical tracking...")
                        save_daily_volume_snapshot(stocks_data)
                        engine.volume_snapshot_saved_today = True
                        print("✅ Volume snapshot saved successfully")
                    except Exception as e:
                        print(f"❌ Error saving volume snapshot: {e}")

                # ============================================
                # ALERT FOLLOW-UP TRACKER - 9:20 AM CHECK
                # ============================================
                # Check yesterday's alerts for opening momentum at 9:20 AM
                current_time = datetime.now()

                # Initialize follow-up flag if not exists
                if not hasattr(engine, 'followup_checked_today'):
                    engine.followup_checked_today = False

                # Reset flag at midnight
                if current_time.hour == 0 and current_time.minute == 0:
                    engine.followup_checked_today = False

                # Execute at 9:20 AM (±2 minute window) once per day
                if (current_time.hour == 9 and 20 <= current_time.minute <= 22 and
                    not engine.followup_checked_today):
                    try:
                        print("🔍 ALERT FOLLOW-UP TRACKER - Checking yesterday's alerts...")

                        # Get yesterday's alerts that haven't been followed up
                        yesterday_alerts = get_yesterday_alerts()

                        if not yesterday_alerts.empty:
                            print(f"📋 Found {len(yesterday_alerts)} alerts from yesterday")

                            # Get list of stock symbols to check
                            stocks_to_check = yesterday_alerts['stock'].unique().tolist()
                            print(f"📊 Checking momentum for: {', '.join(stocks_to_check)}")

                            # Check opening momentum for these stocks
                            momentum_stocks = check_opening_momentum(kite, stocks_to_check)

                            if momentum_stocks:
                                print(f"🎯 Found {len(momentum_stocks)} stocks with significant opening momentum!")

                                # Send priority alerts for each stock
                                alerted_stocks = []
                                for stock_data in momentum_stocks:
                                    send_followup_alert(
                                        stock=stock_data['stock'],
                                        opening_pct=stock_data['opening_pct'],
                                        current_pct=stock_data['current_pct'],
                                        current_price=stock_data['current_price'],
                                        signal=stock_data['signal']
                                    )
                                    alerted_stocks.append(stock_data['stock'])

                                # Mark these alerts as followed up
                                mark_alerts_followed_up(alerted_stocks)
                                print(f"✅ Follow-up alerts sent for {len(alerted_stocks)} stocks")
                            else:
                                print("ℹ️ No stocks showing significant opening momentum (>±1%)")
                        else:
                            print("ℹ️ No alerts from yesterday to follow up")

                        # Mark as checked for today
                        engine.followup_checked_today = True
                        print("✅ Alert follow-up check complete for today")

                    except Exception as e:
                        print(f"❌ Error in alert follow-up tracker: {e}")
                        import traceback
                        traceback.print_exc()

                # PHASE 1: Update chart data every 5 minutes (30 polls = 5 min at 10 sec intervals)
                engine.chart_update_counter += 1
                log_chart_debug(f"chart_update_counter = {engine.chart_update_counter}/30")

                if engine.chart_update_counter >= 10:  # 5 minutes
                    log_chart_debug(f"🎯 CHART UPDATE TRIGGERED! Counter reached {engine.chart_update_counter}")
                    engine.chart_update_counter = 0

                    # WEEKLY EXPIRY TRACKING: Collect data every 5 minutes
                    if not engine.ins_df.empty:
                        try:
                            print("📅 Collecting weekly expiry data...")

                            # Get next 4 expiries
                            next_expiries = get_next_nifty_expiries(engine.ins_df, num_expiries=4)

                            if next_expiries and "NIFTY" in indices_data:
                                nifty_price = indices_data["NIFTY"].get("price")

                                if nifty_price:
                                    atm_strike = get_atm_strike(nifty_price)

                                    # Collect data for each expiry
                                    for expiry_date in next_expiries:
                                        try:
                                            # Get strikes for this expiry
                                            strike_map = get_strikes_for_expiry(engine.ins_df, expiry_date, atm_strike, range_strikes=20)

                                            if strike_map:
                                                # Collect options data
                                                print(f"   🔍 About to call collect_weekly_expiry_data() for {expiry_date.strftime('%d-%b')}")
                                                daily_df = collect_weekly_expiry_data(kite, engine.ins_df, expiry_date, strike_map)
                                                print(f"   🔍 collect_weekly_expiry_data() returned, df empty: {daily_df.empty if daily_df is not None else 'None'}")

                                                if not daily_df.empty:
                                                    # Save cumulative data
                                                    print(f"   🔍 Calling save_cumulative_expiry_data()...")
                                                    save_cumulative_expiry_data(expiry_date, daily_df)
                                                else:
                                                    print(f"   ⚠️ daily_df is EMPTY - not saving")

                                        except Exception as e:
                                            print(f"❌ Error collecting data for {expiry_date}: {e}")

                                    print("✅ Weekly expiry data collection complete")

                        except Exception as e:
                            print(f"❌ Error in weekly expiry tracking: {e}")
                            import traceback
                            traceback.print_exc()

                    # STOCK MONTHLY EXPIRY TRACKING: Collect data every 5 minutes
                    if not engine.ins_df.empty and engine.stocks_with_fo:
                        try:
                            print("📈 Collecting stock monthly expiry data...")
                            stocks_collected = 0

                            # Iterate through all F&O stocks (191 stocks)
                            for symbol in engine.stocks_with_fo:
                                try:
                                    # Get stock price from stocks_data
                                    if symbol not in stocks_data:
                                        continue

                                    stock_price = stocks_data[symbol].get("price")
                                    if not stock_price or stock_price <= 0:
                                        continue

                                    # Get current month expiry for this stock
                                    expiry_date = get_stock_expiry(engine.ins_df, symbol)
                                    if not expiry_date:
                                        continue

                                    # Calculate ATM strike
                                    atm_strike = get_stock_atm_strike(stock_price, symbol)

                                    # Get ATM ± 10 strikes
                                    strike_map = get_stock_strikes_for_expiry(
                                        engine.ins_df, symbol, expiry_date, atm_strike, range_strikes=10
                                    )

                                    if strike_map:
                                        # Collect options data
                                        daily_df = collect_stock_expiry_data(kite, engine.ins_df, symbol, expiry_date, strike_map)

                                        if not daily_df.empty:
                                            # Save cumulative data
                                            save_cumulative_stock_expiry_data(symbol, expiry_date, daily_df)
                                            stocks_collected += 1

                                except Exception as e:
                                    print(f"❌ Error collecting data for {symbol}: {e}")
                                    continue

                            print(f"✅ Stock expiry data collection complete ({stocks_collected}/{len(engine.stocks_with_fo)} stocks)")

                        except Exception as e:
                            print(f"❌ Error in stock expiry tracking: {e}")
                            import traceback
                            traceback.print_exc()

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

            # AUTO-BACKUP: Check if we need to backup after market close
            try:
                auto_backup_after_market_close()
            except Exception as e:
                print(f"Auto-backup check failed: {e}")

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
st.set_page_config(page_title="APEX AI TRADING", layout="wide", initial_sidebar_state="expanded")

if AUTOREFRESH_AVAILABLE and st.session_state.get("auto_refresh_toggle", True) and st.session_state.get("polling_running", False):
    st.session_state.refresh_count += 1
    # Reset counter periodically to prevent overflow
    if st.session_state.refresh_count > 1000:
        st.session_state.refresh_count = 0
    count = st_autorefresh(interval=60 * 1000, key="auto_refresh_counter")  # 60s refresh - optimized for 8-hour market sessions without crashes

st.markdown("""
<style>
/* Futuristic Animated Header */
@keyframes gradientShift {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

@keyframes glow {
    0%, 100% { text-shadow: 0 0 10px #00ffff, 0 0 20px #00ffff, 0 0 30px #00ffff, 0 0 40px #00ffff; }
    50% { text-shadow: 0 0 20px #00ffff, 0 0 30px #00ffff, 0 0 40px #00ffff, 0 0 50px #00ffff, 0 0 60px #00ffff; }
}

@keyframes float {
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-10px); }
}

.main-header {
    font-size: 10rem;
    font-weight: 900;
    letter-spacing: 20px;
    text-align: center;
    padding: 3rem 0 2rem 0;
    margin-bottom: 1rem;
    background: linear-gradient(90deg, #0d47a1, #1976d2, #2196f3, #e91e63, #9c27b0, #0d47a1);
    background-size: 400% 400%;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: gradientShift 8s ease infinite, float 3s ease-in-out infinite;
    filter: drop-shadow(0 4px 8px rgba(13, 71, 161, 0.6)) drop-shadow(0 0 30px rgba(33, 150, 243, 0.4));
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    text-transform: uppercase;
    line-height: 1.2;
}

/* Color-Coded Metric Cards */
.metric-card-bullish {
    background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
    border-left: 4px solid #28a745;
    padding: 1rem;
    border-radius: 8px;
    margin: 0.5rem 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.metric-card-bearish {
    background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%);
    border-left: 4px solid #dc3545;
    padding: 1rem;
    border-radius: 8px;
    margin: 0.5rem 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.metric-card-neutral {
    background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
    border-left: 4px solid #ffc107;
    padding: 1rem;
    border-radius: 8px;
    margin: 0.5rem 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

/* CE/PE Progress Bars */
.cepe-bar-container {
    width: 100%;
    height: 30px;
    background-color: #f0f0f0;
    border-radius: 15px;
    overflow: hidden;
    position: relative;
    border: 2px solid #ddd;
}
.cepe-bar-ce {
    height: 100%;
    background: linear-gradient(90deg, #28a745, #20c997);
    float: left;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: bold;
    font-size: 0.85rem;
}
.cepe-bar-pe {
    height: 100%;
    background: linear-gradient(90deg, #dc3545, #e74c3c);
    float: left;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: bold;
    font-size: 0.85rem;
}

/* Market Overview Panel */
.overview-panel {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 2rem;
    border-radius: 15px;
    margin: 1rem 0;
    box-shadow: 0 4px 6px rgba(0,0,0,0.2);
}
.overview-metric {
    text-align: center;
    padding: 1rem;
}

/* Sentiment Gauge */
.sentiment-gauge {
    width: 200px;
    height: 100px;
    position: relative;
    margin: 0 auto;
}
.gauge-arrow {
    width: 4px;
    height: 80px;
    background-color: #333;
    position: absolute;
    bottom: 0;
    left: 50%;
    transform-origin: bottom center;
}

/* Enhanced Section Headers */
.section-header {
    background: linear-gradient(90deg, #f8f9fa 0%, #e9ecef 100%);
    border-left: 5px solid #1f77b4;
    padding: 1rem 1.5rem;
    border-radius: 8px;
    margin: 1.5rem 0 1rem 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

/* Status Indicators */
.status-green { color: #28a745; font-size: 1.5rem; }
.status-yellow { color: #ffc107; font-size: 1.5rem; }
.status-red { color: #dc3545; font-size: 1.5rem; }

/* Stock Cards */
.stock-card {
    border-radius: 10px;
    padding: 1rem;
    margin: 0.5rem 0;
    transition: transform 0.2s;
}
.stock-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

.part-container {
    border: 4px solid #000000;
    border-radius: 10px;
    padding: 1.5rem;
    margin: 1.5rem 0;
    background-color: #fafafa;
}
.section-box-green {
    border: 2px solid #28a745;
    border-radius: 8px;
    padding: 1rem;
    margin: 1rem 0;
    background-color: #ffffff;
}
.section-box-blue {
    border: 2px solid #1f77b4;
    border-radius: 8px;
    padding: 1rem;
    margin: 1rem 0;
    background-color: #ffffff;
}
.alert-box {padding: 0.5rem; border-radius: 0.3rem; margin-bottom: 0.3rem; font-size: 0.9rem;}
.alert-warning {background-color: #fff3cd; border-left: 4px solid #ffc107;}
.alert-success {background-color: #d4edda; border-left: 4px solid #28a745;}
.momentum-gauge {text-align: center; padding: 0.5rem; border-radius: 0.5rem; font-weight: bold;}

/* ============================================
   DARK MODE STYLES
   ============================================ */
body.dark-mode {
    background-color: #1a1a1a;
    color: #e0e0e0;
}

.dark-mode .main-header {
    background: linear-gradient(90deg, #2c3e50, #34495e);
    color: #ecf0f1;
}

.dark-mode .metric-card-bullish {
    background: linear-gradient(135deg, #1e4d2b 0%, #27ae60 100%);
    color: white;
}

.dark-mode .metric-card-bearish {
    background: linear-gradient(135deg, #7f1d1d 0%, #c0392b 100%);
    color: white;
}

.dark-mode .metric-card-neutral {
    background: linear-gradient(135deg, #4a4a4a 0%, #666 100%);
    color: white;
}

.dark-mode .part-container {
    background-color: #2d2d2d;
    border-color: #444;
}

.dark-mode .section-box-green {
    background-color: #1a1a1a;
    border-color: #27ae60;
}

.dark-mode .section-box-blue {
    background-color: #1a1a1a;
    border-color: #3498db;
}

.dark-mode .section-header {
    background: linear-gradient(90deg, #2d2d2d 0%, #3a3a3a 100%);
    color: #e0e0e0;
}

.dark-mode .stock-card {
    background-color: #2d2d2d;
    color: #e0e0e0;
}

/* Priority Alert Badges */
.priority-critical {
    background-color: #dc3545;
    color: white;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-weight: bold;
    font-size: 0.75rem;
    margin-right: 0.5rem;
}

.priority-high {
    background-color: #ffc107;
    color: #000;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-weight: bold;
    font-size: 0.75rem;
    margin-right: 0.5rem;
}

.priority-medium {
    background-color: #17a2b8;
    color: white;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-weight: bold;
    font-size: 0.75rem;
    margin-right: 0.5rem;
}

.priority-low {
    background-color: #6c757d;
    color: white;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-weight: bold;
    font-size: 0.75rem;
    margin-right: 0.5rem;
}

/* Enhanced Tab Styling */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background-color: #f8f9fa;
    padding: 1rem;
    border-radius: 10px;
}

.stTabs [data-baseweb="tab"] {
    height: 50px;
    padding: 0 24px;
    background-color: white;
    border-radius: 8px;
    font-weight: 600;
    border: 2px solid #dee2e6;
}

.stTabs [aria-selected="true"] {
    background-color: #1f77b4;
    color: white;
    border-color: #1f77b4;
}

.dark-mode .stTabs [data-baseweb="tab-list"] {
    background-color: #2d2d2d;
}

.dark-mode .stTabs [data-baseweb="tab"] {
    background-color: #1a1a1a;
    color: #e0e0e0;
    border-color: #444;
}

.dark-mode .stTabs [aria-selected="true"] {
    background-color: #3498db;
    border-color: #3498db;
}

/* ============================================
   ROCKET ANIMATIONS FOR ALERTS
   ============================================ */

/* Rocket container */
.rocket-container {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: 9999;
}

/* NIFTY Bullish - Rockets going UP */
@keyframes rocketUp {
    0% {
        transform: translateY(100vh) rotate(0deg);
        opacity: 0;
    }
    10% {
        opacity: 1;
    }
    90% {
        opacity: 1;
    }
    100% {
        transform: translateY(-20vh) rotate(15deg);
        opacity: 0;
    }
}

.nifty-rocket-up {
    position: absolute;
    font-size: 4rem;
    animation: rocketUp 3s ease-out forwards;
    filter: drop-shadow(0 0 10px rgba(33, 150, 243, 0.8));
}

/* NIFTY Bearish - Arrows going DOWN */
@keyframes arrowDown {
    0% {
        transform: translateY(-10vh) rotate(0deg);
        opacity: 0;
    }
    10% {
        opacity: 1;
    }
    90% {
        opacity: 1;
    }
    100% {
        transform: translateY(110vh) rotate(-15deg);
        opacity: 0;
    }
}

.nifty-arrow-down {
    position: absolute;
    font-size: 4rem;
    animation: arrowDown 3s ease-in forwards;
    filter: drop-shadow(0 0 10px rgba(244, 67, 54, 0.8));
}

/* STOCK Bullish - Stars going UP with spiral */
@keyframes starUp {
    0% {
        transform: translateY(100vh) translateX(0) rotate(0deg) scale(0.5);
        opacity: 0;
    }
    10% {
        opacity: 1;
    }
    25% {
        transform: translateY(75vh) translateX(30px) rotate(90deg) scale(1);
    }
    50% {
        transform: translateY(50vh) translateX(-30px) rotate(180deg) scale(1.2);
    }
    75% {
        transform: translateY(25vh) translateX(30px) rotate(270deg) scale(1);
    }
    90% {
        opacity: 1;
    }
    100% {
        transform: translateY(-10vh) translateX(0) rotate(360deg) scale(0.5);
        opacity: 0;
    }
}

.stock-star-up {
    position: absolute;
    font-size: 3.5rem;
    animation: starUp 3.5s ease-in-out forwards;
    filter: drop-shadow(0 0 15px rgba(255, 193, 7, 0.9));
}

/* STOCK Bearish - Red sparkles tumbling DOWN */
@keyframes sparkleDown {
    0% {
        transform: translateY(-10vh) translateX(0) rotate(0deg) scale(1);
        opacity: 0;
    }
    10% {
        opacity: 1;
    }
    25% {
        transform: translateY(25vh) translateX(-40px) rotate(-90deg) scale(1.2);
    }
    50% {
        transform: translateY(50vh) translateX(40px) rotate(-180deg) scale(0.8);
    }
    75% {
        transform: translateY(75vh) translateX(-40px) rotate(-270deg) scale(1.1);
    }
    90% {
        opacity: 1;
    }
    100% {
        transform: translateY(110vh) translateX(0) rotate(-360deg) scale(0.5);
        opacity: 0;
    }
}

.stock-sparkle-down {
    position: absolute;
    font-size: 3.5rem;
    animation: sparkleDown 3.5s ease-in forwards;
    filter: drop-shadow(0 0 15px rgba(244, 67, 54, 0.9));
    color: #f44336;
}

/* Pulse effect for critical alerts */
@keyframes pulse {
    0%, 100% {
        transform: scale(1);
    }
    50% {
        transform: scale(1.2);
    }
}

.rocket-critical {
    animation-duration: 2.5s !important;
    font-size: 5rem !important;
}

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

    st.markdown("---")
    st.markdown("### 🎨 Display Settings")

    # Dark Mode Toggle
    dark_mode = st.toggle(
        "🌙 Dark Mode",
        value=st.session_state.dark_mode,
        key="dark_mode_toggle",
        help="Toggle dark mode theme"
    )

    if dark_mode != st.session_state.dark_mode:
        st.session_state.dark_mode = dark_mode
        st.rerun()

    # Apply dark mode styles dynamically
    if st.session_state.dark_mode:
        st.markdown("""
        <style>
        /* Dark Mode Override */
        .stApp {
            background-color: #1a1a1a;
            color: #e0e0e0;
        }
        .stMarkdown, .stText, p, span, div {
            color: #e0e0e0 !important;
        }
        .stMetric {
            background-color: #2d2d2d;
            border-radius: 8px;
            padding: 1rem;
        }
        .stButton>button {
            background-color: #3498db;
            color: white;
        }
        .stSelectbox, .stTextInput, .stTextArea {
            background-color: #2d2d2d !important;
            color: #e0e0e0 !important;
        }
        [data-testid="stSidebar"] {
            background-color: #1e1e1e;
        }
        [data-testid="stSidebar"] * {
            color: #e0e0e0 !important;
        }
        .stAlert {
            background-color: #2d2d2d !important;
        }
        h1, h2, h3, h4, h5, h6 {
            color: #e0e0e0 !important;
        }
        </style>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 📈 Session Metrics")

    metrics = get_session_metrics()
    st.metric("Total Alerts", metrics["total_alerts"])
    st.metric("Critical Alerts", metrics["critical_alerts"])
    st.metric("Uptime", f"{metrics['uptime_minutes']} min")

    # Session Summary Button
    if st.button("📊 Generate Report", use_container_width=True):
        summary = generate_session_summary()
        st.text_area("Session Summary", summary, height=400)


st.markdown('''
<div style="text-align: center; margin-bottom: 2rem;">
    <p class="main-header">⚡ APEX AI TRADING ⚡</p>
    <p style="font-size: 1.1rem; color: #1565c0; font-weight: 600; letter-spacing: 3px; margin-top: -0.5rem; text-shadow: 0 1px 3px rgba(21, 101, 192, 0.3);">
        NEXT-GENERATION MOMENTUM ANALYTICS
    </p>
</div>

<!-- Rocket Animation Container -->
<div id="rocketContainer" class="rocket-container"></div>

<!-- Audio for alerts -->
<audio id="alertSound" preload="auto">
    <source src="data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBSuBzvLZjTgHF2i88OScTgwOUKfj8LRiHAU2kdfy0HgsBS13yPDej0AKElyz6uqnVRQJRp/h8r9sIgUpgc/y2o06BxhqvvbnnU4MClOn4fCzYxwGN5LY8s94LAUtdsjw3Y9AChJcs+rqp1UUCUaf4PK/bCIFKoHO8tqNOwcZar327qBPCwtTqOLws2MdBjmS2PLPeCwGLXbI8N2PQAoSXLPq6qdVFAlGn+DywG0iBSuBzvLajTsHGWu99++gTwsLU6ni8LNkHQY6ktfyz3gtBy12yPDej0AKElyz6+qmVRQJRp/g8sBtIgUrgs7y2o07BxlrvffvoE8LC1Kp4vCzZR0GOJLa8tB5LActdsnw3Y9AChJcs+vqp1UVCUaf4PK/bSIFK4LO8tqNOwcZa7337qFOCwtSqeLws2UdBjmS2PLQeS0HLHbJ8NyPQQoSXLPr6qdVFQlGn+DywG4iBSyCzvLajTwHGWu+9++hTgsLUqni8LNlHQY5ktfyzXktByx2yfDcj0EKElyz6+qnVRUJRp/h8r9uIgUsgs7y2o08BxlrvvfvoU4LC1Kp4vCyZh0GOZLa8tB5LQcsdsnw3I9BChJcs+vqp1UVCUaf4fK/biIFLILO8tqNPAcZa773 76FOCwtSqeLwsmYdBjmS2vLQeS0HLHbJ8NyPQQoSXLTq6qdWFQlGn+HywG4iBSyCzvLajT0HGGu+9++hTgsLUqni8LJmHQY5ktry0HktByx2yfDcj0EKElyz6+qnVhYJRp/h8r9uIgUsgs7y2o09Bxhrvvfuok4LC1Kp4vCyZh0GOpLa8tB5LQcsdsnw3I9BChJctOrqp1YWCUae4fLAbSIGLIHO8tqNPQcYar337qJOCwtTp+PwsmUeBjiS2/LPeC4HK3bJ79yOQgoRXLPr6qdWFglGn+HyvmwjBSyBzvLajT0GGGq+9++iTgsMUqfi8LJlHgc5kdvy0HkuByt2ye/cjkIKEVyz6+qnVhYJRp/h8r5sIwUsgs7y2o09BhhrrvbvpE4LDFKn4vCyZR4HOZHb8tB5LgcqdsrvzIxDCRFcsurqp1YWCUef4fK+bCMFLILO8tqNPQYYa6717qROCwxSpuLwsWUeBzmR2/LQeS4HKnbK78yMRAkQXbPq6qdWFglGn+HyvmwjBSyCzvLajT0GGGuu9e+kTgsMUqbi8LFlHgc5kdvy0HkuByp2yu/MjEQJEF2z6uqnVhYJRp/h8r5sIwUtgs7y2o0+Bhlrrvbvo04LDFKm4vCxZB4HOpHb8tB5LgcqdsvwzIxDCRBds+rqp1YXCUae4fK+bCMFLYLO8tqNPgYYa6717qNODAxSpuLwsWQeBzqR2/LQeS4HKXbL8M+MQwkQXbPq6qhVFwlGn+HyvmwkBSuCzvLajT4GGGuv9u+kTgwMU6bi8LFkHgc7ktvy0HovByl2zPDPjEQJEF2z6uqoVhcJRp/h8r5sJAUsgs7y2o0+BhhrrfbupE4MDFOn4vCxYx8HOpLb8tB6LwcpdszvzoxFCRBds+vqqFUXCkee4fK+bCQFLIHO8tuNPgYYaq317qVODAxTp+LwsWIfBzuS2vLReS8HKXbM782MRQgRXbPq6qhWFwpGn+HyvWwkBSyBzvLbjT8GGGqu9e+lTgwMU6fi8LFiHwc7ktny0HkvBih2zPDNjEYJD1206uqpVRcKRp/h8r1tJAUsgs7y2409BhhrrvXwpU4MDE+o4fCyYh8HPJLa8s96LwYodszwzYxGCQ9dtOrqqlUXCkae4fK9bSMGLIHO8tuNPwYYaq317qZODAxPqOHwsmIfBz2S2vLPei8GKHbM8M2NRQgPXrTp6qtVGApGnuHyvWwkBSyCzvLbjT4HGGqt9++mTwsMT6jh8LFjHwc9ktryz3ovBih2zPDNjUUIEF606+qrVRgKRp/g8r1sJQUsgs7y240+BxdprPfvpk8LDE+o4fCxYh8HPJLb8s96MAYndszwzo1FCBBetOnqrFUYCUae4PK9bCYFK4LO8tyNQAcXaK3276dQDAtPqODwsWIfBz2S2/LPejAGJ3bN8M6NRQgQXrTp6q1VFwpGnt/yvWwnBSyCzvLcjUAHF2ir9++oUAwMUKbf8bFiHwc9kt3yz3ovBSd2zfDOjkYID160 6uqtVRcKRp7e8bxuJwUsgs/y3I1ABxZoqvfvqFAMC1Cmx/GxYyAHPpPd8s97MAYmdszwzo5HBw9etOrqr1UXC0ae3vK8bycFLIHP8tuOQAcWZ6r386hQDAtQpsfxsWQgBj+T3fPPezAGJnXN8c2OSQcPXrTp66xWFwtGnt7yvG4nBSuCz/LcjkEHFmeq9vOqUAwLUKbG8bFlIQc/k93yz3sxBSV1zfDOjkoGD1606euuVRgLRp7e8rttKAUrgtDy3I5BBxZnqfbzqlANDFCmxvGwZiAHQJPd8s97MQYldc3wz45KBQ9etOnrrlYYC0ae3vK7bSgFK4LQ8tuPQQcVZ6n286pRDQxQpsbxsGcgBj+U3vLPezEGJXXN8M+PSwUQXrTp669WGAtGnt3yuW4pBSuB0PLbj0IHFWeq9vOrUQ0LUabF8a9nIQZAlN7y0HwyBiR1zO/Pj0sGEF605+uwVhcLRp/d8bpuKQUrgtDy2o9DBxRmq/b0q1ENDFGmxfGvZyIGQJPf8s99MgYkdMzwz49MBRBftOfqsFYXDEae3fK6cCkFK4LQ8tuPRAcUZqv29KtRDQxRpsTxrmgjBkGT3/LPfTIFJHPL8c+OTQUPYbTn6rBWGA1GneHvuXEqBSqC0PDbkEQHE2Ws9/WsUQ4MUKfD8a5pIwZAk+Dy0H0zBSN0y/HQjU4FD2G05+qwVhgNRp3g8LpxLAUqgdDy3JBFBhJlrvf1rVEODVCmw/GuaiMGQJTg8tB+MwUjdMvx0I1OBQ9htOfqsVcYDUad4PC6cSwFKoHQ8tyPRgYSZa339K5SDQ1Qp8Pxrmk0ByCS4fLQfzQFInPM8dCNTwUPYrTn6rJWGQ5Gnt/xu3MtBSqB0PPdjkYHEWWu+PWuUg0NUKfD8K5qNAcgkuHy0H80BSFzy/HRjk8FD2O05+uzVRkOR5/e8rt0LgUqgc/z3I9HBhFlr/j1r1MODFCnw/CuazQHH5Ph8tB/NAUhc8vx0Y5PBA9ktOnrs1UZDUeg3vK8dS8GKoHQ89yPRwYRZa349a9UDg1QpsPwrms0Bx+T4fLQgDUFIHPL8dGOTwQPZLTp67NVGg1HoN7yvHYwBSqB0PPcj0gGEWWv+fWwUw4NUKfD769sNQcekuHy0IA1BSBzy/HRjlAEDmS16OuzVRoMR6De8rx2MAUrgc/z3I9IBxFlr/r0sFQODVCmw+6ubTYHHpLh8tGANQUgc8vx0Y5RBA5ktejrs1UaDEeg3vK8dzEGKoHQ89yPSQYQZa/69LBUDg1Qpb/vu200ByCS4fLRgDUFIHPL8dGPUQQOZbXn67RWHQ1HoN3yu3cxBiqB0PPcj0kGEGWu+vWxUw8NUaW+76xvNgcfkuLy0YE2BR9zzPHRj1IEDWe05+u0Vh4MR5/d8rt4MgYpgdDz249KBhBlrvr1sVQPDVGlvu+sbzcHHpLi8tGCNgUfcsvy0o9SBA1otObrtFYeDEef3fK7eDIGKYHQ89uQSgYQZa369bJUEA1RpL7uq280Bx6S4vLRgzYFHnLM8tKPUwQOaLTl7LRXHA1Hn9zzu3gzBymB0PPbkEsGD2Wu+vayUxANU6O+7qpwNQcdkuLy0oM3BR1yzPLTj1QEDGm04uy0VxwNR5/c8rt5NAcpgNDz25BLBg9lrfr2s1MQDVKUO+7obEAbB/" type="audio/wav">
</audio>

<script>
// Rocket Animation Trigger Function
function launchRockets(alertType, direction, count, priority) {
    const container = document.getElementById('rocketContainer');
    if (!container) return;

    // Determine emoji and class based on alert type
    let emoji, className;
    if (alertType === 'NIFTY') {
        emoji = direction === 'UP' ? '🚀' : '⬇️';
        className = direction === 'UP' ? 'nifty-rocket-up' : 'nifty-arrow-down';
    } else { // STOCK
        emoji = direction === 'UP' ? '⭐' : '💫';
        className = direction === 'UP' ? 'stock-star-up' : 'stock-sparkle-down';
    }

    // Play sound
    const audio = document.getElementById('alertSound');
    if (audio) {
        audio.currentTime = 0;
        audio.volume = 0.3;
        audio.play().catch(e => console.log('Audio play failed:', e));
    }

    // Launch multiple rockets with staggered timing
    for (let i = 0; i < count; i++) {
        setTimeout(() => {
            const rocket = document.createElement('div');
            rocket.className = className;
            if (priority === 'CRITICAL') {
                rocket.classList.add('rocket-critical');
            }
            rocket.textContent = emoji;

            // Random horizontal position (10% to 90% of screen width)
            const randomX = 10 + Math.random() * 80;
            rocket.style.left = randomX + '%';

            // Add slight delay variation
            rocket.style.animationDelay = (Math.random() * 0.3) + 's';

            container.appendChild(rocket);

            // Remove after animation completes
            setTimeout(() => {
                rocket.remove();
            }, 4000);
        }, i * 200); // Stagger by 200ms
    }
}

// Make function globally accessible
window.launchRockets = launchRockets;
</script>
''', unsafe_allow_html=True)

# 🚀 CHECK FOR PENDING ROCKET LAUNCHES
# This executes whenever the page reruns and triggers any pending rocket animations
if 'rocket_triggers' in st.session_state and st.session_state.rocket_triggers:
    # Build JavaScript to launch all pending rockets
    rocket_js = "<script>\n"
    for trigger in st.session_state.rocket_triggers:
        alert_type = trigger['type']
        direction = trigger['direction']
        count = trigger['count']
        priority = trigger['priority']
        rocket_js += f"window.launchRockets('{alert_type}', '{direction}', {count}, '{priority}');\n"
    rocket_js += "</script>"

    # Inject the JavaScript
    st.markdown(rocket_js, unsafe_allow_html=True)

    # Clear triggers after launching
    st.session_state.rocket_triggers = []

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

# Load sector mapping and store in engine
sector_mapping = load_sector_mapping()
engine.sector_mapping = sector_mapping
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

# PART 1 Header - Always visible
st.markdown("---")
st.markdown("")

st.markdown("""
<div style="border: 4px solid #000000; border-radius: 10px; padding: 1.5rem; margin: 1.5rem 0; background-color: #fafafa;">
    <h1 style="text-align: center; margin: 0;">📊 PART 1: INDICES ANALYSIS</h1>
    <p style="text-align: center; font-style: italic; margin: 0.5rem 0;">Comprehensive analysis of all tracked indices (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX)</p>
    <hr style="border: 1px solid #ddd; margin: 1rem 0;">
</div>
""", unsafe_allow_html=True)

st.markdown("")

# Only show flow charts if we have data
if len(nifty_chart_data) > 1:
    # Section box for NIFTY Flow Analysis
    st.markdown('<div style="border: 2px solid #28a745; border-radius: 8px; padding: 1rem; margin: 1rem 0; background-color: #ffffff;"><h3>📊 NIFTY Flow Analysis Charts</h3></div>', unsafe_allow_html=True)
    
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
st.markdown('<div style="border: 2px solid #28a745; border-radius: 8px; padding: 1rem; margin: 1rem 0; background-color: #ffffff;"><h3>🔥 NIFTY Options Volume Analysis</h3></div>', unsafe_allow_html=True)

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
    st.markdown(create_enhanced_section_header("Volume Spike Monitor (Last 10 Spikes)", "🔥"), unsafe_allow_html=True)
    st.dataframe(
        heatmap_df,
        use_container_width=True,
        hide_index=True
    )
    st.caption("🔥 >3x = Strong Signal | 🟡 2-3x = Moderate | 🟢 <2x = Normal")
else:
    # Show blank heatmap table
    st.markdown(create_enhanced_section_header("Volume Spike Monitor (Last 10 Spikes)", "🔥"), unsafe_allow_html=True)
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

# Volume Spike Session Summary (Always Visible)
st.markdown("")
st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
st.markdown(create_enhanced_section_header("SESSION SUMMARY (Since 9:15 AM)", "📊"), unsafe_allow_html=True)
st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

if volume_state.spike_queue and len(volume_state.spike_queue) > 0:
    # Calculate statistics from actual data
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
else:
    # Show empty structure with zero values
    ce_count = 0
    ce_total_volume = 0
    ce_avg_volume = 0
    ce_largest = None

    pe_count = 0
    pe_total_volume = 0
    pe_avg_volume = 0
    pe_largest = None

# Always display the structure
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

    st.markdown(f"**CE Dominance: {ce_pct:.0f}%**  {ce_pct:.0f}% CE | {pe_pct:.0f}% PE")

    # Add modern CE/PE progress bar
    st.markdown(create_cepe_progress_bar(ce_count, pe_count, show_labels=True), unsafe_allow_html=True)

    if signal_color == "success":
        st.success(f"**Signal:** {signal}")
    elif signal_color == "error":
        st.error(f"**Signal:** {signal}")
    else:
        st.info(f"**Signal:** {signal}")
else:
    # Show waiting message for race summary
    st.info("⏳ **BALANCED - CE and PE spikes roughly equal**")
    st.caption("Waiting for volume spikes to be detected...")

st.markdown("")


st.markdown("")

# Chart 2 & 4: Race Chart + Wave Chart (Side by side)
col1, col2 = st.columns([1, 2])

with col1:
    # CE vs PE Race Chart
    race_data = create_ce_pe_race_chart()
    
    if race_data:
        st.markdown(create_enhanced_section_header("CE vs PE Race", "📈"), unsafe_allow_html=True)
        st.markdown("**10-Minute Window**")

        # Volume metrics
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"**CE:** {format_number(race_data['ce_total'])}")
        with col_b:
            st.markdown(f"**PE:** {format_number(race_data['pe_total'])}")

        # Enhanced progress bar
        st.markdown(create_cepe_progress_bar(race_data['ce_total'], race_data['pe_total']), unsafe_allow_html=True)

        # Net Bias with status indicator
        status_icon = get_status_indicator(race_data['net_flow'], threshold_high=1000, threshold_low=-1000)
        if race_data['bias'] == 'BULLISH':
            st.markdown(f"{status_icon} **Net {race_data['bias']}:** +{format_number(race_data['net_flow'])}", unsafe_allow_html=True)
        elif race_data['bias'] == 'BEARISH':
            st.markdown(f"{status_icon} **Net {race_data['bias']}:** {format_number(race_data['net_flow'])}", unsafe_allow_html=True)
        else:
            st.markdown(f"{status_icon} **Net {race_data['bias']}:** {format_number(race_data['net_flow'])}", unsafe_allow_html=True)
        
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
    indices_data = cached_data.get("indices_data", {})

    # ============================================
    # MARKET OVERVIEW PANEL
    # ============================================
    if indices_data:
        st.markdown(create_market_overview_panel(indices_data, deltas), unsafe_allow_html=True)
        st.markdown("---")

    # Enhanced section header
    st.markdown(create_enhanced_section_header("Indices Momentum", "📊"), unsafe_allow_html=True)
    
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

        # Add CE/PE progress bar
        st.markdown(create_cepe_progress_bar(indices_ce, indices_pe), unsafe_allow_html=True)

        # Status indicator with net flow
        status_icon = get_status_indicator(indices_net, threshold_high=1000, threshold_low=-1000)
        st.markdown(f"{status_icon} **Net:** {format_number(indices_net)}", unsafe_allow_html=True)
    
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
        st.markdown(create_enhanced_section_header("NIFTY Momentum", "📈"), unsafe_allow_html=True)

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

            # Add CE/PE progress bar
            st.markdown(create_cepe_progress_bar(ce_flow, pe_flow), unsafe_allow_html=True)

            # Status indicator with net flow
            status_icon = get_status_indicator(net_flow, threshold_high=500, threshold_low=-500)
            st.markdown(f"{status_icon} **Net:** {format_number(net_flow)}", unsafe_allow_html=True)
        
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
        st.markdown(create_enhanced_section_header("BANKNIFTY Momentum", "📈"), unsafe_allow_html=True)

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

        # Calculate dominance
        total_flow = ce_flow + pe_flow
        if total_flow > 0:
            ce_pct = (ce_flow / total_flow) * 100
            pe_pct = 100 - ce_pct
        else:
            ce_pct = 50
            pe_pct = 50

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

            # Add CE/PE progress bar
            st.markdown("**CE vs PE Race**")
            st.markdown(create_cepe_progress_bar(ce_flow, pe_flow), unsafe_allow_html=True)
            st.caption(dominance)

            # Status indicator with net flow
            status_icon = get_status_indicator(net_flow, threshold_high=500, threshold_low=-500)
            st.markdown(f"{status_icon} **Net:** {format_number(net_flow)}", unsafe_allow_html=True)
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
        st.markdown(create_enhanced_section_header("FINNIFTY Momentum", "📈"), unsafe_allow_html=True)

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

        # Calculate dominance
        total_flow = ce_flow + pe_flow
        if total_flow > 0:
            ce_pct = (ce_flow / total_flow) * 100
            pe_pct = 100 - ce_pct
        else:
            ce_pct = 50
            pe_pct = 50

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

            # Add CE/PE progress bar
            st.markdown("**CE vs PE Race**")
            st.markdown(create_cepe_progress_bar(ce_flow, pe_flow), unsafe_allow_html=True)
            st.caption(dominance)

            # Status indicator with net flow
            status_icon = get_status_indicator(net_flow, threshold_high=300, threshold_low=-300)
            st.markdown(f"{status_icon} **Net:** {format_number(net_flow)}", unsafe_allow_html=True)
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
        st.markdown(create_enhanced_section_header("MIDCPNIFTY Momentum", "📈"), unsafe_allow_html=True)

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

        # Calculate dominance
        total_flow = ce_flow + pe_flow
        if total_flow > 0:
            ce_pct = (ce_flow / total_flow) * 100
            pe_pct = 100 - ce_pct
        else:
            ce_pct = 50
            pe_pct = 50

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

            # Add CE/PE progress bar
            st.markdown("**CE vs PE Race**")
            st.markdown(create_cepe_progress_bar(ce_flow, pe_flow), unsafe_allow_html=True)
            st.caption(dominance)

            # Status indicator with net flow
            status_icon = get_status_indicator(net_flow, threshold_high=200, threshold_low=-200)
            st.markdown(f"{status_icon} **Net:** {format_number(net_flow)}", unsafe_allow_html=True)
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
        st.markdown(create_enhanced_section_header("SENSEX Momentum", "📈"), unsafe_allow_html=True)

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
        
        # Calculate dominance
        total_flow = ce_flow + pe_flow
        if total_flow > 0:
            ce_pct = (ce_flow / total_flow) * 100
            pe_pct = 100 - ce_pct
        else:
            ce_pct = 50
            pe_pct = 50

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

            # Add CE/PE progress bar
            st.markdown("**CE vs PE Race**")
            st.markdown(create_cepe_progress_bar(ce_flow, pe_flow), unsafe_allow_html=True)
            st.caption(dominance)

            # Status indicator with net flow
            status_icon = get_status_indicator(net_flow, threshold_high=500, threshold_low=-500)
            st.markdown(f"{status_icon} **Net:** {format_number(net_flow)}", unsafe_allow_html=True)
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

    
    # Get indices data for INDICES-WIDE PERFORMANCE section
        indices_data_perf = st.session_state.get('indices_data', {})
    if not indices_data_perf:
        cached_perf = load_dashboard_cache()
        if cached_perf and 'indices_data' in cached_perf:
            indices_data_perf = cached_perf['indices_data']

    if indices_data_perf and len(indices_data_perf) > 0:
        st.markdown("")
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        st.markdown(create_enhanced_section_header(f"INDICES-WIDE PERFORMANCE ({len(indices_data_perf)} Indices Tracked)", "📊"), unsafe_allow_html=True)
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

        # Display performance distribution - Compact vertical cards
        st.markdown("**Index Performance Distribution:**")

        # Use equal-width columns instead of proportional
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                label="🟢 POSITIVE",
                value=f"{pos_count} indices",
                delta=f"{pos_pct:.0f}% of market",
                delta_color="normal"
            )

        with col2:
            st.metric(
                label="🔴 NEGATIVE",
                value=f"{neg_count} indices",
                delta=f"{neg_pct:.0f}% of market",
                delta_color="inverse"
            )

        with col3:
            # Market breadth indicator
            if pos_pct >= 60:
                st.metric("Market Breadth", "🚀 Strong", delta="Bullish")
            elif neg_pct >= 60:
                st.metric("Market Breadth", "📉 Weak", delta="Bearish", delta_color="inverse")
            else:
                st.metric("Market Breadth", "⚖️ Mixed", delta="Neutral", delta_color="off")

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

            st.markdown(f"**CE vs PE Race:**")
            st.markdown(f"## {ce_pct_idx:.0f}% CE | {pe_pct_idx:.0f}% PE")

            # Enhanced progress bar (Green for CE, Red for PE)
            st.markdown(create_cepe_progress_bar(total_ce_flow_idx, total_pe_flow_idx, show_labels=True), unsafe_allow_html=True)

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
        # SECTOR PERFORMANCE - SMART SORTING
        # ============================================
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        st.markdown(create_enhanced_section_header("SECTOR PERFORMANCE", "🎯"), unsafe_allow_html=True)
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # Prepare data with CE percentage calculation
        all_idx_with_data = []
        for idx_name, idx_data in indices_data_perf.items():
            change_pct = 0
            if "change_pct" in idx_data:
                change_pct = idx_data["change_pct"]
            elif "price" in idx_data and "prev_close" in idx_data:
                if idx_data["prev_close"] and idx_data["prev_close"] > 0:
                    change_pct = ((idx_data["price"] - idx_data["prev_close"]) / idx_data["prev_close"]) * 100

            ce_flow = idx_data.get("ce_flow", 0)
            pe_flow = idx_data.get("pe_flow", 0)
            total = ce_flow + pe_flow
            ce_pct = (ce_flow / total * 100) if total > 0 else 50

            all_idx_with_data.append({
                'name': idx_name,
                'change_pct': change_pct,
                'ce_flow': ce_flow,
                'pe_flow': pe_flow,
                'ce_pct': ce_pct
            })

        # Create three columns for different perspectives
        col1, col2, col3 = st.columns(3)

        # Column 1: Top 5 by Price Change (Biggest Movers)
        with col1:
            st.markdown("#### 📈 Biggest Movers (Price)")
            sorted_by_price = sorted(all_idx_with_data, key=lambda x: abs(x['change_pct']), reverse=True)[:5]

            medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
            for i, idx_data in enumerate(sorted_by_price):
                name = idx_data['name']
                change = idx_data['change_pct']
                ce_pct = idx_data['ce_pct']

                # Color based on direction
                change_emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"

                # Signal based on CE%
                if ce_pct >= 70:
                    signal = "🚀"
                elif ce_pct >= 60:
                    signal = "✅"
                elif ce_pct >= 40:
                    signal = "⚖️"
                else:
                    signal = "⚠️"

                medal = medals[i]
                st.markdown(f"{medal} **{name}**: {change_emoji}{change:+.2f}%")
                st.caption(f"CE: {ce_pct:.0f}% {signal}")

        # Column 2: Top 5 by Bullish Flow (Most Bullish Sentiment)
        with col2:
            st.markdown("#### 🟢 Most Bullish Flow")
            sorted_by_flow = sorted(all_idx_with_data, key=lambda x: x['ce_pct'], reverse=True)[:5]

            for i, idx_data in enumerate(sorted_by_flow):
                name = idx_data['name']
                change = idx_data['change_pct']
                ce_pct = idx_data['ce_pct']

                # Signal
                if ce_pct >= 80:
                    signal = "🔥 Extreme"
                elif ce_pct >= 70:
                    signal = "🚀 Strong"
                else:
                    signal = "✅ Bullish"

                # Show price for context
                change_emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"

                st.markdown(f"**{i+1}. {name}**: {ce_pct:.0f}% CE {signal}")
                st.caption(f"Price: {change_emoji}{change:+.2f}%")

        # Column 3: Divergence Alerts (Reversal Opportunities)
        with col3:
            st.markdown("#### ⚠️ Divergence Alerts")

            # Find divergences
            divergences = []
            for idx_data in all_idx_with_data:
                name = idx_data['name']
                change = idx_data['change_pct']
                ce_pct = idx_data['ce_pct']

                # Bullish divergence: Price down but flow bullish
                if change < -0.3 and ce_pct > 65:
                    divergences.append({
                        'name': name,
                        'change': change,
                        'ce_pct': ce_pct,
                        'type': 'BULLISH',
                        'strength': ce_pct - 50  # How strong the divergence
                    })

                # Bearish divergence: Price up but flow bearish
                elif change > 0.3 and ce_pct < 35:
                    divergences.append({
                        'name': name,
                        'change': change,
                        'ce_pct': ce_pct,
                        'type': 'BEARISH',
                        'strength': 50 - ce_pct
                    })

            # Sort by strength
            divergences_sorted = sorted(divergences, key=lambda x: x['strength'], reverse=True)[:5]

            if divergences_sorted:
                for i, div in enumerate(divergences_sorted):
                    name = div['name']
                    change = div['change']
                    ce_pct = div['ce_pct']
                    div_type = div['type']

                    if div_type == 'BULLISH':
                        icon = "🎯"
                        signal = "Dip Buy?"
                        interpretation = f"Price {change:.2f}% but {ce_pct:.0f}% CE"
                    else:
                        icon = "⚠️"
                        signal = "Top?"
                        interpretation = f"Price +{change:.2f}% but {ce_pct:.0f}% CE"

                    st.markdown(f"{icon} **{name}** {signal}")
                    st.caption(interpretation)
            else:
                st.info("No strong divergences detected")

        st.markdown("")

    
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

# ============================================
# VWAP & SUPERTREND STRATEGY CARD
# ============================================
# Get strategy data from session state or cache
vwap_st_strategy_display = st.session_state.get('vwap_st_strategy', None)

if not vwap_st_strategy_display:
    cached = load_dashboard_cache()
    if cached and 'vwap_st_strategy' in cached:
        vwap_st_strategy_display = cached['vwap_st_strategy']
        st.session_state.vwap_st_strategy = vwap_st_strategy_display

# Always display the strategy card (shows placeholder when no data)
if vwap_st_strategy_display:
    # Display the strategy card with real data
    strategy_html = create_vwap_supertrend_card(
        vwap=vwap_st_strategy_display.get('vwap'),
        supertrend_value=vwap_st_strategy_display.get('supertrend_value'),
        supertrend_trend=vwap_st_strategy_display.get('supertrend_trend'),
        signal=vwap_st_strategy_display.get('signal'),
        last_candle=vwap_st_strategy_display.get('last_candle'),
        ltp=vwap_st_strategy_display.get('ltp')
    )
else:
    # Show placeholder card with structure
    strategy_html = create_vwap_supertrend_card(
        vwap=None,
        supertrend_value=None,
        supertrend_trend=None,
        signal='NEUTRAL',
        last_candle=None,
        ltp=None
    )

st.markdown(strategy_html, unsafe_allow_html=True)


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
st.markdown("")

# PART 2 Header with border
st.markdown("""
<div style="border: 4px solid #000000; border-radius: 10px; padding: 1.5rem; margin: 1.5rem 0; background-color: #fafafa;">
    <h1 style="text-align: center; margin: 0;">📈 PART 2: STOCKS ANALYSIS</h1>
    <p style="text-align: center; font-style: italic; margin: 0.5rem 0;">Market-wide performance analysis of all 209 F&O stocks</p>
    <hr style="border: 1px solid #ddd; margin: 1rem 0;">
</div>
""", unsafe_allow_html=True)

# ============================================
# STOCKS MARKET OVERVIEW PANEL
# ============================================
if cached_data and "stocks_data" in cached_data:
    stocks_data_overview = cached_data.get("stocks_data", {})
    if stocks_data_overview:
        st.markdown(create_stocks_market_overview_panel(stocks_data_overview, deltas), unsafe_allow_html=True)
        st.markdown("---")

# ============================================
# STOCKS MOMENTUM
# ============================================
st.markdown(create_enhanced_section_header("Stocks Momentum", "📈"), unsafe_allow_html=True)
if cached_data:

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

        # Add CE/PE progress bar
        st.markdown(create_cepe_progress_bar(stocks_ce, stocks_pe), unsafe_allow_html=True)

        # Status indicator with net flow
        status_icon = get_status_indicator(stocks_net, threshold_high=1000, threshold_low=-1000)
        st.markdown(f"{status_icon} **Net:** {format_number(stocks_net)}", unsafe_allow_html=True)

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

# ============================================
# ALERT FOLLOW-UP TRACKER
# ============================================
st.markdown(create_enhanced_section_header("Alert Follow-Up Tracker", "📌"), unsafe_allow_html=True)

with st.expander("📌 View Alert Follow-Up Tracker", expanded=False):
    try:
        from pathlib import Path
        import pandas as pd

        # Load alert history
        history_file = Path("data/alert_history.csv")

        if history_file.exists():
            alert_history = pd.read_csv(history_file)
            alert_history['date'] = pd.to_datetime(alert_history['date'])

            # Get yesterday's date
            yesterday = (datetime.now() - timedelta(days=1)).date()
            today = datetime.now().date()

            # Filter yesterday's alerts
            yesterday_alerts = alert_history[
                alert_history['date'].dt.date == yesterday
            ].copy()

            # Get today's followed-up alerts
            followed_up_today = alert_history[
                (alert_history['date'].dt.date == yesterday) &
                (alert_history['followed_up'] == True)
            ].copy()

            if not yesterday_alerts.empty:
                # Display statistics
                total_alerts = len(yesterday_alerts)
                followed_up_count = len(followed_up_today)
                pending_count = total_alerts - followed_up_count

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Yesterday's Alerts", total_alerts)

                with col2:
                    st.metric("Followed Up Today", followed_up_count,
                             delta=f"{(followed_up_count/total_alerts*100):.0f}%" if total_alerts > 0 else "0%")

                with col3:
                    st.metric("Pending", pending_count)

                st.markdown("---")

                # Display followed-up alerts with current status
                if not followed_up_today.empty:
                    st.markdown("### 🎯 Stocks That Triggered Follow-Up Alerts Today")

                    # Get current prices for these stocks if available
                    if cached_data and "stocks_data" in cached_data:
                        current_stocks_data = cached_data["stocks_data"]

                        display_data = []
                        for _, alert in followed_up_today.iterrows():
                            stock = alert['stock']
                            alert_type = alert['alert_type']
                            alert_price = alert['alert_price']

                            # Get current data if available
                            if stock in current_stocks_data:
                                current_price = current_stocks_data[stock].get('price', 0)
                                current_change = current_stocks_data[stock].get('change_pct', 0)

                                if current_price > 0 and alert_price > 0:
                                    move_from_alert = ((current_price - alert_price) / alert_price) * 100
                                else:
                                    move_from_alert = 0

                                signal = "🟢 BULLISH" if alert_type == "BULLISH" else "🔴 BEARISH"

                                display_data.append({
                                    'Stock': stock,
                                    'Signal': signal,
                                    'Alert Price': f"₹{alert_price:.2f}",
                                    'Current Price': f"₹{current_price:.2f}",
                                    'Today\'s Change': f"{current_change:+.2f}%",
                                    'Move from Alert': f"{move_from_alert:+.2f}%"
                                })

                        if display_data:
                            df_display = pd.DataFrame(display_data)
                            st.dataframe(df_display, use_container_width=True, hide_index=True)
                        else:
                            st.info("💡 Current price data not available. Start polling to see live prices.")
                    else:
                        # Just show the basic alert info
                        display_data = []
                        for _, alert in followed_up_today.iterrows():
                            signal = "🟢 BULLISH" if alert['alert_type'] == "BULLISH" else "🔴 BEARISH"
                            display_data.append({
                                'Stock': alert['stock'],
                                'Signal': signal,
                                'Alert Price': f"₹{alert['alert_price']:.2f}",
                                'Alert Time': alert['time'],
                                'Score': alert['score']
                            })

                        df_display = pd.DataFrame(display_data)
                        st.dataframe(df_display, use_container_width=True, hide_index=True)

                    st.markdown("---")

                # Display pending follow-ups
                pending_alerts = yesterday_alerts[
                    yesterday_alerts['followed_up'] == False
                ].copy()

                if not pending_alerts.empty:
                    st.markdown("### ⏳ Pending Follow-Ups (No Significant Opening Momentum)")

                    display_data = []
                    for _, alert in pending_alerts.iterrows():
                        signal = "🟢 BULLISH" if alert['alert_type'] == "BULLISH" else "🔴 BEARISH"
                        display_data.append({
                            'Stock': alert['stock'],
                            'Signal': signal,
                            'Alert Price': f"₹{alert['alert_price']:.2f}",
                            'Alert Time': alert['time'],
                            'Score': alert['score']
                        })

                    df_display = pd.DataFrame(display_data)
                    st.dataframe(df_display, use_container_width=True, hide_index=True)

                    st.info("💡 These stocks didn't show >±1% opening momentum at 9:20 AM today")

            else:
                st.info("📭 No alerts from yesterday. Alerts will appear here once you receive stock alerts.")

            # Show instructions
            st.markdown("---")
            st.markdown("""
            ### 📖 How It Works

            1. **Alert Capture**: Every stock alert sent via Telegram is automatically saved to history
            2. **Daily Check**: At 9:20 AM, system checks yesterday's alerted stocks for opening momentum
            3. **Follow-Up Alert**: If opening change is >±1%, priority Telegram alert is sent
            4. **Tracking**: Dashboard shows which alerts were followed up and their current performance

            **Success Pattern**: Stocks showing >±1% opening often continue strong momentum throughout the day!
            """)

        else:
            st.info("📭 No alert history yet. Start receiving stock alerts to begin tracking follow-up opportunities!")

    except Exception as e:
        st.error(f"❌ Error loading alert history: {e}")

st.markdown("---")

# ============================================
# TOP 10 STOCKS (Live Rankings)
# ============================================
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
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    # Stock name with entry count tracking
                    tracking_data = st.session_state.get('stock_entry_tracking', {})
                    # Fallback: Load from JSON if session state is empty
                    if not tracking_data:
                        tracking_data = load_stock_entry_tracking()
                    display_name = get_stock_display_name(stock_name, "top10_stocks", tracking_data)

                    price_str = f"₹{stock_price:,.2f}" if stock_price else "N/A"
                    change_str = f"({change_pct:+.2f}%)" if change_pct is not None else ""
                    st.markdown(f"**{rank}. {display_name}** {price_str} {change_str}")
                    st.caption(f"_{sector}_")

                    # CE/PE race bar with color-coded progress bar
                    st.markdown(create_cepe_progress_bar(ce_flow, pe_flow, show_labels=True), unsafe_allow_html=True)

                with col2:
                    # CE Flow
                    ce_emoji = "🟢" if ce_flow > 0 else "🔴"
                    st.metric("CE", f"{ce_emoji}{format_number(ce_flow)}")

                    # PE Flow
                    pe_emoji = "🟢" if pe_flow > 0 else "🔴"
                    st.metric("PE", f"{pe_emoji}{format_number(pe_flow)}")

                with col3:
                    # Net flow
                    if net_flow > 0:
                        st.metric("Net", f"+{format_number(net_flow)}", delta="Bullish", delta_color="normal")
                    else:
                        st.metric("Net", f"{format_number(net_flow)}", delta="Bearish", delta_color="inverse")

                st.markdown("---")

st.markdown("---")
st.markdown("")

# ============================================
# MARKET-WIDE PERFORMANCE (Outside Expander)
# ============================================
# Get stocks_data from cache
if cached_data and "stocks_data" in cached_data:
    stocks_data = cached_data.get("stocks_data", {})

    if stocks_data and len(stocks_data) > 0:
        st.markdown(create_enhanced_section_header("MARKET-WIDE PERFORMANCE (All 209 F&O Stocks)", "📊"), unsafe_allow_html=True)

        # Add Stock Performance Heat Bar
        st.markdown(create_stock_performance_heatbar(stocks_data), unsafe_allow_html=True)

        # Calculate market-wide statistics
        total_stocks = len(stocks_data)
        bullish_count = sum(1 for s in stocks_data.values() if s.get('net_flow', 0) > 0)
        bearish_count = sum(1 for s in stocks_data.values() if s.get('net_flow', 0) < 0)
        neutral_count = total_stocks - bullish_count - bearish_count

        total_net_flow = sum(s.get('net_flow', 0) for s in stocks_data.values())
        avg_net_flow = total_net_flow / total_stocks if total_stocks > 0 else 0

        # Count stocks with price data
        stocks_with_price = [s for s in stocks_data.values() if s.get('change_pct') is not None]
        gainers = [s for s in stocks_with_price if s.get('change_pct', 0) > 0]
        losers = [s for s in stocks_with_price if s.get('change_pct', 0) < 0]

        # Display metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Stocks", total_stocks)
            market_sentiment = "🟢 BULLISH" if bullish_count > bearish_count else ("🔴 BEARISH" if bearish_count > bullish_count else "🟡 NEUTRAL")
            st.caption(f"**Market Sentiment:** {market_sentiment}")

        with col2:
            bullish_pct = (bullish_count / total_stocks * 100) if total_stocks > 0 else 0
            st.metric("🟢 Bullish Stocks", bullish_count, delta=f"{bullish_pct:.1f}%")
            st.caption("Positive net flow")

        with col3:
            bearish_pct = (bearish_count / total_stocks * 100) if total_stocks > 0 else 0
            st.metric("🔴 Bearish Stocks", bearish_count, delta=f"{bearish_pct:.1f}%", delta_color="inverse")
            st.caption("Negative net flow")

        with col4:
            flow_emoji = "🟢" if avg_net_flow > 0 else "🔴"
            st.metric(f"{flow_emoji} Avg Net Flow", format_number(avg_net_flow))
            st.caption(f"Across {total_stocks} stocks")

        st.markdown("")

        # Top Gainers and Losers
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 📈 Top 5 Gainers (Price)")
            if gainers:
                top_gainers = sorted([(name, data) for name, data in stocks_data.items() if data.get('change_pct') and data.get('change_pct') > 0],
                                   key=lambda x: x[1].get('change_pct', 0), reverse=True)[:5]

                for i, (stock_name, data) in enumerate(top_gainers, 1):
                    price = data.get('price')
                    change_pct = data.get('change_pct', 0)
                    net_flow = data.get('net_flow', 0)

                    # Use color-coded stock card for gainers
                    st.markdown(f"**{i}.**", unsafe_allow_html=True)
                    st.markdown(create_stock_card(stock_name, price, change_pct, net_flow, card_type="gainer"), unsafe_allow_html=True)
            else:
                st.info("No gainers data available yet")

        with col2:
            st.markdown("#### 📉 Top 5 Losers (Price)")
            if losers:
                top_losers = sorted([(name, data) for name, data in stocks_data.items() if data.get('change_pct') and data.get('change_pct') < 0],
                                  key=lambda x: x[1].get('change_pct', 0))[:5]

                for i, (stock_name, data) in enumerate(top_losers, 1):
                    price = data.get('price')
                    change_pct = data.get('change_pct', 0)
                    net_flow = data.get('net_flow', 0)

                    # Use color-coded stock card for losers
                    st.markdown(f"**{i}.**", unsafe_allow_html=True)
                    st.markdown(create_stock_card(stock_name, price, change_pct, net_flow, card_type="loser"), unsafe_allow_html=True)
            else:
                st.info("No losers data available yet")

        st.markdown("")

        # Most Active Stocks by Net Flow
        st.markdown("#### 🔥 Top 5 Most Active (By Net Flow)")
        most_active = sorted(stocks_data.items(), key=lambda x: abs(x[1].get('net_flow', 0)), reverse=True)[:5]

        cols = st.columns(5)
        for i, (stock_name, data) in enumerate(most_active):
            with cols[i]:
                net_flow = data.get('net_flow', 0)
                price = data.get('price')
                change_pct = data.get('change_pct')

                flow_emoji = "🟢" if net_flow > 0 else "🔴"
                flow_str = format_number(abs(net_flow))

                st.markdown(f"**{i+1}. {stock_name}**")
                st.metric(f"{flow_emoji} Flow", flow_str)
                if change_pct is not None:
                    change_emoji = "🟢" if change_pct > 0 else "🔴"
                    st.caption(f"{change_emoji} {change_pct:+.2f}%")

st.markdown("---")


# ============================================
# VOLUME SPIKE DETECTION (Unusual Activity)
# ============================================
if cached_data and "stocks_data" in cached_data:
    stocks_data_vol = cached_data.get("stocks_data", {})

    if stocks_data_vol and len(stocks_data_vol) > 0:
        st.markdown("")
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        st.markdown(create_enhanced_section_header("VOLUME SPIKE DETECTION (Unusual Activity)", "🔥"), unsafe_allow_html=True)
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # Calculate volume spikes (based on net flow magnitude)
        # A "volume spike" is when absolute net flow is significantly high
        volume_threshold = 200  # Minimum 200M net flow to be considered

        volume_spikes = []
        for stock_name, data in stocks_data_vol.items():
            net_flow = data.get('net_flow', 0)
            ce_flow = data.get('ce_flow', 0)
            pe_flow = data.get('pe_flow', 0)

            # Calculate total volume (absolute sum of CE + PE)
            total_volume = abs(ce_flow) + abs(pe_flow)

            if abs(net_flow) >= volume_threshold or total_volume >= 500:
                # Calculate volume intensity (how one-sided the flow is)
                if total_volume > 0:
                    intensity = abs(net_flow) / total_volume
                else:
                    intensity = 0

                volume_spikes.append({
                    'name': stock_name,
                    'net_flow': net_flow,
                    'ce_flow': ce_flow,
                    'pe_flow': pe_flow,
                    'total_volume': total_volume,
                    'intensity': intensity,
                    'price': data.get('price'),
                    'change_pct': data.get('change_pct')
                })

        # Sort by total volume (most active)
        volume_spikes_sorted = sorted(volume_spikes, key=lambda x: x['total_volume'], reverse=True)

        # Display summary metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("🔥 Volume Spikes", len(volume_spikes))
            st.caption(f"Net flow ≥ {volume_threshold}M")

        with col2:
            high_intensity = sum(1 for s in volume_spikes if s['intensity'] > 0.7)
            st.metric("⚡ High Intensity", high_intensity)
            st.caption("One-sided flow > 70%")

        with col3:
            bullish_spikes = sum(1 for s in volume_spikes if s['net_flow'] > 0)
            st.metric("🟢 Bullish Spikes", bullish_spikes)
            st.caption("Positive net flow")

        with col4:
            bearish_spikes = sum(1 for s in volume_spikes if s['net_flow'] < 0)
            st.metric("🔴 Bearish Spikes", bearish_spikes)
            st.caption("Negative net flow")

        st.markdown("")

        if volume_spikes_sorted:
            # Display top volume spikes
            st.markdown("#### 📊 Top 10 Volume Spikes (By Total Activity)")

            for i, spike in enumerate(volume_spikes_sorted[:10], 1):
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

                with col1:
                    stock_name = spike['name']
                    price = spike['price']
                    change_pct = spike['change_pct']

                    # Get stock display name with entry count tracking
                    tracking_data = st.session_state.get('stock_entry_tracking', {})
                    # Fallback: Load from JSON if session state is empty
                    if not tracking_data:
                        tracking_data = load_stock_entry_tracking()
                    display_name = get_stock_display_name(stock_name, "volume_spikes", tracking_data)

                    price_str = f"₹{price:,.2f}" if price else "N/A"
                    if change_pct is not None:
                        change_emoji = "🟢" if change_pct > 0 else "🔴"
                        change_str = f"{change_emoji}{change_pct:+.2f}%"
                    else:
                        change_str = ""

                    st.markdown(f"**{i}. {display_name}**")
                    st.caption(f"{price_str} {change_str}")

                    # CE/PE progress bar
                    ce_flow = spike['ce_flow']
                    pe_flow = spike['pe_flow']
                    st.markdown(create_cepe_progress_bar(abs(ce_flow), abs(pe_flow), show_labels=True), unsafe_allow_html=True)

                with col2:
                    # CE Flow
                    ce_emoji = "🟢" if ce_flow > 0 else "🔴"
                    st.metric("CE", f"{ce_emoji}{format_number(ce_flow)}")

                with col3:
                    # PE Flow
                    pe_emoji = "🟢" if pe_flow > 0 else "🔴"
                    st.metric("PE", f"{pe_emoji}{format_number(pe_flow)}")

                with col4:
                    net_flow = spike['net_flow']
                    intensity = spike['intensity']

                    flow_emoji = "🟢" if net_flow > 0 else "🔴"

                    # Intensity indicator
                    if intensity > 0.8:
                        intensity_label = "🔥 Extreme"
                        intensity_color = "red" if net_flow < 0 else "green"
                    elif intensity > 0.6:
                        intensity_label = "⚡ High"
                        intensity_color = "orange"
                    else:
                        intensity_label = "📊 Moderate"
                        intensity_color = "gray"

                    st.metric(f"{flow_emoji} Net", format_number(net_flow))
                    st.caption(f"{intensity_label} ({intensity*100:.0f}%)")

                st.markdown("---")

            # Volume Spike Interpretation Guide
            with st.expander("📖 How to Read Volume Spikes"):
                st.markdown("""
                **What is a Volume Spike?**
                - Unusual high options trading activity in a stock
                - Indicates smart money or institutional interest
                - Can signal upcoming price moves

                **Total Volume:**
                - Sum of CE + PE premium flows (ignores direction)
                - Higher = More active trading

                **Intensity:**
                - How one-sided the flow is
                - **🔥 Extreme (>80%):** Very strong directional bias
                - **⚡ High (60-80%):** Strong directional bias
                - **📊 Moderate (<60%):** Mixed/hedging activity

                **Trading Signals:**
                - **🟢 High Intensity + Positive Net Flow:** Strong bullish signal
                - **🔴 High Intensity + Negative Net Flow:** Strong bearish signal
                - **📊 Low Intensity + High Volume:** Hedging/uncertainty

                **Example:**
                ```
                RELIANCE
                Total Volume: 2000M (very active)
                CE: 1800M | PE: 200M
                Net: +1600M (bullish)
                Intensity: 80% (extreme one-sided)

                → Strong bullish signal! Traders heavily buying calls.
                ```
                """)
        else:
            st.info("No significant volume spikes detected yet. Spikes appear when net flow ≥ 200M")


# ============================================
# UNUSUAL VOLUME ACTIVITY (Relative to 10-Day Average)
# ============================================
if cached_data and "stocks_data" in cached_data:
    stocks_data_unusual = cached_data.get("stocks_data", {})

    if stocks_data_unusual and len(stocks_data_unusual) > 0:
        st.markdown("")
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        st.markdown(create_enhanced_section_header("⚡ UNUSUAL VOLUME ACTIVITY (vs 10-Day Avg)", "📊"), unsafe_allow_html=True)
        st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # Load volume history and calculate spike ratios
        volume_history = load_volume_history()

        # Pass kite and token_meta for API fallback (works from day 1!)
        kite_instance = engine.kite if hasattr(engine, 'kite') else None
        token_meta_df = engine.token_meta if hasattr(engine, 'token_meta') else None

        unusual_stocks = calculate_volume_spike_ratio(
            stocks_data_unusual,
            volume_history,
            kite=kite_instance,
            token_meta=token_meta_df
        )

        if unusual_stocks and len(unusual_stocks) > 0:
            # Display summary metrics
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("⚡ Unusual Stocks", len(unusual_stocks))
                st.caption("Volume >2.0x normal")

            with col2:
                extreme_spikes = sum(1 for s in unusual_stocks if s['spike_ratio'] >= 3.0)
                st.metric("🔥 Extreme Spikes", extreme_spikes)
                st.caption("Volume >3.0x normal")

            with col3:
                bullish_unusual = sum(1 for s in unusual_stocks if s['net_flow'] > 0)
                st.metric("🟢 Bullish Unusual", bullish_unusual)
                st.caption("Positive net flow")

            with col4:
                bearish_unusual = sum(1 for s in unusual_stocks if s['net_flow'] < 0)
                st.metric("🔴 Bearish Unusual", bearish_unusual)
                st.caption("Negative net flow")

            st.markdown("")

            # Display top 10 unusual volume stocks
            st.markdown("#### ⚡ Top 10 Unusual Volume Activity (By Spike Ratio)")

            for i, stock_data in enumerate(unusual_stocks[:10], 1):
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

                with col1:
                    stock_name = stock_data['stock']
                    price = stock_data['price']
                    change_pct = stock_data['change_pct']

                    price_str = f"₹{price:,.2f}" if price else "N/A"
                    if change_pct is not None:
                        change_emoji = "🟢" if change_pct > 0 else "🔴"
                        change_str = f"{change_emoji}{change_pct:+.2f}%"
                    else:
                        change_str = ""

                    st.markdown(f"**{i}. {stock_name}**")
                    st.caption(f"{price_str} {change_str}")

                with col2:
                    spike_ratio = stock_data['spike_ratio']

                    # Intensity indicator
                    if spike_ratio >= 3.0:
                        intensity_label = "🔥 Extreme"
                        intensity_color = "red"
                    elif spike_ratio >= 2.5:
                        intensity_label = "⚡ High"
                        intensity_color = "orange"
                    else:
                        intensity_label = "📊 Moderate"
                        intensity_color = "blue"

                    st.metric("Spike Ratio", f"{spike_ratio:.2f}x")
                    st.caption(intensity_label)

                with col3:
                    today_vol = stock_data['today_volume']
                    avg_vol = stock_data['avg_volume']

                    st.markdown(f"**Today:** {format_number(today_vol)}")
                    st.caption(f"Avg: {format_number(avg_vol)}")

                with col4:
                    net_flow = stock_data['net_flow']
                    flow_emoji = "🟢" if net_flow > 0 else "🔴"

                    st.metric(f"{flow_emoji} Net", format_number(net_flow))
                    if change_pct and change_pct != 0:
                        if abs(change_pct) >= 5:
                            st.caption("💥 Strong move!")
                        elif abs(change_pct) >= 3:
                            st.caption("⚡ Good move")

                st.markdown("---")

            # Interpretation Guide
            with st.expander("📖 How to Read Unusual Volume Activity"):
                st.markdown("""
                **What is Unusual Volume?**
                - Volume significantly higher than the stock's normal trading
                - Indicates smart money or institutional interest
                - Better for catching mid-cap quality moves

                **Spike Ratio:**
                - **Today's Volume / 10-Day Average Volume**
                - **🔥 Extreme (>3.0x):** Very unusual activity - investigate!
                - **⚡ High (2.5-3.0x):** Strong unusual activity
                - **📊 Moderate (2.0-2.5x):** Above normal activity

                **Why This Matters:**
                - Large caps naturally have 200M+ volume daily
                - Mid caps might only have 30M normally
                - **3.0x spike on mid-cap = HUGE relative interest**
                - **1.1x on large-cap = Normal day**

                **Example:**
                ```
                TATAELXSI (Mid-cap IT):
                - Today: 30M volume (Stock up +9%)
                - 10-day avg: 8M volume
                - Spike Ratio: 3.75x 🔥 EXTREME

                → Smart money entering aggressively!
                → Would've been missed in absolute volume rankings
                → Now caught due to relative spike!
                ```

                **Trading Signals:**
                - **High spike + Price up:** Breakout potential
                - **High spike + Price down:** Breakdown or capitulation
                - **Extreme spike:** Major news or big player entering
                """)
        else:
            st.info("🔄 Loading historical volume data from Kite API... This may take a moment on first run.")
            st.caption("💡 Historical data is fetched automatically from Kite API. Feature works from day 1!")


# ============================================
# CHARTINK MOMENTUM ALERTS (Gmail Integration)
# ============================================
st.markdown("")
st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
st.markdown(create_enhanced_section_header("📧 CHARTINK MOMENTUM ALERTS (Gmail)", "⚡"), unsafe_allow_html=True)
st.markdown("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

# Initialize session state for alerts
if 'chartink_alerts' not in st.session_state:
    st.session_state.chartink_alerts = []
if 'chartink_last_fetch' not in st.session_state:
    st.session_state.chartink_last_fetch = None
if 'chartink_last_fetch_time' not in st.session_state:
    st.session_state.chartink_last_fetch_time = None
if 'chartink_fetch_count' not in st.session_state:
    st.session_state.chartink_fetch_count = 0
if 'chartink_auto_fetch_enabled' not in st.session_state:
    st.session_state.chartink_auto_fetch_enabled = True

# UI Debug logging helper - writes to both console and file
from pathlib import Path
ui_debug_dir = Path(r'D:\Stocks Analysis\Apex Nifty Trading\Logs')
# Use DAILY log file (not per-session) so logs don't split across files on st.rerun()
ui_debug_file = ui_debug_dir / f"UI_DEBUG_{datetime.now().strftime('%Y%m%d')}.log"

def log_ui(msg):
    """Write to both console and UI debug file"""
    timestamp = datetime.now().strftime('[%Y-%m-%d %H:%M:%S]')
    full_msg = f"{timestamp} {msg}"
    print(full_msg)
    try:
        ui_debug_dir.mkdir(parents=True, exist_ok=True)
        with open(ui_debug_file, 'a', encoding='utf-8') as f:
            f.write(full_msg + '\n')
    except Exception as e:
        print(f"Failed to write UI debug: {e}")

# Check if Gmail is configured
gmail_configured = bool(os.getenv('GMAIL_USER') and os.getenv('GMAIL_APP_PASSWORD'))

if gmail_configured:
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

    with col1:
        st.caption("✅ Gmail configured | Monitoring: **Alert for Weekly close=high/low ONLY**")

    with col2:
        # Mode selector
        test_mode = st.checkbox("🧪 TEST Mode", value=False, help="TEST: Last 30 days (read-only) | LIVE: Unread emails only")

    with col3:
        # Auto-fetch toggle (only for LIVE mode)
        if not test_mode:
            auto_fetch = st.checkbox("⚡ Auto-fetch", value=st.session_state.chartink_auto_fetch_enabled,
                                    help="Auto-fetch new alerts: First fetch after 5min, then every 30sec")
            if auto_fetch != st.session_state.chartink_auto_fetch_enabled:
                st.session_state.chartink_auto_fetch_enabled = auto_fetch
                st.rerun()

    with col4:
        # Clear button
        if st.button("🗑️ Clear", help="Clear displayed alerts"):
            st.session_state.chartink_alerts = []
            st.session_state.chartink_last_fetch = None
            st.session_state.chartink_last_fetch_time = None
            st.session_state.chartink_fetch_count = 0
            st.rerun()

    # AUTO-FETCH LOGIC (only in LIVE mode with auto-fetch enabled)
    should_auto_fetch = False
    if not test_mode and st.session_state.chartink_auto_fetch_enabled:
        now = datetime.now()

        if st.session_state.chartink_last_fetch_time is None:
            # First time - fetch immediately
            should_auto_fetch = True
            log_ui("🤖 AUTO-FETCH: First fetch triggered")
        else:
            last_fetch_time = st.session_state.chartink_last_fetch_time
            seconds_since_last = (now - last_fetch_time).total_seconds()

            if st.session_state.chartink_fetch_count == 1:
                # After first fetch, wait 5 minutes before second fetch
                if seconds_since_last >= 300:  # 5 minutes
                    should_auto_fetch = True
                    log_ui(f"🤖 AUTO-FETCH: 5 min interval reached ({seconds_since_last:.0f}s since last)")
            else:
                # After second fetch, check every 30 seconds
                if seconds_since_last >= 30:
                    should_auto_fetch = True
                    log_ui(f"🤖 AUTO-FETCH: 30 sec interval reached ({seconds_since_last:.0f}s since last)")

    # Execute auto-fetch if triggered
    if should_auto_fetch:
        mode = 'LIVE'
        log_ui(f"🤖 AUTO-FETCH STARTING - Fetch #{st.session_state.chartink_fetch_count + 1}")

        with st.spinner(f"Auto-fetching new alerts..."):
            alerts = fetch_chartink_alerts(mode=mode)

        log_ui(f"✅ AUTO-FETCH COMPLETED: {len(alerts)} alerts")

        # Update tracking
        st.session_state.chartink_alerts = alerts
        st.session_state.chartink_last_fetch = datetime.now().strftime('%I:%M:%S %p')
        st.session_state.chartink_last_fetch_time = datetime.now()
        st.session_state.chartink_fetch_count += 1

        st.rerun()

    # Manual fetch alerts button
    if st.button("📬 Fetch Now", type="primary"):
        mode = 'TEST' if test_mode else 'LIVE'

        log_ui(f"🔵 FETCH BUTTON CLICKED - Mode: {mode}")
        log_ui(f"⏳ Starting fetch... This takes ~60-90 seconds. Please wait and do NOT refresh the page!")

        with st.spinner(f"Fetching alerts in {mode} mode... Please wait ~60-90 seconds..."):
            alerts = fetch_chartink_alerts(mode=mode)

        # DEBUG: Print what we got
        log_ui(f"✅ FETCH COMPLETED: Received {len(alerts)} alerts from fetch_chartink_alerts()")
        log_ui(f"📄 Alerts saved to JSON file by fetch function")

        # Store in session state for immediate display
        st.session_state.chartink_alerts = alerts
        st.session_state.chartink_last_fetch = datetime.now().strftime('%I:%M:%S %p')
        st.session_state.chartink_last_fetch_time = datetime.now()
        st.session_state.chartink_fetch_count += 1
        log_ui(f"💾 Stored {len(alerts)} alerts in session_state (Fetch #{st.session_state.chartink_fetch_count})")

        # Force page reload to display
        log_ui(f"🔄 Triggering page reload to display alerts...")
        st.rerun()

    # Show auto-fetch status
    if not test_mode and st.session_state.chartink_auto_fetch_enabled:
        if st.session_state.chartink_last_fetch_time:
            now = datetime.now()
            seconds_since = (now - st.session_state.chartink_last_fetch_time).total_seconds()

            if st.session_state.chartink_fetch_count == 1:
                # After first fetch, wait 5 minutes
                next_fetch_in = 300 - seconds_since
                if next_fetch_in > 0:
                    st.info(f"⚡ Auto-fetch enabled | Next fetch in: {int(next_fetch_in)}s (waiting 5 min after first fetch)")
                else:
                    st.info(f"⚡ Auto-fetch enabled | Fetching on next refresh...")
            else:
                # After second fetch, every 30 seconds
                next_fetch_in = 30 - seconds_since
                if next_fetch_in > 0:
                    st.info(f"⚡ Auto-fetch enabled | Next fetch in: {int(next_fetch_in)}s (every 30s)")
                else:
                    st.info(f"⚡ Auto-fetch enabled | Fetching on next refresh...")
        else:
            st.info(f"⚡ Auto-fetch enabled | Will fetch on next refresh...")

    # Display alerts - try session_state first, then fall back to file
    # DEBUG: Check what's in session state
    log_ui(f"📊 DISPLAY SECTION - session_state has {len(st.session_state.chartink_alerts)} alerts")

    # If session_state is empty, try loading from file
    if not st.session_state.chartink_alerts:
        import json
        alerts_file = ui_debug_dir / "chartink_alerts.json"
        if alerts_file.exists():
            try:
                log_ui(f"📂 Session state empty - Loading from file: {alerts_file}")
                with open(alerts_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    alerts_from_file = data.get('alerts', [])

                    # Convert timestamp strings back to datetime for display
                    for alert in alerts_from_file:
                        if 'timestamp' in alert and isinstance(alert['timestamp'], str):
                            try:
                                alert['timestamp'] = datetime.strptime(alert['timestamp'], '%Y-%m-%d %H:%M:%S')
                            except:
                                pass

                    st.session_state.chartink_alerts = alerts_from_file
                    st.session_state.chartink_last_fetch = data.get('last_fetch')
                    log_ui(f"✅ Loaded {len(alerts_from_file)} alerts from file")
            except Exception as e:
                log_ui(f"❌ ERROR loading from file: {e}")

    if st.session_state.chartink_alerts:
        log_ui(f"✅ DISPLAY: Found alerts to display - {len(st.session_state.chartink_alerts)} total")
        alerts = st.session_state.chartink_alerts

        # Show last fetch time
        if st.session_state.chartink_last_fetch:
            st.success(f"✅ Found {len(alerts)} momentum alert(s) | Last fetched: {st.session_state.chartink_last_fetch}")
        else:
            st.success(f"✅ Found {len(alerts)} momentum alert(s)")

        # Separate by direction
        long_alerts = [a for a in alerts if a['direction'] == 'LONG']
        bearish_alerts = [a for a in alerts if a['direction'] == 'SHORT']

        log_ui(f"📈 LONG alerts: {len(long_alerts)}, 📉 SHORT alerts: {len(bearish_alerts)}")

        # Display in columns
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### 🟢 BULLISH ALERTS (LONG)")
            st.caption("Weekly close = Weekly high")

            if long_alerts:
                for alert in long_alerts:
                    stocks_str = ', '.join(alert['stocks']) if alert['stocks'] else 'None'
                    timestamp_str = alert['timestamp'].strftime('%b %d, %I:%M %p') if hasattr(alert['timestamp'], 'strftime') else alert['date'][:20]

                    with st.container():
                        st.markdown(f"**📈 {stocks_str}**")
                        st.caption(f"⏰ {timestamp_str}")
                        st.markdown("---")
            else:
                st.info("No bullish alerts found")

        with col2:
            st.markdown("### 🔴 BEARISH ALERTS (SHORT)")
            st.caption("Weekly close = Weekly low")

            if bearish_alerts:
                for alert in bearish_alerts:
                    stocks_str = ', '.join(alert['stocks']) if alert['stocks'] else 'None'
                    timestamp_str = alert['timestamp'].strftime('%b %d, %I:%M %p') if hasattr(alert['timestamp'], 'strftime') else alert['date'][:20]

                    with st.container():
                        st.markdown(f"**📉 {stocks_str}**")
                        st.caption(f"⏰ {timestamp_str}")
                        st.markdown("---")
            else:
                st.info("No bearish alerts found")
    elif st.session_state.chartink_last_fetch:
        log_ui(f"⚠️ DISPLAY: No alerts in session_state but last_fetch exists: {st.session_state.chartink_last_fetch}")
        st.info(f"No momentum alerts found | Last fetched: {st.session_state.chartink_last_fetch}")
    else:
        log_ui(f"ℹ️ DISPLAY: No alerts and no last_fetch - first load")
        st.info("Click 'Fetch Chartink Alerts' to load momentum alerts")

    # Info expander
    st.markdown("")
    with st.expander("ℹ️ How Chartink Gmail Integration Works"):
        st.markdown("""
        **What This Does:**
        - Connects to your Gmail account via IMAP
        - Fetches Chartink scan alerts for momentum conditions
        - Classifies alerts as LONG (bullish) or SHORT (bearish)

        **Alert Criteria:**
        - 🟢 **LONG:** "Alert for Weekly close=high" → Bullish momentum
        - 🔴 **SHORT:** "Alert for Weekly close=low" → Bearish momentum

        **Modes:**
        - **LIVE Mode:**
          - Fetches only UNSEEN emails
          - Marks processed emails as SEEN
          - Use during market hours for real-time alerts

        - **TEST Mode:**
          - Fetches last 30 days of emails
          - Does NOT mark as read
          - Safe for testing/debugging

        **Setup Required:**
        1. Add to `.env` file:
           ```
           GMAIL_USER=your_email@gmail.com
           GMAIL_APP_PASSWORD=your_16_char_password
           ```
        2. Generate Gmail App Password:
           - Google Account → Security → 2-Step Verification
           - App passwords → Mail → Generate

        **Output:**
        - Stock names extracted from email body
        - Direction (LONG/SHORT)
        - Alert timestamp
        - Printed to console for logging
        """)
else:
    st.warning("⚠️ Gmail not configured")
    st.info("""
    **To enable Chartink alerts:**

    1. Add to your `.env` file:
       ```
       GMAIL_USER=your_email@gmail.com
       GMAIL_APP_PASSWORD=your_16_char_app_password
       ```

    2. Generate Gmail App Password:
       - Google Account → Security
       - Enable 2-Step Verification
       - App passwords → Select Mail → Generate
       - Copy 16-character password

    3. Restart the application
    """)


# ============================================
# MOMENTUM STOCKS (Bullish & Bearish) - REMOVED FROM UI
# ============================================
# NOTE: Backend momentum tracking still runs for Smart Scoring Alert System
# UI section removed per user request - alerts will be handled separately

st.markdown("---")


st.caption("🔥 Live Momentum Trading System - Actionable Alerts with Strike Prices! 🚀")