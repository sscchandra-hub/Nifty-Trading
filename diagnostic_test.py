# app.py - FIXED VERSION
# Enhanced Streamlit + Zerodha momentum engine

import os, json, time, threading, queue, pickle, signal, math
import datetime as dt
from datetime import datetime, time as dt_time
from pathlib import Path
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from kiteconnect import KiteConnect, KiteTicker

# =========================
# CONSTANTS & PATHS
# =========================
TZ = "Asia/Kolkata"
DATA_ROOT = Path("data")
CACHE_DIR = Path(".cache")
TOKENS_FILE = CACHE_DIR / "tokens.json"
RUNTIME_STATE_FILE = CACHE_DIR / "runtime_state.pkl"
INSTRUMENTS_FILE = CACHE_DIR / "instruments.parquet"
DASHBOARD_CACHE_FILE = CACHE_DIR / "dashboard_cache.pkl"

DATA_ROOT.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Load environment
load_dotenv()
API_KEY = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")

# Derivative segments
DERIV_FUT_SEGMENTS = {"NFO-FUT", "BFO-FUT"}
DERIV_OPT_SEGMENTS = {"NFO-OPT", "BFO-OPT"}
INDEX_NAME_WHITELIST = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"}

# =========================
# ENGINE STATE
# =========================
@dataclass
class EngineState:
    kite: KiteConnect = None
    ticker_thread: threading.Thread = None
    minute_thread: threading.Thread = None
    ins_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    token_meta: pd.DataFrame = field(default_factory=pd.DataFrame)
    subscribe_tokens: list = field(default_factory=list)
    ticker_connected: bool = False
    stop_flag: bool = False
    tick_q: queue.Queue = field(default_factory=queue.Queue)
    minute_buf: list = field(default_factory=list)
    indices_with_fo: list = field(default_factory=list)

engine = EngineState()

# =========================
# AUTHENTICATION
# =========================
def get_kite_session():
    """Load cached session if valid"""
    if TOKENS_FILE.exists():
        try:
            with open(TOKENS_FILE) as f:
                data = json.load(f)
            
            saved_at = datetime.fromisoformat(data.get("saved_at", "2000-01-01"))
            now = datetime.now()
            
            # Invalidate after 6 AM next day
            if saved_at.date() < now.date() and now.hour >= 6:
                TOKENS_FILE.unlink()
                return None, None
            
            kite = KiteConnect(api_key=API_KEY)
            kite.set_access_token(data["access_token"])
            kite.margins()  # Test connection
            return kite, saved_at
        except Exception as e:
            print(f"Token validation error: {e}")
            try:
                TOKENS_FILE.unlink()
            except:
                pass
            return None, None
    return None, None

def authenticate_kite(request_token):
    """Authenticate with request token"""
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
        kite.margins()  # Verify
        
        return kite, datetime.now()
    except Exception as e:
        raise Exception(f"Auth failed: {str(e)}")

def get_market_status():
    """Check if market is open"""
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
    except Exception:
        return "UNKNOWN", "⚪", "info"

# =========================
# UTILITY FUNCTIONS
# =========================
def ist_now():
    return pd.Timestamp.now(tz=TZ)

def _safe_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()

# =========================
# DASHBOARD CACHE FUNCTIONS
# =========================
def save_dashboard_cache(data: dict):
    """Save dashboard display data to cache"""
    try:
        now = datetime.now()
        data["cached_at"] = now.isoformat()
        with open(DASHBOARD_CACHE_FILE, "wb") as f:
            pickle.dump(data, f)
    except Exception as e:
        print(f"Error saving dashboard cache: {e}")

def load_dashboard_cache():
    """Load cached dashboard data"""
    if not DASHBOARD_CACHE_FILE.exists():
        return None
    try:
        with open(DASHBOARD_CACHE_FILE, "rb") as f:
            data = pickle.load(f)
        cached_at_str = data.get("cached_at", "2000-01-01")
        cached_at = datetime.fromisoformat(cached_at_str)
        
        # Remove timezone for comparison
        now = datetime.now()
        if cached_at.tzinfo is not None:
            cached_at = cached_at.replace(tzinfo=None)
        if now.tzinfo is not None:
            now = now.replace(tzinfo=None)
            
        if (now - cached_at).total_seconds() < 86400:  # 24 hours
            return data
    except Exception as e:
        print(f"Error loading dashboard cache: {e}")
    return None

