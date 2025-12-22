# oi_liquidity.py - OI & LIQUIDITY INTEGRATION
# Fetches Open Interest and filters for liquid strikes

from typing import Dict, Optional, List, Tuple
import pandas as pd
from datetime import datetime

# =========================
# LIQUIDITY THRESHOLDS
# =========================

# Minimum thresholds (will be optimized from data later)
LIQUIDITY_THRESHOLDS = {
    'NIFTY': {
        'min_oi': 100_000,
        'min_volume': 10_000,
        'max_bid_ask_spread': 2.0  # percentage
    },
    'BANKNIFTY': {
        'min_oi': 50_000,
        'min_volume': 5_000,
        'max_bid_ask_spread': 2.0
    },
    'FINNIFTY': {
        'min_oi': 20_000,
        'min_volume': 2_000,
        'max_bid_ask_spread': 3.0
    },
    'MIDCPNIFTY': {
        'min_oi': 20_000,
        'min_volume': 2_000,
        'max_bid_ask_spread': 3.0
    },
    'SENSEX': {
        'min_oi': 20_000,
        'min_volume': 2_000,
        'max_bid_ask_spread': 3.0
    }
}

# Default thresholds for stocks
DEFAULT_STOCK_THRESHOLDS = {
    'min_oi': 10_000,
    'min_volume': 1_000,
    'max_bid_ask_spread': 3.0
}

# =========================
# OI DATA FETCHING
# =========================

def get_option_oi_data(kite, ins_df, index_name: str, strike: int, option_type: str) -> Optional[Dict]:
    """
    Fetch OI and liquidity data for a specific option strike
    
    Args:
        kite: KiteConnect instance
        ins_df: Instruments DataFrame
        index_name: Index name (NIFTY, BANKNIFTY, etc.)
        strike: Strike price
        option_type: 'CE' or 'PE'
    
    Returns:
        Dictionary with OI data or None
    """
    try:
        # Find the option in instruments
        DERIV_OPT_SEGMENTS = {"NFO-OPT", "BFO-OPT"}
        
        option_data = ins_df[
            (ins_df["name"] == index_name) &
            (ins_df["strike"] == strike) &
            (ins_df["instrument_type"] == option_type) &
            (ins_df["segment"].isin(DERIV_OPT_SEGMENTS))
        ]
        
        if option_data.empty:
            return None
        
        # Get the instrument token
        option_token = int(option_data.iloc[0]["instrument_token"])
        
        # Fetch quote data
        quote = kite.quote([option_token])
        
        if not quote or str(option_token) not in quote:
            return None
        
        quote_data = quote[str(option_token)]
        
        # Extract OI and liquidity metrics
        oi = quote_data.get('oi', 0)
        volume = quote_data.get('volume', 0)
        last_price = quote_data.get('last_price', 0)
        
        # Get bid-ask spread
        ohlc = quote_data.get('ohlc', {})
        depth = quote_data.get('depth', {})
        
        # Calculate bid-ask spread
        buy_prices = depth.get('buy', [])
        sell_prices = depth.get('sell', [])
        
        if buy_prices and sell_prices:
            best_bid = buy_prices[0].get('price', 0) if buy_prices else 0
            best_ask = sell_prices[0].get('price', 0) if sell_prices else 0
            
            if best_bid > 0 and best_ask > 0:
                bid_ask_spread = ((best_ask - best_bid) / best_bid) * 100
            else:
                bid_ask_spread = 0
        else:
            bid_ask_spread = 0
        
        # Last traded time
        last_trade_time = quote_data.get('last_trade_time', None)
        
        return {
            'instrument_token': option_token,
            'strike': strike,
            'option_type': option_type,
            'oi': oi,
            'volume': volume,
            'last_price': last_price,
            'bid_ask_spread': bid_ask_spread,
            'last_trade_time': last_trade_time,
            'tradingsymbol': option_data.iloc[0]['tradingsymbol']
        }
    
    except Exception as e:
        print(f"Error fetching OI data for {index_name} {strike} {option_type}: {e}")
        return None

