# pattern_integration.py - PATTERN MATCHING INTEGRATION
# Add-on module to integrate pattern matching with main app

import sys
from pathlib import Path
from datetime import datetime

# Add paths
sys.path.insert(0, '/mnt/user-data/outputs')

try:
    from patterns import analyze_pattern, get_market_state, get_available_data_days
    from pattern_alerts import format_pattern_alert, should_generate_alert
    from oi_liquidity import enhance_pattern_alert_with_oi, get_option_oi_data, should_trade_strike
    import pandas as pd
    PATTERNS_LOADED = True
    print("✅ Pattern matching + OI modules loaded successfully")
except Exception as e:
    PATTERNS_LOADED = False
    print(f"⚠️ Pattern matching not available: {e}")

def run_pattern_detection(flow_history, indices_data, deltas, indices_with_fo, 
                         last_pattern_alert, add_alert_func, kite=None, ins_df=None):
    """
    Run pattern detection on current market data with OI enhancement
    
    Args:
        flow_history: Deque of historical flow data
        indices_data: Current indices data dict
        deltas: Current delta calculations
        indices_with_fo: List of indices to check
        last_pattern_alert: Dict tracking last alerts (will be modified)
        add_alert_func: Function to call for adding alerts
        kite: KiteConnect instance (optional - for OI data)
        ins_df: Instruments DataFrame (optional - for OI data)
    
    Returns:
        Number of patterns detected
    """
    if not PATTERNS_LOADED:
        return 0
    
    if len(flow_history) < 6:
        return 0  # Need at least 6 polls (1 minute of data)
    
    patterns_found = 0
    
    try:
        for idx_name in indices_with_fo:
            if idx_name not in indices_data:
                continue
            
            # Check if we have enough historical data
            try:
                days_available = get_available_data_days(idx_name)
            except:
                days_available = 0
            
            if days_available < 1:
                continue  # Need at least 1 day of CSV data
            
            # Get recent data for market state  
            recent_snapshots = list(flow_history)[-6:]  # Last 6 polls
            recent_df_data = []
            
            for snap in recent_snapshots:
                idx_data = snap.get('indices_data', {}).get(idx_name, {})
                if idx_data:
                    try:
                        recent_df_data.append({
                            'timestamp': datetime.fromisoformat(snap['timestamp']),
                            'index_name': idx_name,
                            'spot_price': idx_data.get('price', 0),
                            'price_change_pct': idx_data.get('change_pct', 0),
                            'ce_flow': idx_data.get('ce_flow', 0),
                            'pe_flow': idx_data.get('pe_flow', 0),
                            'delta_1min_ce': deltas.get(f'{idx_name}_ce_1min', 0) if deltas else 0,
                            'delta_1min_pe': deltas.get(f'{idx_name}_pe_1min', 0) if deltas else 0,
                            'sentiment': 'UNKNOWN',
                            'range_status': idx_data.get('range_status', 'UNKNOWN')
                        })
                    except Exception as e:
                        print(f"Error building recent data: {e}")
                        continue
            
            if len(recent_df_data) < 2:
                continue
            
            try:
                recent_df = pd.DataFrame(recent_df_data)
                current_row = recent_df.iloc[-1]
                
                # Get market state
                state = get_market_state(recent_df, current_row)
                
                if not state:
                    continue
                
                # Analyze for patterns
                analysis = analyze_pattern(idx_name, state, days_back=min(days_available, 7))
                
                if analysis and should_generate_alert(analysis, idx_name, last_pattern_alert):
                    # Generate base alert
                    alert_msg = format_pattern_alert(analysis)
                    
                    if not alert_msg:
                        continue
                    
                    # Enhance with OI data if available
                    if kite and ins_df is not None:
                        try:
                            # Determine option type from pattern direction
                            pattern_direction = analysis.get('pattern_direction', 'UNKNOWN')
                            
                            if pattern_direction == 'BULLISH':
                                option_type = 'CE'
                            elif pattern_direction == 'BEARISH':
                                option_type = 'PE'
                            else:
                                option_type = 'CE'  # Default
                            
                            # Calculate ATM strike
                            spot_price = state.get('spot_price', 0)
                            step_map = {"BANKNIFTY": 100, "NIFTY": 50, "FINNIFTY": 50, "MIDCPNIFTY": 25, "SENSEX": 100}
                            step = step_map.get(idx_name, 50)
                            atm_strike = round(spot_price / step) * step
                            
                            # Enhance alert with OI
                            alert_msg = enhance_pattern_alert_with_oi(
                                alert_msg, kite, ins_df, idx_name, atm_strike, option_type
                            )
                            
                            # Check if strike is liquid enough
                            oi_data = get_option_oi_data(kite, ins_df, idx_name, atm_strike, option_type)
                            if oi_data:
                                should_trade, reason = should_trade_strike(oi_data, idx_name)
                                if not should_trade:
                                    alert_msg += f"\n\n⚠️ <b>LIQUIDITY WARNING:</b> {reason}"
                        
                        except Exception as e:
                            print(f"Error enhancing with OI: {e}")
                            # Continue with base alert
                    
                    # Send alert
                    add_alert_func(alert_msg, "warning")
                    print(f"🔍 PATTERN: {analysis['pattern_name']} detected for {idx_name}")
                    print(f"   Success rate: {analysis['outcomes']['success_rate']:.0%}")
                    print(f"   Confidence: {analysis['confidence']}")
                    patterns_found += 1
            
            except Exception as e:
                print(f"Error analyzing {idx_name}: {e}")
                continue
    
    except Exception as e:
        print(f"Pattern detection error: {e}")
        import traceback
        traceback.print_exc()
    
    return patterns_found

def get_pattern_status():
    """Check if pattern matching is available"""
    if not PATTERNS_LOADED:
        return "❌ Not Available - Modules not loaded"
    
    # Check if we have any historical data
    from pathlib import Path
    hist_dir = Path("data/historical/indices")
    
    if not hist_dir.exists():
        return "⚠️ Waiting for Data - No CSV files yet"
    
    # Count days with data
    dates_with_data = 0
    for date_folder in hist_dir.iterdir():
        if date_folder.is_dir():
            csv_files = list(date_folder.glob("*.csv"))
            if csv_files:
                dates_with_data += 1
    
    if dates_with_data == 0:
        return "⏳ Collecting Data - 0 days"
    elif dates_with_data < 5:
        return f"📊 Collecting Data - {dates_with_data} day(s) (need 5-7 for accuracy)"
    else:
        return f"✅ Ready - {dates_with_data} days of data available"