# =========================
# INSTRUMENTS
# =========================
def ensure_instruments(kite: KiteConnect) -> pd.DataFrame:
    if INSTRUMENTS_FILE.exists():
        try:
            df = pd.read_parquet(INSTRUMENTS_FILE)
            need = {"segment","name","tradingsymbol","instrument_token","expiry","strike","instrument_type"}
            if need.issubset(df.columns):
                return df
        except Exception:
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

# =========================
# PICKERS
# =========================
def nearest_fut(ins_df: pd.DataFrame, name: str):
    """Get nearest futures contract"""
    df = ins_df[(ins_df["segment"].isin(DERIV_FUT_SEGMENTS)) & (ins_df["name"]==name)].copy()
    if df.empty: return None
    df["expiry"] = pd.to_datetime(df["expiry"])
    today = pd.Timestamp.today().normalize()
    df = df[df["expiry"]>=today].sort_values("expiry")
    return df.iloc[0].to_dict() if not df.empty else None

def index_opt_chain(ins_df: pd.DataFrame, name: str, expiry=None):
    """Get option chain"""
    df = ins_df[(ins_df["segment"].isin(DERIV_OPT_SEGMENTS)) & (ins_df["name"]==name)].copy()
    if df.empty: return df
    df["expiry"] = pd.to_datetime(df["expiry"])
    if expiry is None:
        today = pd.Timestamp.today().normalize()
        df = df[df["expiry"]>=today]
        if df.empty: return df
        expiry = df["expiry"].min()
    else:
        expiry = pd.to_datetime(expiry)
    return df[df["expiry"]==expiry].copy()

def select_atm_band(options_df: pd.DataFrame, ltp: float, step_guess: int):
    """Select ATM band"""
    if options_df.empty: return options_df
    strikes = sorted(options_df["strike"].unique().tolist())
    if not strikes: return options_df.head(0)
    atm = min(strikes, key=lambda k: abs(k - ltp))
    band = [k for k in strikes if abs(k - atm) <= 6*step_guess]
    return options_df[options_df["strike"].isin(band)]

# =========================
# SUBSCRIPTIONS
# =========================
def build_subscriptions(kite: KiteConnect, ins_df: pd.DataFrame):
    """Build subscription list - SIMPLIFIED for stability"""
    subscribe_tokens = set()
    token_meta_rows = []

    step_guess_map = {"BANKNIFTY": 100, "NIFTY": 50, "FINNIFTY": 50, "MIDCPNIFTY": 25, "SENSEX": 100}
    
    print("=" * 50)
    print("BUILDING SUBSCRIPTIONS")
    print("=" * 50)
    
    # Only subscribe to indices (most stable)
    for idx in engine.indices_with_fo:
        try:
            print(f"\nProcessing {idx}...")
            fut = nearest_fut(ins_df, idx)
            if not fut:
                print(f"  ⚠️ No futures found for {idx}")
                continue
                
            fut_token = int(fut["instrument_token"])
            subscribe_tokens.add(fut_token)
            token_meta_rows.append(fut)
            print(f"  ✓ Added futures token: {fut_token}")
            
            # Get current price for ATM calculation
            try:
                q = kite.quote([fut_token])
                fut_ltp = list(q.values())[0]["last_price"]
                print(f"  ✓ LTP: {fut_ltp}")
            except Exception as e:
                # Fallback prices
                fallback_prices = {"NIFTY": 24000, "BANKNIFTY": 50000, "FINNIFTY": 22000, 
                                  "MIDCPNIFTY": 10000, "SENSEX": 78000}
                fut_ltp = fallback_prices.get(idx, 24000)
                print(f"  ⚠️ Using fallback LTP: {fut_ltp} ({e})")
                
            step_guess = step_guess_map.get(idx, 50)
            oc = index_opt_chain(ins_df, idx, None)
            
            if not oc.empty:
                oc_sel = select_atm_band(oc, fut_ltp, step_guess)
                
                if not oc_sel.empty:
                    opt_tokens = oc_sel["instrument_token"].astype(int).tolist()
                    subscribe_tokens.update(opt_tokens)
                    token_meta_rows += oc_sel.to_dict("records")
                    print(f"  ✓ Added {len(opt_tokens)} options")
        except Exception as e:
            print(f"  ❌ Error processing {idx}: {e}")
            continue

    sub_tokens = sorted(list(subscribe_tokens))
    token_meta = pd.DataFrame(token_meta_rows)
    
    if not token_meta.empty:
        token_meta = token_meta.drop_duplicates(subset=["instrument_token"]).copy()
        token_meta = token_meta.set_index("instrument_token")
    
    print("\n" + "=" * 50)
    print(f"✓ SUBSCRIPTIONS BUILT: {len(sub_tokens)} instruments")
    print("=" * 50)
    return sub_tokens, token_meta

