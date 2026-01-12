# 🤝 Contributing to NIFTY Options Flow Trading System

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

---

## 📋 Table of Contents

1. [Getting Started](#getting-started)
2. [Development Setup](#development-setup)
3. [Code Style & Standards](#code-style--standards)
4. [Pull Request Process](#pull-request-process)
5. [Testing Requirements](#testing-requirements)
6. [Documentation Standards](#documentation-standards)
7. [Commit Message Guidelines](#commit-message-guidelines)
8. [Issue Reporting](#issue-reporting)
9. [Feature Requests](#feature-requests)
10. [Code Review Process](#code-review-process)

---

## Getting Started

### Prerequisites

Before contributing, ensure you have:
- **Python 3.8+** installed
- **Git** installed and configured
- **Zerodha Kite Connect** account (for testing)
- **Telegram Bot** (for alert testing)
- Familiarity with **Streamlit**, **pandas**, **numpy**

### Fork & Clone

```bash
# Fork the repository on GitHub
# Then clone your fork
git clone https://github.com/YOUR_USERNAME/Nifty-Trading.git
cd Nifty-Trading

# Add upstream remote
git remote add upstream https://github.com/ORIGINAL_OWNER/Nifty-Trading.git
```

---

## Development Setup

### 1. Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
# Install production dependencies
pip install -r requirements.txt

# Install development dependencies (if available)
pip install -r requirements-dev.txt

# Or install dev tools manually
pip install black isort flake8 pylint mypy pytest pytest-cov
```

### 3. Configure Environment

```bash
# Copy .env example
cp .env.example .env

# Edit .env with your credentials
nano .env
```

### 4. Run the Application

```bash
# Start Streamlit dashboard
streamlit run app.py

# Access at http://localhost:8501
```

---

## Code Style & Standards

### Python Style Guide

We follow **PEP 8** with some modifications:

#### Line Length
- **Maximum 100 characters** (not 79)
- Use backslashes or parentheses for line continuation

#### Imports
```python
# Standard library imports
import os
import sys
from datetime import datetime, timedelta

# Third-party imports
import streamlit as st
import pandas as pd
import numpy as np
from kiteconnect import KiteConnect

# Local imports
from patterns import detect_pattern
from oi_liquidity import calculate_liquidity
```

#### Naming Conventions
- **Functions**: `snake_case` (e.g., `calculate_sector_breadth()`)
- **Variables**: `snake_case` (e.g., `ce_pe_ratio`)
- **Classes**: `PascalCase` (e.g., `EngineState`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `KITE_API_KEY`)
- **Private methods**: `_leading_underscore` (e.g., `_internal_helper()`)

#### Docstrings
Use **Google-style docstrings**:

```python
def calculate_ce_pe_ratio(ce_flow, pe_flow):
    """
    Calculate CE/PE ratio from option flows.

    Args:
        ce_flow (float): Call option flow
        pe_flow (float): Put option flow

    Returns:
        float: CE/PE ratio (or 999 if PE flow is 0)

    Raises:
        ValueError: If ce_flow or pe_flow is negative

    Example:
        >>> calculate_ce_pe_ratio(100, 50)
        2.0
    """
    if pe_flow <= 0:
        return 999 if ce_flow > 0 else 0
    return ce_flow / pe_flow
```

#### Type Hints
Use type hints for function signatures:

```python
from typing import Dict, List, Optional, Tuple

def fetch_quotes(instruments: List[str]) -> Dict[str, Dict]:
    """Fetch quotes for multiple instruments"""
    pass

def calculate_score(data: Dict) -> Tuple[int, Dict[str, int]]:
    """Calculate score and breakdown"""
    pass
```

### Code Formatting

#### 1. Use Black for Auto-Formatting
```bash
# Format single file
black app.py

# Format all Python files
black .

# Check without modifying
black --check app.py
```

#### 2. Use isort for Import Sorting
```bash
# Sort imports in file
isort app.py

# Sort all files
isort .

# Check without modifying
isort --check-only app.py
```

### Linting

#### 1. Flake8 (Style Checker)
```bash
# Check single file
flake8 app.py

# Check all files
flake8 .

# Ignore specific errors
flake8 --ignore=E501,W503 app.py
```

#### 2. Pylint (Static Analysis)
```bash
# Check single file
pylint app.py

# Check with specific score
pylint --fail-under=8.0 app.py
```

#### 3. Mypy (Type Checker)
```bash
# Type check file
mypy app.py

# Check with strict mode
mypy --strict app.py
```

---

## Pull Request Process

### 1. Create Feature Branch

```bash
# Sync with upstream
git fetch upstream
git checkout main
git merge upstream/main

# Create feature branch
git checkout -b feature/your-feature-name

# Or for bug fixes
git checkout -b fix/bug-description
```

### 2. Make Changes

- Write clean, documented code
- Follow coding standards
- Add tests for new functionality
- Update documentation

### 3. Commit Changes

```bash
# Stage changes
git add .

# Commit with descriptive message
git commit -m "feat: Add new alert type for volume spikes"
```

See [Commit Message Guidelines](#commit-message-guidelines) for format details.

### 4. Push to Your Fork

```bash
# Push feature branch
git push origin feature/your-feature-name
```

### 5. Create Pull Request

1. Go to GitHub repository
2. Click "New Pull Request"
3. Select your branch
4. Fill out PR template:
   - **Title**: Clear, descriptive (e.g., "feat: Add volume spike alerts")
   - **Description**: What changes were made and why
   - **Related Issues**: Link to issue number (e.g., "Closes #42")
   - **Testing**: How you tested the changes
   - **Screenshots**: If UI changes are involved

### 6. Address Review Feedback

- Respond to comments
- Make requested changes
- Push updates to same branch (PR auto-updates)

### 7. Merge

Once approved, maintainers will merge your PR.

---

## Testing Requirements

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_alerts.py

# Run specific test
pytest tests/test_alerts.py::test_bullish_alert_conditions

# Run with coverage
pytest --cov=. --cov-report=html
pytest --cov=. --cov-report=term-missing
```

### Writing Tests

#### 1. Test File Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── test_alerts.py           # Alert system tests
├── test_calculations.py     # Calculation function tests
├── test_api_integration.py  # API integration tests
└── fixtures/
    ├── sample_stock_data.json
    └── sample_indices_data.json
```

#### 2. Test Example

```python
import pytest
from datetime import datetime

def test_calculate_ce_pe_ratio():
    """Test CE/PE ratio calculation"""
    # Test normal case
    assert calculate_ce_pe_ratio(100, 50) == 2.0

    # Test edge case: PE flow is 0
    assert calculate_ce_pe_ratio(100, 0) == 999

    # Test both flows are 0
    assert calculate_ce_pe_ratio(0, 0) == 0

def test_bullish_alert_conditions():
    """Test bullish alert triggering logic"""
    stock_data = {
        'price': 1000,
        'change_pct': 1.5,
        'ce_flow': 100,
        'pe_flow': 40,
        'net_flow': 60
    }
    sector_breadth = {
        'positive_count': 8,
        'negative_count': 3
    }

    # Should trigger alert
    assert should_trigger_bullish_alert(stock_data, sector_breadth) == True

    # Should NOT trigger (price change too low)
    stock_data['change_pct'] = 0.5
    assert should_trigger_bullish_alert(stock_data, sector_breadth) == False
```

#### 3. Use Fixtures for Sample Data

```python
@pytest.fixture
def sample_stock_data():
    """Sample stock data for testing"""
    return {
        'RELIANCE': {
            'price': 2500,
            'change_pct': 1.2,
            'ce_flow': 150,
            'pe_flow': 60,
            'net_flow': 90
        },
        'TCS': {
            'price': 3500,
            'change_pct': -1.5,
            'ce_flow': 40,
            'pe_flow': 120,
            'net_flow': -80
        }
    }

def test_alert_with_fixture(sample_stock_data):
    """Test using fixture"""
    reliance_data = sample_stock_data['RELIANCE']
    assert reliance_data['net_flow'] > 0
```

### Test Coverage Requirements

- **New features**: Minimum **80% coverage**
- **Critical alert logic**: **100% coverage**
- **API integration**: Mock external calls, test error handling

---

## Documentation Standards

### 1. Code Comments

```python
# Use comments to explain WHY, not WHAT
# Good:
# Calculate net flow to determine option buying pressure
net_flow = ce_flow - pe_flow

# Bad:
# Subtract PE flow from CE flow
net_flow = ce_flow - pe_flow
```

### 2. Function Docstrings

Every public function must have a docstring:

```python
def calculate_nifty_momentum_score(indices_data, stocks_data, volume_state, vwap_st_strategy):
    """
    Calculate comprehensive NIFTY momentum score from 8 parameters.

    NOTE: VWAP/SuperTrend scoring has been DISABLED (was ±15 points)
    New score range: -85 to +85 (instead of -100 to +100)

    Args:
        indices_data (dict): Dictionary of sectoral index data
        stocks_data (dict): Dictionary of individual stock data
        volume_state (VolumeState): Volume spike tracking state
        vwap_st_strategy (dict): VWAP & SuperTrend strategy data (unused)

    Returns:
        dict: {
            'total_score': int (-85 to +85),
            'breakdown': dict of parameter scores,
            'signal': 'BULLISH' | 'BEARISH' | 'NEUTRAL'
        }

    Example:
        >>> momentum = calculate_nifty_momentum_score(...)
        >>> print(momentum['total_score'])
        72
        >>> print(momentum['signal'])
        'BULLISH'
    """
```

### 3. Update README & ARCHITECTURE

- If you add a new feature, update [README.md](README.md)
- If you change system architecture, update [ARCHITECTURE.md](ARCHITECTURE.md)
- If you add/modify alerts, update [NIFTY_ALERT_CONDITIONS.md](NIFTY_ALERT_CONDITIONS.md)

### 4. Inline Documentation

Use inline comments for complex logic:

```python
# Check if 3-minute confirmation period has elapsed
# This prevents false positives from short-lived score spikes
elapsed = (now - engine.nifty_alert_confirmation['start_time']).total_seconds()
if elapsed < 180:  # 3 minutes = 180 seconds
    return  # Still confirming, wait for more readings
```

---

## Commit Message Guidelines

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation changes
- **style**: Code style changes (formatting, no logic change)
- **refactor**: Code refactoring (no functional change)
- **test**: Adding or updating tests
- **chore**: Maintenance tasks (dependencies, build config)
- **perf**: Performance improvements

### Scope (Optional)

- **alerts**: Alert system changes
- **ui**: Dashboard UI changes
- **api**: API integration changes
- **data**: Data processing changes

### Examples

```bash
# Feature addition
git commit -m "feat(alerts): Add volume spike alert type"

# Bug fix
git commit -m "fix(alerts): Correct cooldown timer logic for SL alerts"

# Documentation
git commit -m "docs: Update ARCHITECTURE.md with threading model"

# Refactoring
git commit -m "refactor(data): Extract CE/PE calculation to separate function"

# Performance
git commit -m "perf(api): Implement response caching to reduce API calls"
```

### Body (Optional)

Provide additional context:

```
feat(alerts): Add volume spike alert type

Added new alert type that triggers when volume spike exceeds 3x
average volume. This helps identify sudden institutional activity.

- Implemented spike detection logic
- Added Telegram message formatter
- Updated documentation

Closes #42
```

### Footer (Optional)

- **Breaking changes**: `BREAKING CHANGE: <description>`
- **Issue references**: `Closes #42`, `Fixes #55`, `Resolves #67`

---

## Issue Reporting

### Before Submitting an Issue

1. **Search existing issues** to avoid duplicates
2. **Check documentation** (README, ARCHITECTURE, FAQ)
3. **Test with latest version** (pull from main branch)

### Bug Report Template

```markdown
## Bug Description
Clear, concise description of the bug.

## Steps to Reproduce
1. Go to '...'
2. Click on '...'
3. See error

## Expected Behavior
What you expected to happen.

## Actual Behavior
What actually happened.

## Screenshots
If applicable, add screenshots.

## Environment
- OS: [e.g., Ubuntu 22.04]
- Python Version: [e.g., 3.9.7]
- Streamlit Version: [e.g., 1.28.0]
- Browser: [e.g., Chrome 120]

## Additional Context
Any other relevant information.

## Logs
Paste relevant logs (if applicable):
```
<paste logs here>
```
```

---

## Feature Requests

### Feature Request Template

```markdown
## Feature Description
Clear, concise description of the feature.

## Problem it Solves
Explain the problem this feature addresses.

## Proposed Solution
Describe how you envision the feature working.

## Alternatives Considered
Other approaches you've considered.

## Use Case Example
Concrete example of how this would be used.

## Additional Context
Any other relevant information, mockups, or references.
```

---

## Code Review Process

### As a Contributor

When your PR is under review:

1. **Respond promptly** to reviewer comments
2. **Be open to feedback** - reviews improve code quality
3. **Ask questions** if feedback is unclear
4. **Make requested changes** or explain your reasoning
5. **Test thoroughly** after making changes

### As a Reviewer

When reviewing PRs:

1. **Be respectful and constructive**
2. **Focus on code quality**, not personal preferences
3. **Provide specific suggestions** (not just "this is bad")
4. **Check for**:
   - Correctness of logic
   - Code style compliance
   - Test coverage
   - Documentation updates
   - Potential performance issues
   - Security concerns
5. **Approve when satisfied** or request changes with clear reasoning

---

## Development Best Practices

### 1. Keep PRs Small & Focused

- One feature/fix per PR
- Easier to review and test
- Faster to merge

### 2. Write Self-Documenting Code

```python
# Good: Self-explanatory
if change_pct > 1.0 and ce_pe_ratio > 2.0:
    trigger_bullish_alert()

# Bad: Requires comments
if x > 1.0 and y > 2.0:  # Check if bullish
    trigger_alert()
```

### 3. Handle Errors Gracefully

```python
try:
    quotes = kite.quote(instruments)
except Exception as e:
    logger.error(f"Quote fetch failed: {e}")
    # Use cached data or return empty dict
    quotes = st.session_state.get('cached_quotes', {})
```

### 4. Use Type Hints

```python
def send_telegram_message(message: str, parse_mode: str = 'HTML') -> bool:
    """Send formatted message to Telegram"""
    pass
```

### 5. Avoid Hardcoded Values

```python
# Bad
if elapsed < 180:  # Magic number

# Good
CONFIRMATION_PERIOD_SECONDS = 180
if elapsed < CONFIRMATION_PERIOD_SECONDS:
```

### 6. Use Descriptive Variable Names

```python
# Bad
x = ce - pe
r = ce / pe

# Good
net_flow = ce_flow - pe_flow
ce_pe_ratio = ce_flow / pe_flow
```

### 7. DRY (Don't Repeat Yourself)

```python
# Bad: Repeated logic
if stock == "RELIANCE":
    ce_pe_ratio = ce_flow / pe_flow if pe_flow > 0 else 999
elif stock == "TCS":
    ce_pe_ratio = ce_flow / pe_flow if pe_flow > 0 else 999

# Good: Extract to function
def calculate_ce_pe_ratio(ce_flow, pe_flow):
    return ce_flow / pe_flow if pe_flow > 0 else 999

reliance_ratio = calculate_ce_pe_ratio(ce_flow, pe_flow)
tcs_ratio = calculate_ce_pe_ratio(ce_flow, pe_flow)
```

---

## Development Workflow Example

### Complete workflow from idea to merge:

```bash
# 1. Sync with upstream
git fetch upstream
git checkout main
git merge upstream/main

# 2. Create feature branch
git checkout -b feat/volume-spike-alerts

# 3. Make changes
# - Edit app.py
# - Add tests in tests/test_volume_alerts.py
# - Update ARCHITECTURE.md

# 4. Format code
black app.py tests/test_volume_alerts.py
isort app.py tests/test_volume_alerts.py

# 5. Run linters
flake8 app.py tests/test_volume_alerts.py

# 6. Run tests
pytest tests/test_volume_alerts.py -v

# 7. Commit changes
git add .
git commit -m "feat(alerts): Add volume spike alert type

Implemented new alert type that triggers when volume exceeds 3x average.
Helps identify sudden institutional activity.

- Added spike detection logic (app.py:8800-8850)
- Created Telegram message formatter
- Added unit tests with 95% coverage
- Updated ARCHITECTURE.md

Closes #42"

# 8. Push to fork
git push origin feat/volume-spike-alerts

# 9. Create PR on GitHub
# - Fill out PR template
# - Wait for review
# - Address feedback
# - Push updates

# 10. After merge, cleanup
git checkout main
git pull upstream main
git branch -d feat/volume-spike-alerts
```

---

## Questions?

- **General questions**: Open a GitHub Discussion
- **Bugs**: Open a GitHub Issue
- **Security issues**: Email maintainers directly (do NOT open public issue)

---

## Code of Conduct

### Our Pledge

We pledge to make participation in this project a harassment-free experience for everyone, regardless of:
- Age, body size, disability, ethnicity, gender identity
- Level of experience, nationality, personal appearance
- Race, religion, sexual identity and orientation

### Expected Behavior

- Use welcoming and inclusive language
- Be respectful of differing viewpoints
- Accept constructive criticism gracefully
- Focus on what's best for the community
- Show empathy towards others

### Unacceptable Behavior

- Trolling, insulting/derogatory comments
- Public or private harassment
- Publishing others' private information
- Other conduct inappropriate in a professional setting

### Enforcement

Violations may result in:
1. Warning
2. Temporary ban
3. Permanent ban

Report violations to project maintainers.

---

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (MIT License).

---

**Thank you for contributing to the NIFTY Options Flow Trading System!** 🙏

Every contribution, no matter how small, makes a difference. Whether it's fixing a typo, reporting a bug, or adding a major feature - we appreciate your effort!

Happy coding! 🚀
