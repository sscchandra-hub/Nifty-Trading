# Migration Guide: Using New Improved Structure

This guide shows you how to gradually adopt the new code structure without breaking your existing system.

## Quick Start

### 1. Install Dependencies

```bash
# Install updated requirements
pip install -r requirements.txt

# Install development tools (optional)
pip install -r requirements-dev.txt

# Setup pre-commit hooks (optional)
pre-commit install
```

### 2. Run Tests

```bash
# Verify everything works
pytest

# Run with coverage
pytest --cov=src --cov-report=html
```

## Usage Examples

### Using Configuration

**Old way:**
```python
# Hardcoded in app.py
step_map = {"NIFTY": 50, "BANKNIFTY": 100}
step = step_map.get(index_name, 50)
```

**New way:**
```python
from src.config.settings import TradingConfig

step = TradingConfig.STRIKE_STEPS.get(
    index_name,
    TradingConfig.DEFAULT_STRIKE_STEP
)
```

### Using Utilities

**Formatters:**
```python
from src.utils.formatters import format_number, format_price, format_percentage

# Format volume
volume_str = format_number(125000)  # "125.0K"

# Format price
price_str = format_price(19250.50)  # "₹19,250.50"

# Format percentage
pct_str = format_percentage(2.5)  # "2.50%"
```

**Calculations:**
```python
from src.utils.calculations import (
    calculate_atm_strike,
    get_surrounding_strikes,
    calculate_percentage_change
)

# Calculate ATM
atm_strike, step = calculate_atm_strike(19247.50, "NIFTY")
# Returns: (19250, 50)

# Get surrounding strikes
strikes = get_surrounding_strikes(19250, 50, count=2)
# Returns: [19150, 19200, 19250, 19300, 19350]

# Calculate change
change = calculate_percentage_change(110, 100)
# Returns: 10.0
```

**Validators:**
```python
from src.utils.validators import (
    is_market_open,
    is_valid_strike,
    is_liquid_option
)

# Check market hours
if is_market_open():
    # Trade

# Validate strike
if not is_valid_strike(19255, 50):
    raise ValueError("Invalid strike")

# Check liquidity
if is_liquid_option(oi=150000, volume=15000, min_oi=100000, min_volume=10000):
    # Use this option
```

### Using Logging

**Setup (once at startup):**
```python
from src.utils.logging_config import setup_system_loggers, get_logger

# Setup all loggers
setup_system_loggers()

# Get logger for your module
logger = get_logger('trading_system.polling')
```

**Usage:**
```python
logger.info("Starting data polling")
logger.warning("Rate limit approaching")
logger.error("Failed to fetch quotes", exc_info=True)
logger.debug("Detailed debug info")
```

**With context:**
```python
from src.utils.logging_config import get_contextual_logger

logger = get_contextual_logger('trading_system', index='NIFTY', strike=19250)
logger.info("Processing option")
# Logs: [index=NIFTY | strike=19250] Processing option
```

### Using KiteService

**Basic usage:**
```python
from src.services.kite_service import get_kite_service

# Get service instance
kite_service = get_kite_service()

# Set access token (from cache or login)
kite_service.set_access_token(access_token)

# Get quotes (with automatic retry)
quotes = kite_service.get_quote(["NSE:INFY", "NSE:TCS"])

# Get instruments (cached)
instruments = kite_service.get_instruments("NFO")

# Batch quotes (automatic batching)
all_quotes = kite_service.batch_quote(large_list_of_instruments)
```

**With error handling:**
```python
from src.services.kite_service import get_kite_service
from src.utils.exceptions import RateLimitError, KiteConnectionError
import time

kite_service = get_kite_service()

try:
    quotes = kite_service.get_quote(instruments)

except RateLimitError as e:
    logger.warning(f"Rate limited, waiting {e.retry_after}s")
    time.sleep(e.retry_after)
    quotes = kite_service.get_quote(instruments)

except KiteConnectionError as e:
    logger.error(f"Connection failed: {e}")
    # Use cached data or show error to user
```

### Using Models

**Volume models:**
```python
from src.models.volume import VolumeSpike, VolumeState, CEPEData
from datetime import datetime

# Create volume spike
spike = VolumeSpike(
    timestamp=datetime.now(),
    strike=19250,
    option_type="CE",
    volume=50000,
    avg_volume=10000,
    spike_ratio=5.0,
    is_atm=True,
    distance_from_atm=0,
    alert_level="STRONG"
)

# Convert to dict
spike_dict = spike.to_dict()

# Create volume state
volume_state = VolumeState()
volume_state.ce_pe_history.append({
    'timestamp': datetime.now(),
    'ce_volume': 100000,
    'pe_volume': 80000
})
```

