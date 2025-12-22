# patterns.py - PATTERN DETECTION ENGINE
# Implements 8 pattern types for live momentum trading
# Searches historical data for similar scenarios and calculates success rates

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# =========================
# CONFIGURATION
# =========================

HISTORICAL_DIR = Path("data/historical/indices")
TOLERANCE = 0.20  # ±20% tolerance for similarity matching
MIN_MATCHES = 3   # Minimum matches required to generate alert
SUCCESS_THRESHOLD = 0.70  # 70% success rate required
LOOKBACK_MINUTES = 30  # Check outcomes 30 minutes after pattern

# Pattern thresholds
SIDEWAYS_THRESHOLD = 0.5  # ±0.5% is considered sideways
SURGE_MULTIPLIER = 2.0    # 2x average delta is a "surge"
REVERSAL_THRESHOLD = 1.0  # ±1.0% price change

# =========================
# DATA LOADING
# =========================

def load_historical_data(index_name: str, days_back: int = 7) -> pd.DataFrame:
    """
    Load historical data for an index from CSV files
    
    Args:
        index_name: Index name (NIFTY, BANKNIFTY, etc.)
        days_back: Number of days to load
    
    Returns:
        DataFrame with all historical data
    """
    all_data = []
    
    # Get date range
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back)
    
    current_date = start_date
    while current_date <= end_date:
        csv_file = HISTORICAL_DIR / str(current_date) / f"{index_name}.csv"
        
        if csv_file.exists():
            try:
                df = pd.read_csv(csv_file)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                all_data.append(df)
                print(f"✓ Loaded {len(df)} records from {current_date} for {index_name}")
            except Exception as e:
                print(f"⚠️ Error loading {csv_file}: {e}")
        
        current_date += timedelta(days=1)
    
    if not all_data:
        print(f"⚠️ No historical data found for {index_name}")
        return pd.DataFrame()
    
    # Combine all data
    combined_df = pd.concat(all_data, ignore_index=True)
    combined_df = combined_df.sort_values('timestamp').reset_index(drop=True)
    
    print(f"📊 Total records loaded for {index_name}: {len(combined_df)}")
    return combined_df

def get_available_data_days(index_name: str) -> int:
    """Check how many days of data are available"""
    days = 0
    end_date = datetime.now().date()
    
    for i in range(30):  # Check last 30 days
        check_date = end_date - timedelta(days=i)
        csv_file = HISTORICAL_DIR / str(check_date) / f"{index_name}.csv"
        if csv_file.exists():
            days += 1
    
    return days

# =========================
# PATTERN STATE DETECTION
# =========================

def get_market_state(recent_data: pd.DataFrame, current_row: pd.Series) -> Dict:
    """
    Determine current market state from recent data
    
    Args:
        recent_data: Last 5-10 minutes of data
        current_row: Current data point
    
    Returns:
        Dictionary with market state info
    """
    if len(recent_data) < 2:
        return None
    
    # Calculate averages
    avg_price_change = recent_data['price_change_pct'].mean()
    avg_ce_delta = recent_data.get('delta_1min_ce', pd.Series([0])).mean()
    avg_pe_delta = recent_data.get('delta_1min_pe', pd.Series([0])).mean()
    
    # Current values
    current_price_change = current_row.get('price_change_pct', 0)
    current_ce_delta = current_row.get('delta_1min_ce', 0)
    current_pe_delta = current_row.get('delta_1min_pe', 0)
    current_ce_flow = current_row.get('ce_flow', 0)
    current_pe_flow = current_row.get('pe_flow', 0)
    
    state = {
        'timestamp': current_row['timestamp'],
        'index_name': current_row['index_name'],
        'spot_price': current_row.get('spot_price', 0),
        'price_change_pct': current_price_change,
        'avg_price_change': avg_price_change,
        'ce_delta': current_ce_delta,
        'pe_delta': current_pe_delta,
        'avg_ce_delta': avg_ce_delta,
        'avg_pe_delta': avg_pe_delta,
        'ce_flow': current_ce_flow,
        'pe_flow': current_pe_flow,
        'net_flow': current_ce_flow - current_pe_flow,
        'sentiment': current_row.get('sentiment', 'UNKNOWN'),
        'range_status': current_row.get('range_status', 'UNKNOWN'),
        'futures_volume': current_row.get('futures_volume', 0),
        'avg_volume': current_row.get('avg_volume', 0)
    }
    
    return state

# =========================
# PATTERN DETECTION FUNCTIONS
# =========================

