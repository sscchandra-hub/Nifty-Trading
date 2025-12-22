# pattern_alerts.py - PATTERN ALERT GENERATION
# Generates formatted alerts for detected patterns

from datetime import datetime
from typing import Dict, Optional

def format_pattern_alert(analysis: Dict) -> str:
    """
    Generate formatted Telegram alert for detected pattern
    
    Args:
        analysis: Pattern analysis result from patterns.py
    
    Returns:
        Formatted HTML message for Telegram
    """
    if not analysis:
        return None
    
    pattern_name = analysis['pattern_name']
    pattern_direction = analysis['pattern_direction']
    current_state = analysis['current_state']
    outcomes = analysis['outcomes']
    confidence = analysis['confidence']
    
    # Format pattern name for display
    pattern_display = pattern_name.replace('_', ' → ').title()
    
    # Direction emoji
    direction_emoji = {
        'BULLISH': '🟢',
        'BEARISH': '🔴',
        'WARNING': '⚠️',
        'DEPENDS': '🟡'
    }.get(pattern_direction, '⚪')
    
    # Build recent examples list
    examples_text = ""
    for i, example in enumerate(outcomes['examples'][:5], 1):
        timestamp_str = example['timestamp'].strftime('%Y-%m-%d %H:%M')
        change = example['price_change']
        status_emoji = '✅' if example['success'] else '❌'
        examples_text += f"• {timestamp_str}: {change:+.1f}% {status_emoji}\n"
    
    # Calculate recommended strike and trade details
    index_name = current_state['index_name']
    spot_price = current_state['spot_price']
    
    # ATM strike calculation (simplified - will be enhanced with OI data)
    step_map = {"BANKNIFTY": 100, "NIFTY": 50, "FINNIFTY": 50, "MIDCPNIFTY": 25, "SENSEX": 100}
    step = step_map.get(index_name, 50)
    atm_strike = round(spot_price / step) * step
    
    # Option type based on direction
    if pattern_direction == 'BULLISH':
        option_type = 'CE'
        trade_action = 'BUY CALL'
    elif pattern_direction == 'BEARISH':
        option_type = 'PE'
        trade_action = 'BUY PUT'
    else:
        option_type = 'N/A'
        trade_action = 'WAIT'
    
    # Build alert message
    alert_msg = f"""<b>🔍 PATTERN MATCH - {index_name}</b>

<b>Pattern:</b> {pattern_display}
<b>Trigger:</b> CE Δ{current_state.get('ce_delta', 0):+,.0f}, PE Δ{current_state.get('pe_delta', 0):+,.0f}

📊 <b>Historical Analysis:</b>
{direction_emoji} <b>{outcomes['total_matches']} similar patterns found</b>
✅ <b>Success Rate: {outcomes['success_rate']:.0%}</b> ({outcomes['successful']}/{outcomes['total_matches']})
📈 <b>Average Move: {outcomes['avg_gain']:+.1f}%</b>
⏱️ <b>Average Time: {outcomes['avg_time']:.0f} minutes</b>

<b>Recent Matches:</b>
{examples_text}
📈 <b>RECOMMENDATION:</b>
<b>Action:</b> {trade_action}
<b>Strike:</b> {atm_strike} {option_type} (ATM)
<b>Spot Price:</b> {spot_price:.2f}

<b>Pattern Confidence:</b> {confidence}
<b>Risk Level:</b> {'Low-Medium' if confidence == 'HIGH' else 'Medium'}
<b>Expected Win Rate:</b> {outcomes['success_rate']:.0%}

<i>⚠️ Note: Historical patterns don't guarantee future results. Always manage risk properly.</i>

⏰ {datetime.now().strftime('%I:%M:%S %p')}
"""
    
    return alert_msg

def format_pattern_alert_with_oi(analysis: Dict, option_ltp: float, oi_data: Dict) -> str:
    """
    Generate enhanced alert with OI and liquidity data
    
    Args:
        analysis: Pattern analysis result
        option_ltp: Current LTP of recommended strike
        oi_data: Open Interest and liquidity data
    
    Returns:
        Enhanced formatted alert
    """
    if not analysis:
        return None
    
    # Get base alert
    base_alert = format_pattern_alert(analysis)
    
    if not base_alert or not option_ltp:
        return base_alert
    
    # Calculate entry/target/SL
    entry_low = option_ltp * 0.98
    entry_high = option_ltp * 1.02
    target = option_ltp * 1.15
    stop_loss = option_ltp * 0.90
    
    # Build OI section
    oi_section = f"""
<b>Current LTP:</b> ₹{option_ltp:.2f}
<b>Entry Range:</b> ₹{entry_low:.2f} - ₹{entry_high:.2f}
<b>Target:</b> ₹{target:.2f} (+15%)
<b>Stop Loss:</b> ₹{stop_loss:.2f} (-10%)
"""
    
    if oi_data:
        oi_volume = oi_data.get('oi', 0)
        volume = oi_data.get('volume', 0)
        bid_ask_spread = oi_data.get('bid_ask_spread', 0)
        
        # Liquidity rating
        if oi_volume > 100000 and volume > 10000:
            liquidity_rating = "✅ Excellent"
        elif oi_volume > 50000 and volume > 5000:
            liquidity_rating = "✅ Good"
        elif oi_volume > 20000 and volume > 2000:
            liquidity_rating = "⚠️ Moderate"
        else:
            liquidity_rating = "❌ Low - Avoid"
        
        oi_section += f"""
<b>Liquidity Analysis:</b>
OI: {oi_volume:,} {liquidity_rating}
Volume: {volume:,}
Bid-Ask: {bid_ask_spread:.2f}%
"""
    
    # Insert OI section before "Pattern Confidence"
    enhanced_alert = base_alert.replace(
        '<b>Pattern Confidence:</b>',
        oi_section + '\n<b>Pattern Confidence:</b>'
    )
    
    return enhanced_alert

def should_generate_alert(analysis: Dict, index_name: str, last_pattern_time: Dict) -> bool:
    """
    Check if we should generate an alert (avoid spam)
    
    Args:
        analysis: Pattern analysis
        index_name: Index name
        last_pattern_time: Dict tracking last alert time for each pattern
    
    Returns:
        True if should alert, False if too soon
    """
    if not analysis:
        return False
    
    pattern_name = analysis['pattern_name']
    key = f"{index_name}_{pattern_name}"
    
    # Check if we alerted for this pattern recently (within 5 minutes)
    if key in last_pattern_time:
        time_since = (datetime.now() - last_pattern_time[key]).total_seconds()
        if time_since < 300:  # 5 minutes
            return False
    
    # Update last alert time
    last_pattern_time[key] = datetime.now()
    return True
