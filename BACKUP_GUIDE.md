# 📦 Trading Data Backup Guide

## Quick Start

### ✅ Create a Backup (Manual)

Run this command after market closes:

```bash
./backup_data.sh
```

**What it does:**
- Backs up your `data/` folder (CSV files)
- Backs up your `.cache/` folder (cached data)
- Saves to `~/trading_backups/`
- Automatically deletes backups older than 30 days
- Shows summary of all backups

**Output example:**
```
============================================
Starting Trading Data Backup
============================================
✓ Created backup directory: /home/user/trading_backups

Creating backup...
Backup location: /home/user/trading_backups/trading_backup_2024-12-22_15-30-00.tar.gz
✓ Backup created successfully!
   Size: 45M

Total backups: 5
✓ Backup completed successfully!
============================================
```

---

## 🔄 Restore a Backup

If something goes wrong and you need to restore old data:

```bash
./restore_backup.sh
```

**Steps:**
1. Script shows list of available backups
2. Choose the number of the backup you want
3. Confirm (type `yes`)
4. Data is restored!

**Safety:** Before restoring, the script automatically creates a safety backup of your current data.

---

## 🤖 Automatic Daily Backups

### Set up automatic backup at 3:45 PM every day:

**Step 1: Open crontab**
```bash
crontab -e
```

**Step 2: Add this line at the bottom:**
```bash
45 15 * * 1-5 cd /home/user/Nifty-Trading && ./backup_data.sh >> backup.log 2>&1
```

This runs the backup:
- Every weekday (Monday-Friday)
- At 3:45 PM (after market close)
- Logs output to `backup.log`

**Step 3: Save and exit**
- Press `Ctrl+O` to save
- Press `Enter` to confirm
- Press `Ctrl+X` to exit

**To check if it's working:**
```bash
crontab -l  # List scheduled jobs
```

---

## 📁 Backup Location

All backups are saved to:
```
/home/user/trading_backups/
```

**Backup file format:**
```
trading_backup_2024-12-22_15-30-00.tar.gz
                  YYYY-MM-DD_HH-MM-SS
```

---

## 🗄️ What Gets Backed Up?

✅ **data/** folder
- All CSV files with historical market data
- Organized by date (data/historical/indices/2024-12-22/)

✅ **.cache/** folder
- Cached dashboard data
- Flow history
- Chart data

❌ **NOT backed up:**
- `app.py` (your code - use git for this)
- `.env` (credentials - keep separate secure copy)
- Large files like `instruments.csv`

---

## 🧹 Cleaning Up Old Backups

The script **automatically** keeps only the last **30 backups**.

**To change this:**
Edit `backup_data.sh` and change this line:
```bash
MAX_BACKUPS=30  # Change to 60 for 60 days, etc.
```

**Manual cleanup (delete all backups older than 7 days):**
```bash
find ~/trading_backups/ -name "trading_backup_*.tar.gz" -mtime +7 -delete
```

---

## 💾 Backup to External Drive

**Copy backups to USB drive:**
```bash
# Insert USB drive, then:
cp ~/trading_backups/*.tar.gz /media/usb/trading_backups/
```

**Copy to cloud (Google Drive, Dropbox, etc.):**
```bash
# If you have rclone configured:
rclone copy ~/trading_backups/ gdrive:trading_backups/
```

---

## 🚨 Emergency: Restore Last Backup

If your data gets corrupted:

```bash
# Quick restore (automatically picks latest backup)
./restore_backup.sh
# Choose option 1 (latest backup)
# Type "yes" to confirm
```

---

## 📊 Check Backup Status

**See all backups:**
```bash
ls -lh ~/trading_backups/
```

**Count total backups:**
```bash
ls -1 ~/trading_backups/ | wc -l
```

**Total backup size:**
```bash
du -sh ~/trading_backups/
```

**View what's inside a backup (without extracting):**
```bash
tar -tzf ~/trading_backups/trading_backup_2024-12-22_15-30-00.tar.gz
```

---

## ⚠️ Important Notes

1. **Run backup AFTER market close** (after 3:30 PM)
   - Ensures full day's data is captured
   - App can still be running (safe to backup while running)

2. **Backups are compressed**
   - Original data: 100 MB
   - Backup file: ~20-30 MB (saves space)

3. **Keep backups for at least 30 days**
   - In case you need to compare old patterns
   - Safety net for data corruption

4. **Test restore once!**
   - Before you need it, try restoring to make sure it works
   - Better to learn now than during an emergency

---

## 🔐 Backup Security

**Your backups contain market data but NO sensitive info:**
- ✅ Market prices (public data)
- ✅ Calculated flows (your analysis)
- ❌ NO API keys (stored in `.env` which is NOT backed up)
- ❌ NO passwords

**To include .env in backup (not recommended):**
```bash
# Only do this if you're backing up to encrypted drive!
tar -czf secure_backup.tar.gz data/ .cache/ .env
```

---

## 🆘 Troubleshooting

**Problem: "Permission denied"**
```bash
# Solution: Make scripts executable
chmod +x backup_data.sh restore_backup.sh
```

**Problem: "No space left on device"**
```bash
# Solution: Clean old backups
rm ~/trading_backups/trading_backup_2024-11-*.tar.gz
```

**Problem: "data/ folder not found"**
```
This is normal if you haven't run the app yet.
The folder gets created when app starts collecting data.
```

**Problem: Backup is empty (0 bytes)**
```bash
# Check if data folder has files
ls -la data/

# Run backup with verbose output
bash -x ./backup_data.sh
```

---

## 📞 Quick Commands Reference

| Task | Command |
|------|---------|
| Create backup | `./backup_data.sh` |
| Restore backup | `./restore_backup.sh` |
| List backups | `ls -lh ~/trading_backups/` |
| Delete old backups | `find ~/trading_backups/ -mtime +30 -delete` |
| Copy to USB | `cp ~/trading_backups/*.tar.gz /media/usb/` |
| Check cron job | `crontab -l` |
| View backup contents | `tar -tzf <backup-file>` |

---

## ✅ Best Practices

1. **Backup daily** - Set up the cron job (automatic is best!)
2. **Keep 30 days** - Don't delete too soon
3. **Test restore** - Try it once to make sure it works
4. **External copy** - Copy important backups to USB/cloud weekly
5. **After major changes** - Always backup before upgrading app

---

**Need help? Check `backup.log` for error messages after automatic backups run.**