def detect_sideways_to_bullish(state: Dict) -> bool:
    """
    Pattern 1: Sideways → Bullish Surge
    
    Conditions:
    - Market was sideways (price change < ±0.5%) 
    - Sudden CE surge (delta > 2x average)
    - PE flow flat or decreasing
    - Price starting to move up
    """
    if not state or state['avg_ce_delta'] == 0:
        return False
    
    is_sideways = abs(state['avg_price_change']) < SIDEWAYS_THRESHOLD
    ce_surge = state['ce_delta'] > (SURGE_MULTIPLIER * abs(state['avg_ce_delta']))
    pe_flat = state['pe_delta'] <= abs(state['avg_pe_delta'])
    price_rising = state['price_change_pct'] > 0.1
    
    return is_sideways and ce_surge and pe_flat and price_rising

def detect_sideways_to_bearish(state: Dict) -> bool:
    """
    Pattern 2: Sideways → Bearish Crash
    
    Conditions:
    - Market was sideways
    - Sudden PE surge
    - CE flow flat or decreasing
    - Price starting to fall
    """
    if not state or state['avg_pe_delta'] == 0:
        return False
    
    is_sideways = abs(state['avg_price_change']) < SIDEWAYS_THRESHOLD
    pe_surge = state['pe_delta'] > (SURGE_MULTIPLIER * abs(state['avg_pe_delta']))
    ce_flat = state['ce_delta'] <= abs(state['avg_ce_delta'])
    price_falling = state['price_change_pct'] < -0.1
    
    return is_sideways and pe_surge and ce_flat and price_falling

def detect_bullish_continuation(state: Dict) -> bool:
    """
    Pattern 3: Bullish Continuation
    
    Conditions:
    - Market already rising (avg > +0.5%)
    - CE surge continues
    - Strong momentum
    """
    if not state or state['avg_ce_delta'] == 0:
        return False
    
    market_rising = state['avg_price_change'] > SIDEWAYS_THRESHOLD
    ce_surge = state['ce_delta'] > (SURGE_MULTIPLIER * abs(state['avg_ce_delta']))
    price_rising = state['price_change_pct'] > 0.3
    
    return market_rising and ce_surge and price_rising

def detect_bearish_continuation(state: Dict) -> bool:
    """
    Pattern 4: Bearish Continuation
    
    Conditions:
    - Market already falling (avg < -0.5%)
    - PE surge continues
    - Strong downward momentum
    """
    if not state or state['avg_pe_delta'] == 0:
        return False
    
    market_falling = state['avg_price_change'] < -SIDEWAYS_THRESHOLD
    pe_surge = state['pe_delta'] > (SURGE_MULTIPLIER * abs(state['avg_pe_delta']))
    price_falling = state['price_change_pct'] < -0.3
    
    return market_falling and pe_surge and price_falling

def detect_bullish_reversal(state: Dict) -> bool:
    """
    Pattern 5: Bullish Reversal
    
    Conditions:
    - Market was falling (avg < -1.0%)
    - Sudden CE buying surge
    - Reversal signal
    """
    if not state or state['avg_ce_delta'] == 0:
        return False
    
    was_falling = state['avg_price_change'] < -REVERSAL_THRESHOLD
    ce_surge = state['ce_delta'] > (SURGE_MULTIPLIER * abs(state['avg_ce_delta']))
    price_stabilizing = state['price_change_pct'] > -0.5
    
    return was_falling and ce_surge and price_stabilizing

def detect_bearish_reversal(state: Dict) -> bool:
    """
    Pattern 6: Bearish Reversal
    
    Conditions:
    - Market was rising (avg > +1.0%)
    - Sudden PE buying surge
    - Reversal signal
    """
    if not state or state['avg_pe_delta'] == 0:
        return False
    
    was_rising = state['avg_price_change'] > REVERSAL_THRESHOLD
    pe_surge = state['pe_delta'] > (SURGE_MULTIPLIER * abs(state['avg_pe_delta']))
    price_stabilizing = state['price_change_pct'] < 0.5
    
    return was_rising and pe_surge and price_stabilizing

def detect_range_breakout_flow(state: Dict) -> bool:
    """
    Pattern 7: Range Breakout + Flow Confirmation
    
    Conditions:
    - Price broke 15min range
    - Flow confirms direction
    - Volume confirmation
    """
    if not state:
        return False
    
    is_breakout = 'BREAKER' in state.get('range_status', '')
    
    if 'HIGH' in state.get('range_status', ''):
        # Bullish breakout - CE should surge
        flow_confirms = state['ce_delta'] > abs(state['pe_delta'])
    elif 'LOW' in state.get('range_status', ''):
        # Bearish breakout - PE should surge
        flow_confirms = state['pe_delta'] > abs(state['ce_delta'])
    else:
        flow_confirms = False
    
    volume_confirms = True  # Already checked in range_status
    
    return is_breakout and flow_confirms and volume_confirms