# =========================
# LIQUIDITY SCORING
# =========================

def calculate_liquidity_score(oi_data: Dict, index_name: str) -> Dict:
    """
    Calculate liquidity score and rating
    
    Args:
        oi_data: OI data dictionary
        index_name: Index name
    
    Returns:
        Dictionary with liquidity metrics
    """
    if not oi_data:
        return {
            'score': 0,
            'rating': 'POOR',
            'recommendation': 'AVOID',
            'reasons': ['No data available']
        }
    
    # Get thresholds for this index
    thresholds = LIQUIDITY_THRESHOLDS.get(index_name, DEFAULT_STOCK_THRESHOLDS)
    
    oi = oi_data.get('oi', 0)
    volume = oi_data.get('volume', 0)
    bid_ask_spread = oi_data.get('bid_ask_spread', 100)
    
    # Calculate score components (0-100 each)
    oi_score = min(100, (oi / thresholds['min_oi']) * 100) if thresholds['min_oi'] > 0 else 0
    volume_score = min(100, (volume / thresholds['min_volume']) * 100) if thresholds['min_volume'] > 0 else 0
    spread_score = max(0, 100 - (bid_ask_spread / thresholds['max_bid_ask_spread']) * 100)
    
    # Overall score (weighted average)
    overall_score = (oi_score * 0.4) + (volume_score * 0.4) + (spread_score * 0.2)
    
    # Determine rating
    if overall_score >= 80:
        rating = 'EXCELLENT'
        recommendation = 'STRONG BUY'
    elif overall_score >= 60:
        rating = 'GOOD'
        recommendation = 'BUY'
    elif overall_score >= 40:
        rating = 'MODERATE'
        recommendation = 'CAUTION'
    elif overall_score >= 20:
        rating = 'POOR'
        recommendation = 'AVOID'
    else:
        rating = 'VERY POOR'
        recommendation = 'DO NOT TRADE'
    
    # Identify reasons
    reasons = []
    
    if oi >= thresholds['min_oi'] * 2:
        reasons.append('Excellent OI')
    elif oi >= thresholds['min_oi']:
        reasons.append('Good OI')
    else:
        reasons.append('Low OI - Risk of illiquidity')
    
    if volume >= thresholds['min_volume'] * 2:
        reasons.append('High volume')
    elif volume >= thresholds['min_volume']:
        reasons.append('Adequate volume')
    else:
        reasons.append('Low volume - May have slippage')
    
    if bid_ask_spread <= thresholds['max_bid_ask_spread'] * 0.5:
        reasons.append('Tight spreads')
    elif bid_ask_spread <= thresholds['max_bid_ask_spread']:
        reasons.append('Acceptable spreads')
    else:
        reasons.append('Wide spreads - High cost')
    
    return {
        'score': round(overall_score, 1),
        'rating': rating,
        'recommendation': recommendation,
        'reasons': reasons,
        'component_scores': {
            'oi_score': round(oi_score, 1),
            'volume_score': round(volume_score, 1),
            'spread_score': round(spread_score, 1)
        }
    }

# =========================
# FIND BEST LIQUID STRIKE
# =========================

