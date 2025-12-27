#!/bin/bash
# ============================================
# TRADING DATA BACKUP SCRIPT
# Backs up your trading data safely
# ============================================

# Configuration
BACKUP_DIR="$HOME/trading_backups"
DATA_DIR="./data"
CACHE_DIR="./.cache"
MAX_BACKUPS=30  # Keep last 30 days of backups

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "============================================"
echo "Starting Trading Data Backup"
echo "============================================"

# Create backup directory if it doesn't exist
if [ ! -d "$BACKUP_DIR" ]; then
    mkdir -p "$BACKUP_DIR"
    echo -e "${GREEN}✓${NC} Created backup directory: $BACKUP_DIR"
fi

# Get current date and time
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="$BACKUP_DIR/trading_backup_$TIMESTAMP.tar.gz"

# Check if data directory exists
if [ ! -d "$DATA_DIR" ]; then
    echo -e "${YELLOW}⚠${NC} Warning: data/ folder doesn't exist yet"
    echo "   This is normal if you haven't run the app yet"
    echo "   Backup will include cache files only"
fi

# Create backup
echo ""
echo "Creating backup..."
echo "Backup location: $BACKUP_FILE"

# Include data folder if exists, always include cache
BACKUP_ITEMS=""
[ -d "$DATA_DIR" ] && BACKUP_ITEMS="$BACKUP_ITEMS $DATA_DIR"
[ -d "$CACHE_DIR" ] && BACKUP_ITEMS="$BACKUP_ITEMS $CACHE_DIR"

if [ -z "$BACKUP_ITEMS" ]; then
    echo -e "${YELLOW}⚠${NC} No data to backup yet"
    exit 0
fi

tar -czf "$BACKUP_FILE" $BACKUP_ITEMS 2>/dev/null

if [ $? -eq 0 ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}✓${NC} Backup created successfully!"
    echo "   Size: $BACKUP_SIZE"
else
    echo -e "${RED}✗${NC} Backup failed!"
    exit 1
fi

# Clean up old backups (keep last MAX_BACKUPS)
echo ""
echo "Cleaning old backups (keeping last $MAX_BACKUPS)..."
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/trading_backup_*.tar.gz 2>/dev/null | wc -l)

if [ $BACKUP_COUNT -gt $MAX_BACKUPS ]; then
    OLD_COUNT=$((BACKUP_COUNT - MAX_BACKUPS))
    ls -1t "$BACKUP_DIR"/trading_backup_*.tar.gz | tail -n $OLD_COUNT | xargs rm -f
    echo -e "${GREEN}✓${NC} Removed $OLD_COUNT old backup(s)"
else
    echo "   No old backups to remove"
fi

# Show backup summary
echo ""
echo "============================================"
echo "Backup Summary"
echo "============================================"
echo "Total backups: $(ls -1 "$BACKUP_DIR"/trading_backup_*.tar.gz 2>/dev/null | wc -l)"
echo "Backup directory size: $(du -sh "$BACKUP_DIR" | cut -f1)"
echo ""
echo "Latest 5 backups:"
ls -lht "$BACKUP_DIR"/trading_backup_*.tar.gz 2>/dev/null | head -5 | awk '{print "  " $9 " (" $5 ")"}'
echo ""
echo -e "${GREEN}✓ Backup completed successfully!${NC}"
echo "============================================"
