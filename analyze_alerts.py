#!/usr/bin/env python3
"""Simple CSV analyzer without pandas dependency"""

from collections import defaultdict, Counter
from datetime import datetime

def parse_date(date_str):
    """Parse date string to datetime object"""
    try:
        return datetime.strptime(date_str, '%d-%m-%Y')
    except:
        return None

# Read CSV file
alerts = []
with open('/home/user/Nifty-Trading/alert_history.csv', 'r') as f:
    lines = f.readlines()
    header = lines[0].strip().split(',')

    for line in lines[1:]:
        parts = line.strip().split(',')
        if len(parts) >= 6:
            alerts.append({
                'date': parts[0],
                'time': parts[1],
                'stock': parts[2],
                'alert_type': parts[3],
                'score': parts[4],
                'alert_price': parts[5]
            })

print(f"Total alerts: {len(alerts)}\n")

# 1. Stock frequency count
stock_counts = Counter([a['stock'] for a in alerts])
print("="*60)
print("TOP 20 MOST FREQUENTLY ALERTED STOCKS")
print("="*60)
for i, (stock, count) in enumerate(stock_counts.most_common(20), 1):
    print(f"{i:2}. {stock:15} → {count:3} alerts")

# 2. Date-wise breakdown
date_counts = Counter([a['date'] for a in alerts])
print("\n" + "="*60)
print("ALERTS BY DATE")
print("="*60)
for date in sorted(date_counts.keys()):
    print(f"{date}: {date_counts[date]} alerts")

# 3. Stocks alerted on multiple different days
stock_dates = defaultdict(set)
for alert in alerts:
    stock_dates[alert['stock']].add(alert['date'])

multi_day_stocks = {stock: dates for stock, dates in stock_dates.items() if len(dates) > 1}
print("\n" + "="*60)
print("STOCKS ALERTED ON MULTIPLE DAYS")
print("="*60)
sorted_multi = sorted(multi_day_stocks.items(), key=lambda x: len(x[1]), reverse=True)
for stock, dates in sorted_multi[:15]:
    sorted_dates = sorted(dates)
    print(f"{stock:15} → {len(dates)} days: {', '.join(sorted_dates)}")

# 4. Stocks with consecutive day alerts
print("\n" + "="*60)
print("CONSECUTIVE DAY PATTERNS")
print("="*60)
for stock, dates in sorted_multi[:15]:
    date_objs = sorted([parse_date(d) for d in dates if parse_date(d)])
    if len(date_objs) >= 2:
        for i in range(len(date_objs) - 1):
            gap = (date_objs[i+1] - date_objs[i]).days
            if gap == 1:
                print(f"{stock:15} → Consecutive: {date_objs[i].strftime('%d-%m-%Y')} to {date_objs[i+1].strftime('%d-%m-%Y')}")

# 5. Stocks that would trigger recurring alert (multiple alerts in 7-day window)
print("\n" + "="*60)
print("RECURRING ALERT TRIGGERS (Multiple alerts in 7-day window)")
print("="*60)
stock_alert_dates = defaultdict(list)
for alert in alerts:
    stock_alert_dates[alert['stock']].append(parse_date(alert['date']))

recurring_stocks = []
for stock, dates in stock_alert_dates.items():
    sorted_dates = sorted([d for d in dates if d])
    unique_dates = sorted(set(sorted_dates))

    # Check for alerts within 7 days
    for i in range(len(unique_dates) - 1):
        for j in range(i+1, len(unique_dates)):
            gap = (unique_dates[j] - unique_dates[i]).days
            if gap <= 7:
                recurring_stocks.append({
                    'stock': stock,
                    'days_apart': gap,
                    'date1': unique_dates[i].strftime('%d-%m-%Y'),
                    'date2': unique_dates[j].strftime('%d-%m-%Y'),
                    'total_days': len(unique_dates)
                })
                break

# Remove duplicates and sort
seen = set()
unique_recurring = []
for item in recurring_stocks:
    key = item['stock']
    if key not in seen:
        seen.add(key)
        unique_recurring.append(item)

unique_recurring.sort(key=lambda x: x['total_days'], reverse=True)

for item in unique_recurring[:20]:
    print(f"{item['stock']:15} → {item['total_days']} different days, gap: {item['days_apart']} days ({item['date1']} to {item['date2']})")

print("\n" + "="*60)
print(f"SUMMARY: {len(unique_recurring)} stocks would trigger recurring alerts")
print("="*60)