def find_best_liquid_strikes(kite, ins_df, index_name: str, 
                             atm_strike: int, option_type: str,
                             num_strikes: int = 3) -> List[Dict]:
    """
    Find best liquid strikes near ATM
    
    Args:
        kite: KiteConnect instance
        ins_df: Instruments DataFrame
        index_name: Index name
        atm_strike: ATM strike price
        option_type: 'CE' or 'PE'
        num_strikes: Number of strikes to check
    
    Returns:
        List of strikes sorted by liquidity score
    """
    step_map = {"BANKNIFTY": 100, "NIFTY": 50, "FINNIFTY": 50, "MIDCPNIFTY": 25, "SENSEX": 100}
    step = step_map.get(index_name, 50)
    
    # Get strikes to check (ATM and nearby)
    strikes_to_check = []
    for i in range(-num_strikes, num_strikes + 1):
        strike = atm_strike + (i * step)
        strikes_to_check.append(strike)
    
    # Fetch OI data for each strike
    strike_data = []
    
    for strike in strikes_to_check:
        oi_data = get_option_oi_data(kite, ins_df, index_name, strike, option_type)
        
        if oi_data:
            liquidity = calculate_liquidity_score(oi_data, index_name)
            
            strike_data.append({
                'strike': strike,
                'oi': oi_data['oi'],
                'volume': oi_data['volume'],
                'last_price': oi_data['last_price'],
                'bid_ask_spread': oi_data['bid_ask_spread'],
                'liquidity_score': liquidity['score'],
                'liquidity_rating': liquidity['rating'],
                'recommendation': liquidity['recommendation'],
                'reasons': liquidity['reasons'],
                'tradingsymbol': oi_data['tradingsymbol'],
                'distance_from_atm': abs(strike - atm_strike)
            })
    
    # Sort by liquidity score (descending)
    strike_data.sort(key=lambda x: x['liquidity_score'], reverse=True)
    
    return strike_data

# =========================
# ENHANCED PATTERN ALERT
# =========================

def enhance_pattern_alert_with_oi(pattern_alert: str, 
                                   kite, ins_df, 
                                   index_name: str,
                                   atm_strike: int,
                                   option_type: str) -> str:
    """
    Enhance pattern alert with OI and liquidity data
    
    Args:
        pattern_alert: Original pattern alert message
        kite: KiteConnect instance
        ins_df: Instruments DataFrame
        index_name: Index name
        atm_strike: Recommended ATM strike
        option_type: 'CE' or 'PE'
    
    Returns:
        Enhanced alert with OI data
    """
    try:
        # Find best liquid strikes
        liquid_strikes = find_best_liquid_strikes(kite, ins_df, index_name, atm_strike, option_type, num_strikes=2)
        
        if not liquid_strikes:
            return pattern_alert + "\n\n⚠️ <i>OI data not available</i>"
        
        # Get the best strike
        best_strike = liquid_strikes[0]
        
        # Calculate entry/target/SL based on LTP
        ltp = best_strike['last_price']
        
        if ltp == 0:
            return pattern_alert + "\n\n⚠️ <i>Strike price not available</i>"
        
        entry_low = ltp * 0.98
        entry_high = ltp * 1.02
        target = ltp * 1.15
        stop_loss = ltp * 0.90
        
        # Build OI section
        oi_section = f"""

<b>💰 TRADE DETAILS (ENHANCED):</b>

<b>Recommended Strike:</b> {best_strike['strike']} {option_type}
<b>Current LTP:</b> ₹{ltp:.2f}
<b>Entry Range:</b> ₹{entry_low:.2f} - ₹{entry_high:.2f}
<b>Target:</b> ₹{target:.2f} (+15%)
<b>Stop Loss:</b> ₹{stop_loss:.2f} (-10%)

<b>📊 LIQUIDITY ANALYSIS:</b>
<b>Rating:</b> {best_strike['liquidity_rating']} ({best_strike['liquidity_score']}/100)
<b>Recommendation:</b> {best_strike['recommendation']}

<b>Open Interest:</b> {best_strike['oi']:,}
<b>Volume:</b> {best_strike['volume']:,}
<b>Bid-Ask Spread:</b> {best_strike['bid_ask_spread']:.2f}%

<b>Key Points:</b>
"""
        
        for reason in best_strike['reasons']:
            oi_section += f"• {reason}\n"
        
        # Add alternative strikes if available
        if len(liquid_strikes) > 1:
            oi_section += f"\n<b>Alternative Strikes:</b>\n"
            for alt_strike in liquid_strikes[1:3]:  # Show next 2 best
                oi_section += f"• {alt_strike['strike']} {option_type}: ₹{alt_strike['last_price']:.2f} ({alt_strike['liquidity_rating']})\n"
        
        # Insert OI section before the timestamp
        enhanced_alert = pattern_alert.replace(
            '⏰',
            oi_section + '\n⏰'
        )
        
        return enhanced_alert
    
    except Exception as e:
        print(f"Error enhancing alert with OI: {e}")
        return pattern_alert + f"\n\n⚠️ <i>Error fetching OI data: {str(e)}</i>"

