#!/bin/bash
# ============================================
# TRADING DATA RESTORE SCRIPT
# Restores your trading data from backup
# ============================================

# Configuration
BACKUP_DIR="$HOME/trading_backups"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "============================================"
echo "Trading Data Restore Tool"
echo "============================================"
echo ""

# Check if backup directory exists
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}✗${NC} Backup directory not found: $BACKUP_DIR"
    echo "   No backups available to restore"
    exit 1
fi

# List available backups
BACKUPS=($(ls -1t "$BACKUP_DIR"/trading_backup_*.tar.gz 2>/dev/null))

if [ ${#BACKUPS[@]} -eq 0 ]; then
    echo -e "${RED}✗${NC} No backups found in: $BACKUP_DIR"
    exit 1
fi

echo "Available backups:"
echo ""
for i in "${!BACKUPS[@]}"; do
    BACKUP_FILE="${BACKUPS[$i]}"
    BACKUP_NAME=$(basename "$BACKUP_FILE")
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    BACKUP_DATE=$(echo "$BACKUP_NAME" | sed 's/trading_backup_//; s/.tar.gz//; s/_/ /; s/_/:/; s/_/:/')
    printf "${BLUE}%2d${NC}) %s (%s)\n" $((i+1)) "$BACKUP_DATE" "$BACKUP_SIZE"
done

echo ""
echo -e "${YELLOW}⚠ WARNING:${NC} This will overwrite your current data!"
echo ""
read -p "Enter backup number to restore (or 'q' to quit): " CHOICE

if [ "$CHOICE" = "q" ] || [ "$CHOICE" = "Q" ]; then
    echo "Restore cancelled"
    exit 0
fi

# Validate choice
if ! [[ "$CHOICE" =~ ^[0-9]+$ ]] || [ "$CHOICE" -lt 1 ] || [ "$CHOICE" -gt ${#BACKUPS[@]} ]; then
    echo -e "${RED}✗${NC} Invalid choice"
    exit 1
fi

SELECTED_BACKUP="${BACKUPS[$((CHOICE-1))]}"

echo ""
echo "Selected backup: $(basename "$SELECTED_BACKUP")"
echo ""
read -p "Are you sure you want to restore? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Restore cancelled"
    exit 0
fi

# Backup current data before restoring (just in case)
if [ -d "./data" ] || [ -d "./.cache" ]; then
    SAFETY_BACKUP="$BACKUP_DIR/pre_restore_backup_$(date +"%Y-%m-%d_%H-%M-%S").tar.gz"
    echo ""
    echo "Creating safety backup of current data..."
    tar -czf "$SAFETY_BACKUP" ./data ./.cache 2>/dev/null
    echo -e "${GREEN}✓${NC} Safety backup created: $(basename "$SAFETY_BACKUP")"
fi

# Restore backup
echo ""
echo "Restoring backup..."
tar -xzf "$SELECTED_BACKUP" 2>/dev/null

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Backup restored successfully!"
    echo ""
    echo "Restored files:"
    tar -tzf "$SELECTED_BACKUP" | head -10
    echo ""
    echo -e "${GREEN}✓ Restore completed!${NC}"
else
    echo -e "${RED}✗${NC} Restore failed!"
    exit 1
fi
