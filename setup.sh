#!/bin/bash
# Setup script for Nifty Trading System

set -e  # Exit on error

echo "========================================="
echo "Nifty Trading System - Setup"
echo "========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Found Python $python_version"
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "✓ Activated"
echo ""

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip > /dev/null
echo "✓ Pip upgraded"
echo ""

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# Ask about dev dependencies
read -p "Install development dependencies? (y/N): " install_dev
if [ "$install_dev" = "y" ] || [ "$install_dev" = "Y" ]; then
    echo "Installing dev dependencies..."
    pip install -r requirements-dev.txt
    echo "✓ Dev dependencies installed"
    echo ""

    # Setup pre-commit hooks
    read -p "Setup pre-commit hooks? (y/N): " setup_hooks
    if [ "$setup_hooks" = "y" ] || [ "$setup_hooks" = "Y" ]; then
        echo "Installing pre-commit hooks..."
        pre-commit install
        echo "✓ Pre-commit hooks installed"
    fi
fi
echo ""

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️  WARNING: .env file not found!"
    echo "Please copy .env.example to .env and add your credentials"
    echo ""
    read -p "Create .env from template now? (y/N): " create_env
    if [ "$create_env" = "y" ] || [ "$create_env" = "Y" ]; then
        cp .env.example .env
        echo "✓ Created .env file"
        echo "⚠️  Please edit .env and add your API credentials"
    fi
else
    echo "✓ .env file found"
fi
echo ""

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p data/historical/indices
mkdir -p data/debug
mkdir -p .cache
mkdir -p logs
echo "✓ Directories created"
echo ""

# Run tests
read -p "Run tests to verify installation? (y/N): " run_tests
if [ "$run_tests" = "y" ] || [ "$run_tests" = "Y" ]; then
    echo "Running tests..."
    pytest -v
    echo ""
fi

echo "========================================="
echo "✅ Setup complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env and add your API credentials"
echo "2. Activate virtual environment: source venv/bin/activate"
echo "3. Run the app: streamlit run app.py"
echo ""
echo "For more information, see:"
echo "- IMPROVEMENTS.md - Overview of changes"
echo "- MIGRATION_GUIDE.md - How to use new structure"
echo ""
