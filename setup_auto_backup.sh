#!/bin/bash
# ============================================
# SETUP AUTOMATIC DAILY BACKUP
# Configures cron job for automatic backups
# ============================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "============================================"
echo "Automatic Backup Setup"
echo "============================================"
echo ""

# Get the absolute path to the script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup_data.sh"
LOG_FILE="$SCRIPT_DIR/backup.log"

echo "Script location: $SCRIPT_DIR"
echo "Backup script: $BACKUP_SCRIPT"
echo "Log file: $LOG_FILE"
echo ""

# Check if backup script exists
if [ ! -f "$BACKUP_SCRIPT" ]; then
    echo -e "${RED}✗${NC} Error: backup_data.sh not found!"
    exit 1
fi

# Make sure backup script is executable
chmod +x "$BACKUP_SCRIPT"

# Create the cron job entry
CRON_JOB="45 15 * * 1-5 cd $SCRIPT_DIR && ./backup_data.sh >> $LOG_FILE 2>&1"

echo -e "${BLUE}Cron job to be added:${NC}"
echo "$CRON_JOB"
echo ""
echo "This will run backup:"
echo "  • Every weekday (Monday-Friday)"
echo "  • At 3:45 PM (after market closes)"
echo "  • Logs saved to: backup.log"
echo ""

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "backup_data.sh"; then
    echo -e "${YELLOW}⚠${NC} Backup cron job already exists!"
    echo ""
    echo "Current backup cron jobs:"
    crontab -l | grep "backup_data.sh"
    echo ""
    read -p "Do you want to replace it? (yes/no): " REPLACE

    if [ "$REPLACE" != "yes" ]; then
        echo "Setup cancelled"
        exit 0
    fi

    # Remove old backup cron jobs
    crontab -l | grep -v "backup_data.sh" | crontab -
    echo -e "${GREEN}✓${NC} Removed old backup cron job"
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Automatic backup configured successfully!${NC}"
    echo ""
    echo "============================================"
    echo "Setup Complete"
    echo "============================================"
    echo ""
    echo "Backup schedule:"
    echo "  • Time: 3:45 PM (15:45)"
    echo "  • Days: Monday to Friday"
    echo "  • Location: ~/trading_backups/"
    echo "  • Retention: Last 30 backups"
    echo ""
    echo "To verify cron job:"
    echo "  crontab -l"
    echo ""
    echo "To view backup logs:"
    echo "  tail -f $LOG_FILE"
    echo ""
    echo "To disable automatic backup:"
    echo "  crontab -e"
    echo "  (then delete the backup_data.sh line)"
    echo ""
    echo -e "${BLUE}💡 Tip:${NC} Run a manual backup now to test:"
    echo "  ./backup_data.sh"
    echo ""
else
    echo -e "${RED}✗${NC} Failed to setup cron job"
    exit 1
fi