# =========================
# LIQUIDITY FILTER
# =========================

def should_trade_strike(oi_data: Dict, index_name: str) -> Tuple[bool, str]:
    """
    Determine if a strike is liquid enough to trade
    
    Args:
        oi_data: OI data dictionary
        index_name: Index name
    
    Returns:
        (should_trade: bool, reason: str)
    """
    if not oi_data:
        return False, "No OI data available"
    
    liquidity = calculate_liquidity_score(oi_data, index_name)
    
    # Only trade if score >= 40 (MODERATE or better)
    if liquidity['score'] >= 60:
        return True, f"Good liquidity ({liquidity['rating']})"
    elif liquidity['score'] >= 40:
        return True, f"Acceptable liquidity ({liquidity['rating']}) - trade with caution"
    else:
        return False, f"Poor liquidity ({liquidity['rating']}) - avoid trading"

# =========================
# STATISTICS TRACKING
# =========================

class LiquidityTracker:
    """Track liquidity statistics over time"""
    
    def __init__(self):
        self.history = []
    
    def record_trade(self, index_name: str, strike: int, option_type: str, 
                    oi: int, volume: int, success: bool):
        """Record a trade outcome with liquidity metrics"""
        self.history.append({
            'timestamp': datetime.now(),
            'index_name': index_name,
            'strike': strike,
            'option_type': option_type,
            'oi': oi,
            'volume': volume,
            'success': success
        })
    
    def get_optimal_thresholds(self, index_name: str) -> Dict:
        """
        Analyze historical data to find optimal OI/volume thresholds
        
        Returns optimal thresholds based on success rates
        """
        if not self.history:
            return LIQUIDITY_THRESHOLDS.get(index_name, DEFAULT_STOCK_THRESHOLDS)
        
        # Filter for this index
        index_trades = [t for t in self.history if t['index_name'] == index_name]
        
        if len(index_trades) < 10:
            return LIQUIDITY_THRESHOLDS.get(index_name, DEFAULT_STOCK_THRESHOLDS)
        
        # Find OI/volume levels with highest success rates
        successful = [t for t in index_trades if t['success']]
        
        if not successful:
            return LIQUIDITY_THRESHOLDS.get(index_name, DEFAULT_STOCK_THRESHOLDS)
        
        # Calculate optimal thresholds (median of successful trades)
        oi_values = sorted([t['oi'] for t in successful])
        volume_values = sorted([t['volume'] for t in successful])
        
        optimal_oi = oi_values[len(oi_values) // 2]  # Median
        optimal_volume = volume_values[len(volume_values) // 2]
        
        return {
            'min_oi': optimal_oi,
            'min_volume': optimal_volume,
            'max_bid_ask_spread': 2.0  # Keep constant for now
        }
    
    def get_stats(self) -> Dict:
        """Get overall liquidity statistics"""
        if not self.history:
            return {'total_trades': 0}
        
        total = len(self.history)
        successful = sum(1 for t in self.history if t['success'])
        
        return {
            'total_trades': total,
            'successful': successful,
            'success_rate': (successful / total) * 100 if total > 0 else 0,
            'avg_oi': sum(t['oi'] for t in self.history) / total,
            'avg_volume': sum(t['volume'] for t in self.history) / total
        }