def detect_false_breakout(state: Dict) -> bool:
    """
    Pattern 8: False Breakout Detection
    
    Conditions:
    - Price broke range
    - Flow contradicts direction
    - Warning signal
    """
    if not state:
        return False
    
    is_breakout = 'BREAKER' in state.get('range_status', '')
    
    if 'HIGH' in state.get('range_status', ''):
        # Bullish breakout but PE surging (contradiction)
        flow_contradicts = state['pe_delta'] > state['ce_delta']
    elif 'LOW' in state.get('range_status', ''):
        # Bearish breakout but CE surging (contradiction)
        flow_contradicts = state['ce_delta'] > state['pe_delta']
    else:
        flow_contradicts = False
    
    return is_breakout and flow_contradicts

# =========================
# PATTERN MATCHER
# =========================

PATTERN_DETECTORS = {
    'SIDEWAYS_TO_BULLISH': detect_sideways_to_bullish,
    'SIDEWAYS_TO_BEARISH': detect_sideways_to_bearish,
    'BULLISH_CONTINUATION': detect_bullish_continuation,
    'BEARISH_CONTINUATION': detect_bearish_continuation,
    'BULLISH_REVERSAL': detect_bullish_reversal,
    'BEARISH_REVERSAL': detect_bearish_reversal,
    'RANGE_BREAKOUT_FLOW': detect_range_breakout_flow,
    'FALSE_BREAKOUT': detect_false_breakout
}

PATTERN_DIRECTIONS = {
    'SIDEWAYS_TO_BULLISH': 'BULLISH',
    'SIDEWAYS_TO_BEARISH': 'BEARISH',
    'BULLISH_CONTINUATION': 'BULLISH',
    'BEARISH_CONTINUATION': 'BEARISH',
    'BULLISH_REVERSAL': 'BULLISH',
    'BEARISH_REVERSAL': 'BEARISH',
    'RANGE_BREAKOUT_FLOW': 'DEPENDS',
    'FALSE_BREAKOUT': 'WARNING'
}

def detect_current_pattern(state: Dict) -> Optional[str]:
    """
    Detect which pattern (if any) matches current state
    
    Returns:
        Pattern name or None
    """
    if not state:
        return None
    
    for pattern_name, detector_func in PATTERN_DETECTORS.items():
        if detector_func(state):
            return pattern_name
    
    return None

# =========================
# SIMILARITY MATCHING
# =========================

def find_similar_scenarios(historical_df: pd.DataFrame, 
                          target_state: Dict, 
                          tolerance: float = TOLERANCE) -> List[int]:
    """
    Find historical scenarios similar to target state
    
    Args:
        historical_df: Historical data
        target_state: Current state to match
        tolerance: Similarity tolerance (default ±20%)
    
    Returns:
        List of indices matching criteria
    """
    if historical_df.empty or not target_state:
        return []
    
    matches = []
    
    # Key metrics to match
    target_ce_delta = target_state.get('ce_delta', 0)
    target_pe_delta = target_state.get('pe_delta', 0)
    target_price_change = target_state.get('price_change_pct', 0)
    
    for idx, row in historical_df.iterrows():
        # Skip if missing data
        if pd.isna(row.get('delta_1min_ce')) or pd.isna(row.get('delta_1min_pe')):
            continue
        
        hist_ce_delta = row.get('delta_1min_ce', 0)
        hist_pe_delta = row.get('delta_1min_pe', 0)
        hist_price_change = row.get('price_change_pct', 0)
        
        # Check similarity within tolerance
        ce_match = abs(hist_ce_delta - target_ce_delta) <= (abs(target_ce_delta) * tolerance) if target_ce_delta != 0 else abs(hist_ce_delta) < 1000
        pe_match = abs(hist_pe_delta - target_pe_delta) <= (abs(target_pe_delta) * tolerance) if target_pe_delta != 0 else abs(hist_pe_delta) < 1000
        price_match = abs(hist_price_change - target_price_change) <= tolerance
        
        # Sentiment must match
        sentiment_match = row.get('sentiment', '') == target_state.get('sentiment', '')
        
        if ce_match and pe_match and price_match and sentiment_match:
            matches.append(idx)
    
    return matches

# =========================
# OUTCOME ANALYSIS
# =========================