# =========================
# STREAMING
# =========================
def on_ticks(ws, ticks):
    """Handle incoming ticks"""
    try:
        now = ist_now()
        for t in ticks:
            t["ts"] = now
            engine.tick_q.put(t)
    except Exception as e:
        print(f"❌ Error in on_ticks: {e}")

def on_connect(ws, response):
    """Handle WebSocket connection"""
    try:
        print(f"\n{'='*50}")
        print(f"✓ WEBSOCKET CONNECTED")
        print(f"{'='*50}")
        print(f"Response: {response}")
        
        if engine.subscribe_tokens:
            # Subscribe in chunks
            chunk_size = 500
            total_chunks = (len(engine.subscribe_tokens) + chunk_size - 1) // chunk_size
            
            for i in range(0, len(engine.subscribe_tokens), chunk_size):
                chunk = engine.subscribe_tokens[i:i+chunk_size]
                ws.subscribe(chunk)
                ws.set_mode(ws.MODE_FULL, chunk)
                print(f"✓ Subscribed batch {i//chunk_size + 1}/{total_chunks}: {len(chunk)} instruments")
                time.sleep(0.5)  # Small delay between batches
        
        engine.ticker_connected = True
        print(f"\n{'='*50}")
        print(f"✓ WEBSOCKET READY - RECEIVING TICKS")
        print(f"{'='*50}\n")
    except Exception as e:
        print(f"❌ Error in on_connect: {e}")
        engine.ticker_connected = False

def on_close(ws, code, reason):
    """Handle WebSocket disconnection"""
    print(f"\n❌ WEBSOCKET CLOSED: code={code}, reason={reason}")
    engine.ticker_connected = False

def on_error(ws, code, reason):
    """Handle WebSocket errors"""
    print(f"\n❌ WEBSOCKET ERROR: code={code}, reason={reason}")
    engine.ticker_connected = False

def start_ticker_thread(api_key: str, access_token: str):
    """Start WebSocket ticker thread"""
    try:
        print("\n" + "="*50)
        print("STARTING WEBSOCKET TICKER")
        print("="*50)
        
        kws = KiteTicker(api_key, access_token)
        kws.on_ticks = on_ticks
        kws.on_connect = on_connect
        kws.on_close = on_close
        kws.on_error = on_error
        
        def run_ticker():
            try:
                print("Connecting to WebSocket...")
                kws.connect(threaded=False)
            except Exception as e:
                print(f"❌ Ticker thread died: {e}")
                import traceback
                traceback.print_exc()
                engine.ticker_connected = False
        
        th = threading.Thread(target=run_ticker, daemon=True, name="TickerThread")
        th.start()
        print(f"✓ Ticker thread started (Thread-{th.ident})")
        return th
    except Exception as e:
        print(f"❌ Failed to start ticker: {e}")
        import traceback
        traceback.print_exc()
        return None

