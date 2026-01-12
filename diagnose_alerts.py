"""
Diagnostic script to understand why PE alerts are not triggering
"""
import sys
from datetime import datetime
from kiteconnect import KiteConnect
import json

# Load credentials
with open('credentials.json', 'r') as f:
    creds = json.load(f)

kite = KiteConnect(api_key=creds['api_key'])
kite.set_access_token(creds['access_token'])

print("=" * 80)
print(f"🔍 ALERT DIAGNOSTIC REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)

# Check if we're in market hours
now = datetime.now()
current_time = now.time()
from datetime import time as dt_time
market_start = dt_time(9, 15)
market_end = dt_time(15, 30)
is_market_hours = market_start <= current_time <= market_end

print(f"\n📅 Current Time: {now.strftime('%H:%M:%S')}")
print(f"⏰ Market Hours (09:15-15:30): {'YES ✅' if is_market_hours else 'NO ❌'}")

# Get NIFTY 50 performance
print("\n" + "=" * 80)
print("📊 NIFTY 50 PERFORMANCE")
print("=" * 80)

try:
    nifty_data = kite.quote(["NSE:NIFTY 50"])
    nifty_info = nifty_data.get("NSE:NIFTY 50", {})
    nifty_price = nifty_info.get("last_price", 0)
    nifty_change = nifty_info.get("change", 0)
    nifty_change_pct = (nifty_change / (nifty_price - nifty_change)) * 100 if nifty_price > 0 else 0

    print(f"Price: ₹{nifty_price:,.2f}")
    print(f"Change: {nifty_change_pct:+.2f}%")

    if nifty_change_pct < -0.10:
        print("Market Status: 🔴 BEARISH (good for PE alerts)")
    elif nifty_change_pct > 0.10:
        print("Market Status: 🟢 BULLISH (bad for PE alerts)")
    else:
        print("Market Status: ⚪ FLAT")

except Exception as e:
    print(f"❌ Error fetching NIFTY data: {e}")

# Get sector breadth
print("\n" + "=" * 80)
print("🏢 SECTOR BREADTH ANALYSIS")
print("=" * 80)

sector_indices = [
    "NIFTY BANK", "NIFTY IT", "NIFTY AUTO", "NIFTY PHARMA",
    "NIFTY METAL", "NIFTY FMCG", "NIFTY ENERGY", "NIFTY FIN SERVICE",
    "NIFTY REALTY", "NIFTY MEDIA", "NIFTY HEALTHCARE",
    "NIFTY CONSUMER DURABLES", "NIFTY OIL AND GAS", "NIFTY PSU BANK"
]

positive_sectors = []
negative_sectors = []
flat_sectors = []

try:
    # Fetch all sector indices
    instruments_str = [f"NSE:{idx}" for idx in sector_indices]
    sector_data = kite.quote(instruments_str)

    for idx_name in sector_indices:
        key = f"NSE:{idx_name}"
        if key in sector_data:
            data = sector_data[key]
            price = data.get("last_price", 0)
            change = data.get("change", 0)
            change_pct = (change / (price - change)) * 100 if price > 0 else 0

            if change_pct > 0:
                positive_sectors.append((idx_name, change_pct))
            elif change_pct < 0:
                negative_sectors.append((idx_name, change_pct))
            else:
                flat_sectors.append((idx_name, 0))

    print(f"\n🟢 Positive Sectors: {len(positive_sectors)}/{len(sector_indices)}")
    for sector, pct in positive_sectors:
        print(f"   {sector}: +{pct:.2f}%")

    print(f"\n🔴 Negative Sectors: {len(negative_sectors)}/{len(sector_indices)}")
    for sector, pct in negative_sectors:
        print(f"   {sector}: {pct:.2f}%")

    if flat_sectors:
        print(f"\n⚪ Flat Sectors: {len(flat_sectors)}")
        for sector, _ in flat_sectors:
            print(f"   {sector}")

    # Check PE alert requirement
    print("\n" + "-" * 80)
    if len(negative_sectors) >= 6:
        print(f"✅ PE ALERT SECTOR REQUIREMENT MET: {len(negative_sectors)}/14 sectors negative (≥6 needed)")
    else:
        print(f"❌ PE ALERT SECTOR REQUIREMENT NOT MET: {len(negative_sectors)}/14 sectors negative (need ≥6)")
        print(f"   Need {6 - len(negative_sectors)} more negative sectors for PE alerts")

except Exception as e:
    print(f"❌ Error fetching sector data: {e}")

# Check top stocks for potential PE alert conditions
print("\n" + "=" * 80)
print("📈 TOP STOCKS PE ALERT CONDITIONS")
print("=" * 80)

# Common liquid stocks to check
check_stocks = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "BAJFINANCE", "LT", "ASIANPAINT", "AXISBANK", "MARUTI"
]

print("\nChecking for stocks meeting PE alert conditions:")
print("Required: Price < -1.5%, Net Flow < 0, CE/PE < 1.0, 6+ sectors negative")
print("-" * 80)

try:
    # Get stock quotes
    stock_instruments = [f"NSE:{stock}" for stock in check_stocks]
    stock_quotes = kite.quote(stock_instruments)

    pe_candidates = []

    for stock in check_stocks:
        key = f"NSE:{stock}"
        if key in stock_quotes:
            data = stock_quotes[key]
            price = data.get("last_price", 0)
            change = data.get("change", 0)
            change_pct = (change / (price - change)) * 100 if price > 0 else 0

            # Check if price condition met
            if change_pct < -1.5:
                pe_candidates.append((stock, price, change_pct))
                print(f"🔴 {stock}: ₹{price:,.2f} ({change_pct:+.2f}%) - Price condition MET")
            elif change_pct < -1.0:
                print(f"⚠️ {stock}: ₹{price:,.2f} ({change_pct:+.2f}%) - Close but not -1.5%")

    if not pe_candidates:
        print("\n❌ NO stocks found with price < -1.5%")
    else:
        print(f"\n✅ Found {len(pe_candidates)} stocks with price < -1.5%")
        print("   (Still need to check Net Flow, CE/PE ratio for full PE alert)")

except Exception as e:
    print(f"❌ Error checking stocks: {e}")

# Summary
print("\n" + "=" * 80)
print("📋 SUMMARY - Why No PE Alerts?")
print("=" * 80)

print("\nPE Alert Requirements (ALL 4 must be TRUE):")
print("1. ❓ Price < -1.5%")
print("2. ❓ Net Flow < 0")
print("3. ❓ CE/PE Ratio < 1.0 (PE volume > CE volume)")
print(f"4. {'✅' if len(negative_sectors) >= 6 else '❌'} Sector Breadth: {len(negative_sectors)}/14 negative (need ≥6)")

print("\n💡 Most Likely Reasons:")
if not is_market_hours:
    print("⚠️  Outside market hours - alerts only sent 09:15-15:30")
if len(negative_sectors) < 6:
    print(f"⚠️  Insufficient sector weakness - only {len(negative_sectors)}/14 sectors negative")
    print("   Even in bearish market, need BROAD sector selloff for PE alerts")
if nifty_change_pct > -0.5:
    print("⚠️  Market not strongly bearish - NIFTY needs broad selloff")
if len(pe_candidates) == 0:
    print("⚠️  No individual stocks down > -1.5%")

print("\n📝 Next Steps:")
print("1. Wait for broader market selloff (6+ sectors negative)")
print("2. Look for individual stock weakness (-1.5%+) with PUT option buying")
print("3. Ensure app.py is running and monitoring in real-time")
print("4. Check alert_history.csv after market hours for any missed alerts")

print("\n" + "=" * 80)