**Engine models:**
```python
from src.models.engine import EngineState, MarketQuote

# Create engine state
engine = EngineState()

# Check if initialized
if engine.is_initialized():
    # Ready to use

# Get index metadata
nifty_meta = engine.get_index_metadata("NIFTY")

# Create market quote from Kite data
quote = MarketQuote.from_kite_quote(token, kite_quote_dict)
```

## Integration with Existing Code

### Step 1: Add Imports to app.py

At the top of `app.py`, add:

```python
# New imports
from src.config.settings import TradingConfig, PatternConfig, VolumeConfig
from src.utils.formatters import format_number, format_price
from src.utils.calculations import calculate_atm_strike
from src.utils.validators import is_market_open, is_liquid_option
from src.utils.logging_config import setup_system_loggers, get_logger
from src.services.kite_service import get_kite_service

# Setup logging (add after imports)
setup_system_loggers()
logger = get_logger('trading_system')
```

### Step 2: Replace Hardcoded Values

**Before:**
```python
step_map = {"NIFTY": 50, "BANKNIFTY": 100}
```

**After:**
```python
# Remove step_map, use TradingConfig.STRIKE_STEPS instead
from src.config.settings import TradingConfig
```

### Step 3: Replace Helper Functions

**Before:**
```python
def format_number(num):
    if num is None:
        return "—"
    # ...
```

**After:**
```python
# Remove function, use:
from src.utils.formatters import format_number
```

### Step 4: Add Error Handling

**Before:**
```python
try:
    quotes = kite.quote(instruments)
except:
    pass
```

**After:**
```python
from src.utils.exceptions import KiteConnectionError

try:
    quotes = kite_service.get_quote(instruments)
except KiteConnectionError as e:
    logger.error(f"Failed to get quotes: {e}")
    # Handle error appropriately
```

### Step 5: Replace Print Statements

**Before:**
```python
print(f"Starting polling...")
print(f"Error: {e}")
```

**After:**
```python
logger.info("Starting polling...")
logger.error(f"Error: {e}", exc_info=True)
```

## Testing Your Changes

### Run Unit Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_calculations.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=src --cov-report=term --cov-report=html
```

### Test Your App

```bash
# Run your Streamlit app
streamlit run app.py

# Check logs
tail -f logs/trading_system.log

# Check debug logs
tail -f data/debug/charts_debug.log
```

## Troubleshooting

### Import Errors

If you get `ModuleNotFoundError: No module named 'src'`:

```bash
# Option 1: Add to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:/home/user/Nifty-Trading"

# Option 2: Install as package (recommended)
pip install -e .
```

### Configuration Errors

If you get configuration warnings:

```python
from src.config.settings import validate_config

is_valid, errors = validate_config()
if not is_valid:
    for error in errors:
        print(f"Config error: {error}")
```

### API Credential Issues

```python
from src.config.settings import APIConfig

if not APIConfig.validate():
    print("ERROR: Missing API credentials in .env file")
    print("Please update .env with your Kite API key and secret")
```

## Best Practices

### 1. Always Use Utilities

```python
# ❌ Don't
if num >= 1000000:
    return f"{num/1000000:.1f}M"

# ✅ Do
from src.utils.formatters import format_number
return format_number(num)
```

### 2. Use Configuration

```python
# ❌ Don't
TOLERANCE = 0.20

# ✅ Do
from src.config.settings import PatternConfig
tolerance = PatternConfig.SIMILARITY_TOLERANCE
```

### 3. Use Proper Logging

```python
# ❌ Don't
print("Error:", e)

# ✅ Do
logger.error("Failed to process data", exc_info=True)
```

### 4. Handle Exceptions

```python
# ❌ Don't
try:
    data = fetch_data()
except:
    pass

# ✅ Do
from src.utils.exceptions import DataValidationError

try:
    data = fetch_data()
except DataValidationError as e:
    logger.warning(f"Invalid data: {e}")
    data = get_default_data()
```

### 5. Write Tests

```python
# tests/unit/test_my_function.py
from src.utils.my_module import my_function

def test_my_function():
    result = my_function(input_data)
    assert result == expected_output
```

## Getting Help

1. Check module docstrings: `help(module_name)`
2. Read source code in `src/` directories
3. Look at test files for usage examples
4. Check `IMPROVEMENTS.md` for overview
