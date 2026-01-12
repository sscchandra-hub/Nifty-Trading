# 🏗️ System Architecture

> **Detailed technical documentation for the NIFTY Options Flow Trading System**

This document provides a comprehensive overview of the system architecture, data flows, key components, and implementation details.

---

## 📋 Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Core Components](#core-components)
3. [Data Flow](#data-flow)
4. [Alert System Architecture](#alert-system-architecture)
5. [Threading Model](#threading-model)
6. [State Management](#state-management)
7. [API Integration](#api-integration)
8. [Function Reference](#function-reference)
9. [Database Schema (CSV Files)](#database-schema-csv-files)
10. [Performance Optimization](#performance-optimization)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACE LAYER                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │              STREAMLIT DASHBOARD (app.py:11000+)                 │  │
│  │  • Live Charts (Plotly/Altair)                                   │  │
│  │  • Momentum Score Display                                        │  │
│  │  • Volume Heatmaps                                               │  │
│  │  • Manual Control Buttons                                        │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                         DATA POLLING LAYER                              │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │        BACKGROUND POLLING THREAD (app.py:8000-9000)              │  │
│  │  • Runs every 15 seconds (market hours only)                     │  │
│  │  • Thread-safe with threading.Lock()                             │  │
│  │  • Singleton pattern (prevents multiple instances)               │  │
│  │  • Updates session_state for UI rendering                        │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                         API INTEGRATION LAYER                           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────┐   │
│  │  KITE CONNECT   │  │  OPTIONS DATA   │  │   SECTORAL INDICES   │   │
│  │  (Zerodha)      │  │  (CE/PE Flows)  │  │   (14 indices)       │   │
│  │  app.py:230+    │  │  app.py:5500+   │  │   app.py:5600+       │   │
│  └─────────────────┘  └─────────────────┘  └──────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                       DATA PROCESSING LAYER                             │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │             CE/PE FLOW ANALYSIS (app.py:5500-6500)               │  │
│  │  • Calculate net flow (CE - PE)                                  │  │
│  │  • Calculate CE/PE ratio (CE / PE)                               │  │
│  │  • Detect volume spikes (> 2x average)                           │  │
│  │  • Track momentum changes (1min, 5min deltas)                    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │          SECTOR BREADTH ANALYSIS (app.py:7500-7700)              │  │
│  │  • Count positive/negative sectoral indices                      │  │
│  │  • Calculate sector momentum scores                              │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │        NIFTY MOMENTUM SCORE (app.py:1992-2235)                   │  │
│  │  • 8-parameter scoring (-85 to +85 range)                        │  │
│  │  • Real-time score breakdown display                             │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                       ALERT EVALUATION LAYER                            │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │          STOCK ALERT CHECKER (app.py:8720-8781)                  │  │
│  │  • Checks ALL stocks (no Top 10 restriction)                     │  │
│  │  • BULLISH: Price > +1%, CE/PE > 2, Net > 0, ≥6 sectors +ve     │  │
│  │  • BEARISH: Price < -1%, CE/PE < 1, Net < 0, ≥6 sectors -ve     │  │
│  │  • Cooldown: 5 minutes per stock                                 │  │
│  │  • Momentum filter: ensures stronger signals for repeats         │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │            SL ALERT MONITOR (app.py:8736-8781)                   │  │
│  │  • Tracks alerted stocks for reversals                           │  │
│  │  • BULLISH SL: CE/PE < 1.0 (full reversal)                       │  │
│  │  • BEARISH SL: CE/PE > 2.0 (full reversal)                       │  │
│  │  • Sent once per stock per alert                                 │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │         NIFTY ALERT CHECKER (app.py:8200-8450)                   │  │
│  │  • 7 alert types (Strong/Regular/Divergence/Reversal)            │  │
│  │  • 3-minute confirmation for standard alerts                     │  │
│  │  • Instant alerts for divergence/reversals                       │  │
│  │  • Cooldown: 30 minutes                                          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                      NOTIFICATION DELIVERY LAYER                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │            TELEGRAM INTEGRATION (app.py:3000-3100)               │  │
│  │  • Formatted HTML messages with emojis                           │  │
│  │  • Strike price recommendations                                  │  │
│  │  • Timestamp & hashtags                                          │  │
│  │  • Retry logic with exponential backoff                          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────┐
│                       DATA PERSISTENCE LAYER                            │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │              CSV EXPORT (app.py:5724-5800)                       │  │
│  │  • Daily stock flow tracking                                     │  │
│  │  • NIFTY CE/PE flow history                                      │  │
│  │  • Strike-wise OI data                                           │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Engine State Management (app.py:900-950)

```python
@dataclass
class EngineState:
    """
    Central state management for the trading engine
    """
    # Alert cooldown tracking
    last_alerts: dict = field(default_factory=dict)
    # {stock_name: {'alert_type': str, 'time': datetime, 'change_pct': float, 'net_flow': float}}

    # SL tracking for alerted stocks
    alerted_stocks: dict = field(default_factory=dict)
    # {stock_name: {'alert_type': str, 'initial_ce_pe': float, 'sl_sent': bool}}

    # NIFTY alert tracking
    nifty_last_alert_time: datetime = None
    nifty_alert_confirmation: dict = field(default_factory=dict)
    # {'alert_type': str, 'start_time': datetime, 'score': int}

    # Performance metrics
    alert_count: int = 0
    polling_count: int = 0
```

**Location**: `app.py:900-950`

**Purpose**: Thread-safe state management for alerts, cooldowns, and tracking.

---

### 2. Market Hours Check (app.py:2990-2996)

```python
def is_market_hours() -> bool:
    """
    Check if current time is within market hours (09:16 AM - 3:30 PM)

    Returns:
        bool: True if within market hours, False otherwise
    """
    now = datetime.now()
    market_open = now.replace(hour=9, minute=16, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close
```

**Location**: `app.py:2990-2996`

**Key Changes**:
- Alert start time changed from 9:15 AM to **9:16 AM** (user request on 2026-01-12)

---

### 3. Sector Breadth Analysis (app.py:7500-7700)

```python
def calculate_sector_breadth(indices_data):
    """
    Calculate market breadth from 14 sectoral indices

    Args:
        indices_data: Dictionary of index data

    Returns:
        {
            'positive_count': int,     # Number of positive indices
            'negative_count': int,     # Number of negative indices
            'neutral_count': int,      # Number of neutral indices
            'positive_indices': list,  # Names of positive indices
            'negative_indices': list,  # Names of negative indices
            'breadth_score': float     # (+ve count - -ve count) / total
        }
    """
```

**Location**: `app.py:7500-7700`

**Tracked Indices** (14 total):
- NIFTY BANK, NIFTY IT, NIFTY AUTO, NIFTY PHARMA
- NIFTY FMCG, NIFTY METAL, NIFTY REALTY, NIFTY ENERGY
- NIFTY PSU BANK, NIFTY MEDIA, NIFTY PVT BANK, NIFTY FIN SERVICE
- NIFTY COMMODITIES, NIFTY CONSUMPTION

---

### 4. NIFTY Momentum Score Calculator (app.py:1992-2235)

```python
def calculate_nifty_momentum_score(indices_data, stocks_data, volume_state, vwap_st_strategy):
    """
    Calculate comprehensive NIFTY momentum score from 8 parameters

    NOTE: VWAP/SuperTrend scoring has been DISABLED (was ±15 points)
    New score range: -85 to +85 (instead of -100 to +100)

    Returns:
        {
            'total_score': int (-85 to +85),
            'breakdown': {
                'ce_pe_flow': int,          # ±10 points
                'session_spikes': int,       # ±15 points
                'ce_pe_race': int,           # ±10 points
                'live_momentum': int,        # ±10 points
                'nifty_net_flow': int,       # ±10 points
                'indices_net_flow': int,     # ±10 points
                'indices_performance': int,  # ±10 points
                'vwap_supertrend': 0,        # DISABLED (was ±15)
                'stock_performance': int     # ±10 points
            },
            'signal': 'BULLISH' | 'BEARISH' | 'NEUTRAL'
        }
    """
```

**Location**: `app.py:1992-2235`

**Key Change**: VWAP/SuperTrend removed on 2026-01-12 (user request)

**Scoring Breakdown**:

| Parameter | Bullish Score | Bearish Score | Threshold |
|-----------|---------------|---------------|-----------|
| CE/PE Flow | +10 | -10 | > 1.5 or < 0.67 |
| Session Spikes | +15 | -15 | CE spike > 1.5x avg or PE spike > 1.5x avg |
| CE vs PE Race | +10 | -10 | CE lead > 15% or PE lead > 15% |
| Live Momentum | +10 | -10 | Sentiment > 65% or < 35% |
| NIFTY Net Flow | +10 | -10 | > 50M or < -50M |
| Indices Net Flow | +10 | -10 | > 100M or < -100M |
| Indices Performance | +10 | -10 | > 65% up or > 65% down |
| Stock Performance | +10 | -10 | > 60% up or > 60% down |

**Total Range**: -85 to +85 points

---

## Data Flow

### Stock Alert Flow

```
[KITE API]
    ↓ (fetch quotes every 15s)
[stocks_data dict]
    ↓
[FOR EACH STOCK]:
    ├─ Extract: ce_flow, pe_flow, price, change_pct
    ├─ Calculate: net_flow = ce_flow - pe_flow
    ├─ Calculate: ce_pe_ratio = ce_flow / pe_flow
    ├─ Get: sector_breadth (positive_count, negative_count)
    ↓
[CHECK BULLISH CONDITIONS]:
    ├─ change_pct > 1.0 ✓
    ├─ net_flow > 0 ✓
    ├─ ce_pe_ratio > 2.0 ✓
    ├─ sector_breadth['positive_count'] >= 6 ✓
    ├─ Check cooldown (5 minutes) ✓
    ├─ Check momentum (if repeat alert) ✓
    ↓
[CHECK BEARISH CONDITIONS]:
    ├─ change_pct < -1.0 ✓
    ├─ net_flow < 0 ✓
    ├─ ce_pe_ratio < 1.0 ✓
    ├─ sector_breadth['negative_count'] >= 6 ✓
    ├─ Check cooldown (5 minutes) ✓
    ├─ Check momentum (if repeat alert) ✓
    ↓
[IF CONDITIONS MET]:
    ├─ send_stock_alert() → Telegram
    ├─ Track in engine.alerted_stocks (for SL monitoring)
    ├─ Update engine.last_alerts (for cooldown)
    └─ Log to CSV file
```

### SL Alert Flow

```
[engine.alerted_stocks] (populated when initial alert sent)
    ↓
[FOR EACH ALERTED STOCK]:
    ├─ Check if SL already sent ✓
    ├─ Fetch current CE/PE ratio
    ↓
[CHECK BULLISH SL]:
    ├─ Original alert was BULLISH
    ├─ current_ce_pe < 1.0 (full reversal)
    ↓
[CHECK BEARISH SL]:
    ├─ Original alert was BEARISH
    ├─ current_ce_pe > 2.0 (full reversal)
    ↓
[IF SL TRIGGERED]:
    ├─ send_sl_alert() → Telegram
    ├─ Mark sl_sent = True (prevent duplicate)
    └─ Do NOT check price (CE/PE change alone)
```

### NIFTY Alert Flow

```
[calculate_nifty_momentum_score()]
    ↓
[score = -85 to +85]
    ↓
[CHECK ALERT CONDITIONS]:
    ├─ STRONG BULLISH: score >= +70
    ├─ BULLISH: score >= +55
    ├─ STRONG BEARISH: score <= -70
    ├─ BEARISH: score <= -55
    ├─ BULLISH DIVERGENCE: price down + score > +40
    ├─ BEARISH DIVERGENCE: price up + score < -40
    ├─ REVERSAL WARNING: abs(score) >= 35
    ↓
[3-MINUTE CONFIRMATION] (for standard alerts only):
    ├─ First reading: Start timer
    ├─ Subsequent readings: Check if 3 minutes elapsed
    ├─ Score must stay in range for full 3 minutes
    ↓
[CHECK COOLDOWN]:
    ├─ NIFTY alerts: 30 minutes
    ├─ Skip if last alert < 30 minutes ago
    ↓
[IF CONDITIONS MET]:
    ├─ send_nifty_alert() → Telegram
    ├─ Update nifty_last_alert_time
    └─ Reset confirmation timer
```

---

## Alert System Architecture

### Stock Alert System

**Location**: `app.py:8720-8781`

**Key Functions**:
- `send_stock_alert()` - `app.py:3450-3514`
- `send_sl_alert()` - `app.py:3515-3569`

**Alert Conditions**:

#### BULLISH Alert
```python
if (change_pct > 1.0 and
    net_flow > 0 and
    ce_pe_ratio > 2.0 and
    sector_breadth['positive_count'] >= 6):

    # Check cooldown
    if last_alert_time and (now - last_alert_time) < timedelta(minutes=5):
        continue

    # Check momentum filter (for repeat alerts)
    if last_alert_data:
        if (change_pct <= last_alert_data['change_pct'] or
            net_flow <= last_alert_data['net_flow']):
            continue  # Skip weak repeat alerts

    send_stock_alert(stock_name, "BULLISH", ...)
```

#### BEARISH Alert
```python
elif (change_pct < -1.0 and
      net_flow < 0 and
      ce_pe_ratio < 1.0 and
      sector_breadth['negative_count'] >= 6):

    # Check cooldown
    if last_alert_time and (now - last_alert_time) < timedelta(minutes=5):
        continue

    # Check momentum filter (for repeat alerts)
    if last_alert_data:
        if (abs(change_pct) <= abs(last_alert_data['change_pct']) or
            abs(net_flow) <= abs(last_alert_data['net_flow'])):
            continue  # Skip weak repeat alerts

    send_stock_alert(stock_name, "BEARISH", ...)
```

#### Stop Loss (SL) Alert
```python
# Check previously alerted stocks
for stock_name, alert_data in engine.alerted_stocks.items():
    if alert_data.get('sl_sent', False):
        continue  # Skip if SL already sent

    current_ce_pe = ce_flow / pe_flow

    # BULLISH SL: CE/PE drops below 1.0
    if alert_data['alert_type'] == "BULLISH" and current_ce_pe < 1.0:
        send_sl_alert(stock_name, "BULLISH", ...)
        alert_data['sl_sent'] = True

    # BEARISH SL: CE/PE rises above 2.0
    elif alert_data['alert_type'] == "BEARISH" and current_ce_pe > 2.0:
        send_sl_alert(stock_name, "BEARISH", ...)
        alert_data['sl_sent'] = True
```

---

### NIFTY Alert System

**Location**: `app.py:8200-8450`

**Key Functions**:
- `calculate_nifty_momentum_score()` - `app.py:1992-2235`
- `send_nifty_alert()` - `app.py:3600-3900`

**7 Alert Types**:

1. **STRONG BULLISH** (Score: +70 to +85)
   - 3-minute confirmation required
   - 30-minute cooldown

2. **BULLISH** (Score: +55 to +69)
   - 3-minute confirmation required
   - 30-minute cooldown

3. **STRONG BEARISH** (Score: -70 to -85)
   - 3-minute confirmation required
   - 30-minute cooldown

4. **BEARISH** (Score: -55 to -69)
   - 3-minute confirmation required
   - 30-minute cooldown

5. **BULLISH DIVERGENCE** (Price down + Score > +40)
   - Instant alert (no confirmation)
   - Options flow contradicts price movement

6. **BEARISH DIVERGENCE** (Price up + Score < -40)
   - Instant alert (no confirmation)
   - Options flow contradicts price movement

7. **REVERSAL WARNING** (Score: ±35 to ±54)
   - Instant alert (no confirmation)
   - Momentum building but not extreme yet

**Implementation**:

```python
momentum_data = calculate_nifty_momentum_score(...)
score = momentum_data['total_score']

# Determine alert type
if score >= 70:
    alert_type = "STRONG_BULLISH"
    needs_confirmation = True
elif score >= 55:
    alert_type = "BULLISH"
    needs_confirmation = True
# ... (similar for bearish)

# 3-minute confirmation logic
if needs_confirmation:
    if not engine.nifty_alert_confirmation:
        # First reading - start timer
        engine.nifty_alert_confirmation = {
            'alert_type': alert_type,
            'start_time': now,
            'score': score
        }
        return  # Wait for confirmation
    else:
        # Check if 3 minutes elapsed
        elapsed = (now - engine.nifty_alert_confirmation['start_time']).total_seconds()
        if elapsed < 180:  # 3 minutes = 180 seconds
            return  # Still confirming

        # Confirmation complete - send alert
        send_nifty_alert(alert_type, score, ...)
        engine.nifty_alert_confirmation = None
else:
    # Instant alerts (divergence, reversal)
    send_nifty_alert(alert_type, score, ...)
```

---

## Threading Model

### Singleton Polling Thread

**Location**: `app.py:8000-9000`

**Purpose**: Fetch data from Kite API every 15 seconds without blocking Streamlit UI.

**Implementation**:

```python
# Global flag to prevent multiple threads
POLLING_THREAD_ACTIVE = False
THREAD_LOCK = threading.Lock()

def start_polling_thread():
    """
    Start background polling thread (singleton pattern)
    """
    global POLLING_THREAD_ACTIVE

    with THREAD_LOCK:
        if POLLING_THREAD_ACTIVE:
            return  # Thread already running

        POLLING_THREAD_ACTIVE = True
        thread = threading.Thread(target=polling_loop, daemon=True)
        thread.start()

def polling_loop():
    """
    Main polling loop - runs independently from Streamlit
    """
    while True:
        if not is_market_hours():
            time.sleep(60)  # Check every minute outside market hours
            continue

        try:
            # Fetch data from Kite API
            indices_data = fetch_indices_data()
            stocks_data = fetch_stocks_data()

            # Update session state (thread-safe)
            st.session_state['indices_data'] = indices_data
            st.session_state['stocks_data'] = stocks_data
            st.session_state['last_update'] = datetime.now()

            # Check alerts
            check_stock_alerts(stocks_data)
            check_nifty_alerts(indices_data, stocks_data)

        except Exception as e:
            logger.error(f"Polling error: {e}")

        time.sleep(15)  # Poll every 15 seconds
```

**Key Features**:
- **Daemon thread**: Exits when main program exits
- **Singleton pattern**: Only one polling thread runs at a time
- **Thread-safe**: Uses `threading.Lock()` for state updates
- **Error handling**: Catches exceptions, continues polling
- **Market hours aware**: Reduces polling frequency outside market hours

---

## State Management

### Session State (Streamlit)

**Location**: Throughout `app.py`

**Key State Variables**:

```python
# Data storage
st.session_state['indices_data'] = {}       # Sectoral indices data
st.session_state['stocks_data'] = {}        # Individual stock data
st.session_state['futures_data'] = {}       # NIFTY futures data

# Volume analysis
st.session_state['volume_state'] = VolumeState()  # Volume spike tracking

# VWAP/SuperTrend
st.session_state['vwap_st_strategy'] = {}   # VWAP & SuperTrend signals

# Timestamp
st.session_state['last_update'] = None      # Last data fetch time

# Engine state
st.session_state['engine'] = EngineState()  # Alert tracking & cooldowns

# Cached data
st.session_state['cached_data'] = {}        # API response cache
```

**Thread Safety**:
- Session state is automatically thread-safe in Streamlit
- Polling thread writes to session state
- UI reads from session state (no race conditions)

---

## API Integration

### Kite Connect API

**Location**: `app.py:230-500`

**Key Functions**:

1. **Authentication**
   ```python
   kite = KiteConnect(api_key=KITE_API_KEY)
   kite.set_access_token(KITE_ACCESS_TOKEN)
   ```

2. **Fetch Quotes**
   ```python
   def fetch_quotes(instruments):
       """
       Fetch quotes for multiple instruments (batch request)

       Args:
           instruments: List of instrument tokens

       Returns:
           dict: {token: quote_data}
       """
       try:
           quotes = kite.quote(instruments)
           return quotes
       except Exception as e:
           logger.error(f"Quote fetch error: {e}")
           return {}
   ```

3. **Fetch Historical Data** (15-min candles for NIFTY futures)
   ```python
   def fetch_historical_candles(instrument, from_date, to_date, interval="15minute"):
       """
       Fetch historical candle data

       Returns:
           list: [{'date': datetime, 'open': float, 'high': float,
                   'low': float, 'close': float, 'volume': int}, ...]
       """
       try:
           candles = kite.historical_data(
               instrument_token=instrument,
               from_date=from_date,
               to_date=to_date,
               interval=interval
           )
           return candles
       except Exception as e:
           logger.error(f"Historical data error: {e}")
           return []
   ```

**Rate Limits**:
- 3 requests/second
- 1000 requests/day
- System uses batch requests to minimize API calls

**Error Handling**:
- Exponential backoff on rate limit errors
- Retry logic with 3 attempts
- Graceful degradation (use cached data if API fails)

---

### Telegram API

**Location**: `app.py:3000-3100`

**Key Functions**:

```python
def send_telegram_message(message, parse_mode='HTML'):
    """
    Send formatted message to Telegram

    Args:
        message: HTML-formatted message string
        parse_mode: 'HTML' or 'Markdown'

    Returns:
        bool: True if sent successfully, False otherwise
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': parse_mode
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        else:
            logger.error(f"Telegram send failed: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False
```

**Message Format**:
- HTML formatting with `<b>`, `<i>`, `<code>` tags
- Emojis for visual indicators
- Hashtags for searchability
- Timestamp for tracking

---

## Function Reference

### Core Alert Functions

| Function | Location | Purpose |
|----------|----------|---------|
| `is_market_hours()` | app.py:2990-2996 | Check if within trading hours |
| `calculate_sector_breadth()` | app.py:7500-7700 | Count positive/negative sectors |
| `calculate_nifty_momentum_score()` | app.py:1992-2235 | Calculate 8-parameter NIFTY score |
| `send_stock_alert()` | app.py:3450-3514 | Send BULLISH/BEARISH stock alerts |
| `send_sl_alert()` | app.py:3515-3569 | Send Stop Loss reversal alerts |
| `send_nifty_alert()` | app.py:3600-3900 | Send NIFTY momentum alerts |
| `check_stock_alerts()` | app.py:8720-8781 | Check all stocks for alert conditions |
| `check_nifty_alerts()` | app.py:8200-8450 | Check NIFTY score for alerts |

### Data Fetching Functions

| Function | Location | Purpose |
|----------|----------|---------|
| `fetch_indices_data()` | app.py:5600-5700 | Fetch 14 sectoral indices |
| `fetch_stocks_data()` | app.py:5500-5600 | Fetch 50+ stock quotes with CE/PE flows |
| `fetch_futures_data()` | app.py:8534-8616 | Fetch NIFTY futures 15-min candles |
| `calculate_vwap()` | app.py:1275-1350 | Calculate VWAP from candles |
| `calculate_supertrend()` | app.py:1350-1450 | Calculate SuperTrend indicator |

### Visualization Functions

| Function | Location | Purpose |
|----------|----------|---------|
| `create_volume_heatmap()` | app.py:382-414 | Volume spike heatmap chart |
| `create_ce_pe_race_chart()` | app.py:416-470 | CE vs PE flow race chart |
| `create_volume_timeline()` | app.py:472-550 | Volume spike timeline |
| `create_intensity_wave()` | app.py:552-650 | Volume intensity wave chart |

---

## Database Schema (CSV Files)

### stock_flow_tracking_YYYY-MM-DD.csv

**Location**: `CSV_files/`

**Columns**:
- `timestamp`: ISO 8601 datetime
- `stock_name`: Stock symbol (e.g., "RELIANCE", "TCS")
- `price`: Current price (float)
- `change_pct`: Percentage change (float)
- `ce_flow`: Call option flow (float)
- `pe_flow`: Put option flow (float)
- `net_flow`: CE - PE (float)
- `ce_pe_ratio`: CE / PE (float)
- `alerted`: True/False (bool)
- `alert_type`: "BULLISH" / "BEARISH" / "" (string)

**Purpose**: Track all stock flows for backtesting and analysis.

---

### nifty_ce_pe_flow_YYYY-MM-DD.csv

**Location**: `CSV_files/`

**Columns**:
- `timestamp`: ISO 8601 datetime
- `nifty_spot`: NIFTY spot price (float)
- `nifty_change_pct`: Percentage change (float)
- `ce_total_flow`: Total CE flow across all strikes (float)
- `pe_total_flow`: Total PE flow across all strikes (float)
- `net_flow`: CE - PE (float)
- `momentum_score`: 8-parameter score -85 to +85 (int)
- `signal`: "BULLISH" / "BEARISH" / "NEUTRAL" (string)

**Purpose**: Historical NIFTY momentum tracking for pattern analysis.

---

## Performance Optimization

### 1. Batch API Requests
- Fetch quotes for 50+ stocks in single API call
- Reduces API calls by 70%

### 2. Response Caching
- Cache API responses for 15 seconds
- Reduces redundant fetches during Streamlit reruns

### 3. Efficient Data Structures
- Use dictionaries for O(1) lookups
- Pre-compute CE/PE ratios and net flows

### 4. Lazy Loading
- Only fetch futures data when NIFTY section is expanded
- Reduces initial load time

### 5. Thread-Safe State Updates
- Use `threading.Lock()` for critical sections
- Prevents race conditions without blocking UI

---

## Monitoring & Debugging

### Log Files

1. **chart_debug.log** (app.py:42-60)
   - Chart rendering errors
   - Plotly/Altair issues
   - Data transformation problems

2. **app.log** (if configured)
   - General application logs
   - API errors
   - Alert delivery status

### Debug Mode

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## Security Considerations

1. **API Credentials**
   - Store in `.env` file (NEVER commit to git)
   - Use environment variables

2. **Telegram Bot Security**
   - Validate chat ID
   - Use HTTPS for webhook (if applicable)

3. **Rate Limiting**
   - Implement exponential backoff
   - Track API call counts

4. **Error Handling**
   - Never expose API keys in error messages
   - Log sensitive data securely

---

## Deployment Architecture

### Production Setup

```
┌─────────────────────────────────────────┐
│         VPS / Cloud Server              │
│  (Linux, 2GB RAM, 2 CPU cores)          │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │   Streamlit App (app.py)          │ │
│  │   Port: 8501                      │ │
│  └───────────────────────────────────┘ │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │   Nginx Reverse Proxy             │ │
│  │   Port: 80/443 (HTTPS)            │ │
│  └───────────────────────────────────┘ │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │   Systemd Service                 │ │
│  │   Auto-restart on failure         │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

See [PRODUCTION_SETUP.md](PRODUCTION_SETUP.md) for detailed deployment guide.

---

## Future Enhancements

1. **Machine Learning Integration**
   - LSTM models for price prediction
   - Sentiment analysis from news/Twitter

2. **Multi-Broker Support**
   - Upstox, Angel One, Fyers integration
   - Unified data interface

3. **Advanced Backtesting**
   - Strategy simulator
   - Performance metrics (Sharpe ratio, max drawdown)

4. **Mobile App**
   - React Native / Flutter
   - Push notifications

5. **Database Migration**
   - Move from CSV to PostgreSQL/MongoDB
   - Real-time querying capabilities

---

**For more details, see**:
- [README.md](README.md) - Project overview
- [CONTRIBUTIONS.md](CONTRIBUTIONS.md) - Development guidelines
- [ALERT_SYSTEM_VERIFICATION.md](ALERT_SYSTEM_VERIFICATION.md) - Testing procedures
- [NIFTY_ALERT_CONDITIONS.md](NIFTY_ALERT_CONDITIONS.md) - Alert logic deep dive