def analyze_outcomes(historical_df: pd.DataFrame, 
                     match_indices: List[int],
                     pattern_direction: str,
                     lookback_minutes: int = LOOKBACK_MINUTES) -> Dict:
    """
    Analyze what happened after matched scenarios
    
    Args:
        historical_df: Historical data
        match_indices: Indices of matched scenarios
        pattern_direction: Expected direction (BULLISH/BEARISH/WARNING)
        lookback_minutes: Minutes to check outcome
    
    Returns:
        Dictionary with success rate and statistics
    """
    if not match_indices:
        return {
            'total_matches': 0,
            'successful': 0,
            'failed': 0,
            'success_rate': 0.0,
            'avg_gain': 0.0,
            'avg_time': 0,
            'examples': []
        }
    
    successful = 0
    failed = 0
    gains = []
    times = []
    examples = []
    
    for idx in match_indices:
        if idx >= len(historical_df):
            continue
        
        match_row = historical_df.iloc[idx]
        match_time = match_row['timestamp']
        match_price = match_row.get('spot_price', 0)
        
        if match_price == 0:
            continue
        
        # Find data points after this match
        future_data = historical_df[
            (historical_df['timestamp'] > match_time) &
            (historical_df['timestamp'] <= match_time + timedelta(minutes=lookback_minutes))
        ]
        
        if future_data.empty:
            continue
        
        # Check price movement
        max_price = future_data['spot_price'].max()
        min_price = future_data['spot_price'].min()
        final_price = future_data.iloc[-1]['spot_price']
        
        price_change_pct = ((final_price - match_price) / match_price) * 100
        max_gain = ((max_price - match_price) / match_price) * 100
        max_loss = ((min_price - match_price) / match_price) * 100
        
        # Determine success based on direction
        is_success = False
        
        if pattern_direction == 'BULLISH':
            is_success = price_change_pct > 1.0  # Moved up >1%
        elif pattern_direction == 'BEARISH':
            is_success = price_change_pct < -1.0  # Moved down >1%
        elif pattern_direction == 'WARNING':
            # For false breakout, success = reversal happened
            is_success = abs(price_change_pct) < 0.5  # Price didn't continue
        
        if is_success:
            successful += 1
        else:
            failed += 1
        
        gains.append(price_change_pct)
        
        # Calculate time to target (rough estimate)
        time_minutes = len(future_data) * 0.17  # ~10 seconds per row
        times.append(time_minutes)
        
        # Store example
        examples.append({
            'timestamp': match_time,
            'price_change': price_change_pct,
            'max_gain': max_gain,
            'max_loss': max_loss,
            'success': is_success
        })
    
    total = successful + failed
    success_rate = (successful / total) if total > 0 else 0.0
    avg_gain = np.mean(gains) if gains else 0.0
    avg_time = np.mean(times) if times else 0
    
    return {
        'total_matches': total,
        'successful': successful,
        'failed': failed,
        'success_rate': success_rate,
        'avg_gain': avg_gain,
        'avg_time': avg_time,
        'examples': sorted(examples, key=lambda x: x['timestamp'], reverse=True)[:5]  # Last 5
    }

# =========================
# MAIN PATTERN ANALYSIS
# =========================

def analyze_pattern(index_name: str, current_state: Dict, days_back: int = 7) -> Optional[Dict]:
    """
    Main function to analyze if current state matches a pattern
    
    Args:
        index_name: Index name
        current_state: Current market state
        days_back: Days of historical data to analyze
    
    Returns:
        Pattern analysis result or None
    """
    # Detect pattern
    pattern_name = detect_current_pattern(current_state)
    
    if not pattern_name:
        return None
    
    # Load historical data
    historical_df = load_historical_data(index_name, days_back)
    
    if historical_df.empty:
        print(f"⚠️ No historical data for pattern matching")
        return None
    
    # Find similar scenarios
    matches = find_similar_scenarios(historical_df, current_state, TOLERANCE)
    
    if len(matches) < MIN_MATCHES:
        print(f"ℹ️ Pattern detected but insufficient matches ({len(matches)} < {MIN_MATCHES})")
        return None
    
    # Analyze outcomes
    pattern_direction = PATTERN_DIRECTIONS.get(pattern_name, 'UNKNOWN')
    outcomes = analyze_outcomes(historical_df, matches, pattern_direction)
    
    # Check if success rate meets threshold
    if outcomes['success_rate'] < SUCCESS_THRESHOLD:
        print(f"ℹ️ Pattern success rate too low ({outcomes['success_rate']:.0%} < {SUCCESS_THRESHOLD:.0%})")
        return None
    
    # Return complete analysis
    return {
        'pattern_name': pattern_name,
        'pattern_direction': pattern_direction,
        'current_state': current_state,
        'outcomes': outcomes,
        'confidence': 'HIGH' if outcomes['success_rate'] >= 0.80 else 'MODERATE'
    }