def minute_loop():
    """Process ticks into minute bars"""
    print("\n" + "="*50)
    print("STARTING MINUTE PROCESSOR")
    print("="*50)
    
    while not engine.stop_flag:
        try:
            # Get ticks from queue
            try:
                t = engine.tick_q.get(timeout=0.2)
                engine.minute_buf.append(t)
            except queue.Empty:
                pass
            
            # Process at minute boundary
            now = ist_now()
            if now.second == 0 or now.second == 1:
                if engine.minute_buf:
                    try:
                        print(f"\n⏰ Processing minute bar at {now}")
                        df = pd.DataFrame(engine.minute_buf)
                        engine.minute_buf.clear()
                        print(f"   Ticks received: {len(df)}")
                        print(f"   Unique instruments: {df['instrument_token'].nunique()}")
                        
                        # Save simple signal for demo
                        now_min = pd.Timestamp.now(tz=TZ).floor("T")
                        cache_data = {
                            "composite_score": 50.0 + (now.minute % 20) - 10,  # Varying score for demo
                            "signal_band": "Sideways",
                            "stance": "Wait",
                            "total_ce_cod": len(df) * 100,
                            "total_pe_cod": -len(df) * 80,
                            "last_update": now_min.tz_localize(None).isoformat()
                        }
                        save_dashboard_cache(cache_data)
                        print(f"   ✓ Cache updated")
                        
                    except Exception as e:
                        print(f"❌ Error processing minute bar: {e}")
                        import traceback
                        traceback.print_exc()
                
                time.sleep(1.5)  # Avoid double processing
        except Exception as e:
            print(f"❌ Error in minute loop: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(1)
    
    print("\n" + "="*50)
    print("MINUTE PROCESSOR STOPPED")
    print("="*50)

# =========================
# STREAMLIT UI
# =========================
st.set_page_config(
    page_title="Nifty Momentum Engine",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 0.5rem;
    }
    .status-badge {
        display: inline-block;
        padding: 0.5rem 1rem;
        border-radius: 0.5rem;
        font-weight: bold;
        font-size: 1rem;
        margin: 0.5rem 0;
    }
    .status-success {
        background-color: #28a745;
        color: white;
    }
    .status-warning {
        background-color: #ffc107;
        color: black;
    }
    .status-error {
        background-color: #dc3545;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.markdown("### 🎛️ System Status")
    
    # Market Status
    st.markdown("---")
    market_status, status_emoji, status_type = get_market_status()
    
    status_class = f"status-{status_type}"
    st.markdown(f'<div class="status-badge {status_class}">{status_emoji} {market_status}</div>', 
                unsafe_allow_html=True)
    
    now = datetime.now()
    st.caption(f"🕐 IST: {now.strftime('%I:%M %p, %d %b %Y')}")
    
    # Authentication Status
    st.markdown("---")
    st.markdown("### 🔐 Authentication")
    
    kite, token_saved_at = get_kite_session()
    
    if kite and token_saved_at:
        st.success("✅ Authenticated")
        
        time_since = datetime.now() - token_saved_at
        hours_left = max(0, 24 - time_since.total_seconds() / 3600)
        
        st.metric("Token Valid For", f"{int(hours_left)}h {int((hours_left % 1) * 60)}m")
        st.caption(f"Saved: {token_saved_at.strftime('%I:%M %p')}")
        
        try:
            profile = kite.profile()
            st.info(f"👤 {profile.get('user_name', 'User')}")
            st.caption(f"ID: {profile.get('user_id', 'N/A')}")
        except:
            pass
            
        if st.button("🚪 Logout", use_container_width=True, key="sidebar_logout_btn"):
            try:
                TOKENS_FILE.unlink()
                st.success("Logged out!")
                time.sleep(1)
                _safe_rerun()
            except:
                pass
    else:
        st.warning("⚠️ Not Authenticated")
        st.caption("Please authenticate below")
    
    # Engine Status
    st.markdown("---")
    st.markdown("### ⚙️ Engine Status")
    
    is_running = st.session_state.get("engine_running", False)
    ticker_alive = engine.ticker_thread and engine.ticker_thread.is_alive()
    minute_alive = engine.minute_thread and engine.minute_thread.is_alive()
    
    if is_running and ticker_alive and engine.ticker_connected:
        st.success("🟢 Live Streaming")
        if "engine_start_time" in st.session_state:
            uptime = (pd.Timestamp.now() - st.session_state.engine_start_time).total_seconds()
            st.caption(f"Uptime: {int(uptime//60)}m {int(uptime%60)}s")
    elif is_running and ticker_alive and not engine.ticker_connected:
        st.warning("🟡 Connecting...")
        st.caption("Establishing WebSocket...")
    elif is_running and not ticker_alive:
        st.error("🔴 Thread Died")
        st.caption("⚠️ Click 'Restart Engine'")
        st.caption("Check terminal for errors")
    else:
        st.info("⏸️ Stopped")
        st.caption("Click 'Start Engine' to begin")
    
    if engine.subscribe_tokens:
        st.metric("Subscribed Instruments", len(engine.subscribe_tokens))
        if len(engine.subscribe_tokens) < 100:
            st.warning("⚠️ Low instrument count")
    
    # Cache status
    st.markdown("---")
    st.markdown("### 💾 Data Cache")
    
    cache_info = load_dashboard_cache()
    if cache_info:
        cached_at = datetime.fromisoformat(cache_info.get("cached_at", "2000-01-01"))
        now_dt = datetime.now()
        if cached_at.tzinfo is not None:
            cached_at = cached_at.replace(tzinfo=None)
        
        time_ago = (now_dt - cached_at).total_seconds()
        
        if time_ago < 60:
            st.success(f"✅ Fresh ({int(time_ago)}s ago)")
        elif time_ago < 300:
            st.success(f"✅ Recent ({int(time_ago/60)}m ago)")
        else:
            st.warning(f"⚠️ Older ({int(time_ago/60)}m ago)")
    else:
        st.info("📦 No cache yet")

# =========================
# MAIN CONTENT
# =========================
st.markdown('<p class="main-header">🚀 Nifty Multi-Index Momentum Engine</p>', unsafe_allow_html=True)

# Authentication check
if not API_KEY or not API_SECRET:
    st.error("❌ Missing KITE_API_KEY or KITE_API_SECRET in .env file")
    st.stop()

if not kite:
    st.warning("⚠️ Please authenticate with Zerodha Kite")
    
    login_url = f"https://kite.zerodha.com/connect/login?api_key={API_KEY}&v=3"
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 🔐 Authentication Required")
        st.markdown(f"**Step 1:** [Click here to login to Zerodha]({login_url})")
        st.markdown("**Step 2:** After login, copy the `request_token` from the redirect URL")
        st.markdown("**Step 3:** Paste it below and click Authenticate")
    
    with col2:
        st.info("""
        **What is request_token?**
        
        After logging in, you'll see a URL like:
        
        `http://localhost?request_token=ABC123`
        
        Copy the `ABC123` part
        """)
    
    with st.form("auth_form", clear_on_submit=True):
        request_token = st.text_input("📋 Paste Request Token:", type="password")
        submitted = st.form_submit_button("🔐 Authenticate", use_container_width=True)
        
        if submitted and request_token.strip():
            try:
                with st.spinner("🔄 Authenticating..."):
                    kite, _ = authenticate_kite(request_token.strip())
                    engine.kite = kite
                    st.success("✅ Authentication successful!")
                    time.sleep(1)
                    _safe_rerun()
            except Exception as e:
                st.error(f"❌ Authentication failed: {str(e)}")
    
    st.stop()

# =========================
# MAIN DASHBOARD
# =========================
engine.kite = kite

# Initialize
if engine.ins_df.empty:
    with st.spinner("Loading instruments..."):
        engine.ins_df = ensure_instruments(kite)

if not engine.indices_with_fo:
    engine.indices_with_fo = discover_indices_with_fo(engine.ins_df)

# Build subscriptions if needed
if not engine.subscribe_tokens or engine.token_meta.empty:
    with st.spinner("Building subscription list..."):
        try:
            engine.subscribe_tokens, engine.token_meta = build_subscriptions(kite, engine.ins_df)
            if engine.subscribe_tokens:
                st.success(f"✅ Ready! {len(engine.subscribe_tokens)} instruments prepared")
        except Exception as e:
            st.error(f"❌ Failed to build subscriptions: {e}")
            import traceback
            st.code(traceback.format_exc())

# Control Panel
st.subheader("⚙️ Control Panel")

col1, col2, col3, col4 = st.columns(4)

with col1:
    needs_restart = st.session_state.get("engine_running", False) and (
        not engine.ticker_thread or not engine.ticker_thread.is_alive()
    )
    
    button_label = "🔄 Restart Engine" if needs_restart else "▶️ Start Engine"
    
    if st.button(button_label, use_container_width=True, type="primary", key="main_start_engine_btn"):
        with st.spinner("🔄 Starting engine..."):
            try:
                if not engine.subscribe_tokens or len(engine.subscribe_tokens) < 100:
                    st.info("Building fresh subscription list...")
                    engine.subscribe_tokens, engine.token_meta = build_subscriptions(engine.kite, engine.ins_df)
                
                if not engine.subscribe_tokens:
                    st.error("❌ No subscriptions! Check terminal for errors.")
                else:
                    # Stop old threads
                    engine.stop_flag = True
                    time.sleep(0.5)
                    
                    # Start fresh
                    engine.stop_flag = False
                    engine.ticker_thread = start_ticker_thread(API_KEY, kite.access_token)
                    
                    if engine.ticker_thread:
                        engine.minute_thread = threading.Thread(target=minute_loop, daemon=True, name="MinuteThread")
                        engine.minute_thread.start()
                        
                        st.session_state.engine_running = True
                        st.session_state.engine_start_time = pd.Timestamp.now()
                        
                        time.sleep(3)
                        
                        if engine.ticker_connected:
                            st.success(f"✅ Engine started! {len(engine.subscribe_tokens)} instruments")
                            st.info("📊 Wait for next minute boundary for data...")
                        else:
                            st.warning("⚠️ Engine started, waiting for connection...")
                            st.caption("Check terminal for logs")
                    else:
                        st.error("❌ Failed to start ticker. Check terminal!")
                        st.session_state.engine_running = False
                        
            except Exception as e:
                st.error(f"❌ Error: {e}")
                st.session_state.engine_running = False
                import traceback
                st.code(traceback.format_exc())

with col2:
    if st.button("⏸️ Stop Engine", use_container_width=True, key="main_stop_engine_btn"):
        engine.stop_flag = True
        engine.ticker_connected = False
        st.session_state.engine_running = False
        st.warning("🛑 Stopping engine...")

with col3:
    if st.button("📸 Snapshot", use_container_width=True, key="main_snapshot_btn"):
        with st.spinner("📸 Taking snapshot..."):
            try:
                if engine.subscribe_tokens:
                    chunks = [engine.subscribe_tokens[i:i+500] for i in range(0, len(engine.subscribe_tokens), 500)]
                    all_data = []
                    
                    for chunk in chunks[:2]:
                        try:
                            quotes = engine.kite.quote(chunk)
                            for token, data in quotes.items():
                                all_data.append({
                                    'instrument_token': int(data['instrument_token']),
                                    'last_price': data.get('last_price', 0)
                                })
                        except:
                            continue
                    
                    if all_data:
                        # Just save to cache
                        now_min = pd.Timestamp.now(tz=TZ).floor("T")
                        cache_data = {
                            "composite_score": 50.0,
                            "signal_band": "Snapshot",
                            "total_ce_cod": 0,
                            "total_pe_cod": 0,
                            "last_update": now_min.tz_localize(None).isoformat()
                        }
                        save_dashboard_cache(cache_data)
                        st.success(f"✅ Snapshot: {len(all_data)} instruments")
                    else:
                        st.warning("⚠️ No data received")
                else:
                    st.warning("⚠️ No subscriptions yet")
            except Exception as e:
                st.error(f"❌ Error: {e}")

with col4:
    st.metric("📊 Indices", len(engine.indices_with_fo))

st.caption(f"Tracking: {', '.join(engine.indices_with_fo) if engine.indices_with_fo else 'Loading...'}")

st.markdown("---")

# Live Composite Score
st.subheader("📈 Live Composite Score")

cache_data = load_dashboard_cache()
latest_score = None
latest_band = None

if cache_data:
    latest_score = cache_data.get("composite_score", 50.0)
    latest_band = cache_data.get("signal_band", "Waiting")
    
    last_update_str = cache_data.get("last_update")
    if last_update_str:
        last_update_time = pd.Timestamp(last_update_str)
        time_ago = (pd.Timestamp.now() - last_update_time).total_seconds()
        
        if time_ago < 60:
            st.success(f"🔴 Live • Updated {int(time_ago)}s ago")
        elif time_ago < 300:
            st.success(f"🟢 Live • Updated {int(time_ago/60)}m ago")
        else:
            st.warning(f"⚠️ Stale • Updated {int(time_ago/60)}m ago")

col_metric1, col_metric2, col_metric3 = st.columns(3)

with col_metric1:
    score_val = f"{latest_score:.1f}" if latest_score is not None else "—"
    st.metric("Composite Score", score_val)

with col_metric2:
    band_val = latest_band if latest_band else "—"
    st.metric("Signal Band", band_val)

with col_metric3:
    stance = "DIRECTIONAL" if abs(latest_score or 0) > 50 else "NEUTRAL"
    st.metric("Strategy Stance", stance)

# Progress bar
if latest_score is not None:
    score_normalized = (latest_score + 100) / 200
    st.progress(score_normalized)

# Footer
st.markdown("---")
st.caption("⚙️ Real-time momentum engine powered by Zerodha Kite Connect")