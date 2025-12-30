# 🤖 Setup Automatic Daily Backup

## ✅ Quick Setup (2 Minutes)

Follow these simple steps to set up automatic backup after market closes every day.

---

## 📋 Step-by-Step Instructions

### **Step 1: Open Terminal**

Open terminal in your Nifty-Trading folder:
```bash
cd /home/user/Nifty-Trading
```

---

### **Step 2: Run Setup Script**

```bash
bash setup_auto_backup.sh
```

**What it does:**
- Automatically configures cron job
- Sets backup time to 3:45 PM
- Only runs on weekdays (Mon-Fri)
- Creates backup.log file for monitoring

**Expected output:**
```
✓ Automatic backup configured successfully!

Backup schedule:
  • Time: 3:45 PM (15:45)
  • Days: Monday to Friday
  • Location: ~/trading_backups/
  • Retention: Last 30 backups
```

**Done!** Your automatic backup is now configured.

---

## 🔍 Verify It's Working

### Check if cron job is active:
```bash
crontab -l
```

**You should see:**
```
45 15 * * 1-5 cd /home/user/Nifty-Trading && ./backup_data.sh >> /home/user/Nifty-Trading/backup.log 2>&1
```

---

## 📊 Monitor Backups

### View backup log (see what happened):
```bash
tail -f backup.log
```

Press `Ctrl+C` to stop viewing.

### Check if backups are being created:
```bash
ls -lht ~/trading_backups/ | head -10
```

**Expected output:**
```
-rw-r--r-- 1 user user 45M Dec 22 15:45 trading_backup_2024-12-22_15-45-01.tar.gz
-rw-r--r-- 1 user user 43M Dec 21 15:45 trading_backup_2024-12-21_15-45-02.tar.gz
-rw-r--r-- 1 user user 41M Dec 20 15:45 trading_backup_2024-12-20_15-45-03.tar.gz
```

---

## ⏰ Backup Schedule

| Day | Time | Action |
|-----|------|--------|
| Monday | 3:45 PM | ✅ Auto backup |
| Tuesday | 3:45 PM | ✅ Auto backup |
| Wednesday | 3:45 PM | ✅ Auto backup |
| Thursday | 3:45 PM | ✅ Auto backup |
| Friday | 3:45 PM | ✅ Auto backup |
| Saturday | - | ⏸️ No backup (market closed) |
| Sunday | - | ⏸️ No backup (market closed) |

---

## 🛠️ Manual Setup (Alternative Method)

If the setup script doesn't work, do it manually:

### 1. Open crontab editor:
```bash
crontab -e
```

### 2. Add this line at the bottom:
```bash
45 15 * * 1-5 cd /home/user/Nifty-Trading && ./backup_data.sh >> /home/user/Nifty-Trading/backup.log 2>&1
```

### 3. Save and exit:
- **nano editor:** Press `Ctrl+O`, `Enter`, then `Ctrl+X`
- **vim editor:** Press `Esc`, type `:wq`, press `Enter`

### 4. Verify:
```bash
crontab -l
```

---

## ⚙️ Customize Backup Time

Want to backup at a different time?

**Edit the cron job:**
```bash
crontab -e
```

**Change the time (format: MINUTE HOUR):**
```bash
# Backup at 4:00 PM
0 16 * * 1-5 cd /home/user/Nifty-Trading && ./backup_data.sh >> backup.log 2>&1

# Backup at 5:30 PM
30 17 * * 1-5 cd /home/user/Nifty-Trading && ./backup_data.sh >> backup.log 2>&1

# Backup at 6:00 AM (before market opens)
0 6 * * 1-5 cd /home/user/Nifty-Trading && ./backup_data.sh >> backup.log 2>&1
```

**Cron time format:**
```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6, Sunday = 0)
│ │ │ │ │
* * * * *
```

**Examples:**
- `45 15 * * 1-5` = 3:45 PM, Monday-Friday
- `0 16 * * *` = 4:00 PM, Every day
- `30 9 * * 1-5` = 9:30 AM, Monday-Friday

---

## 🔕 Disable Automatic Backup

To stop automatic backups:

```bash
crontab -e
```

Delete the line with `backup_data.sh`, then save and exit.

**Or remove all cron jobs:**
```bash
crontab -r
```

---

## 📧 Get Email Notifications (Optional)

Want email when backup completes?

### 1. Install mail utility:
```bash
sudo apt-get install mailutils
```

### 2. Modify cron job:
```bash
crontab -e
```

### 3. Add MAILTO at the top:
```bash
MAILTO=your.email@gmail.com

45 15 * * 1-5 cd /home/user/Nifty-Trading && ./backup_data.sh >> backup.log 2>&1
```

Now you'll get email with backup status!

---

## 🚨 Troubleshooting

### **Problem: Backup not running automatically**

**Check if cron is running:**
```bash
sudo systemctl status cron
```

**If not running, start it:**
```bash
sudo systemctl start cron
sudo systemctl enable cron
```

---

### **Problem: Backup runs but fails**

**Check the log file:**
```bash
cat backup.log
```

**Common issues:**
- Script not executable → `chmod +x backup_data.sh`
- Wrong path → Use full path `/home/user/Nifty-Trading/backup_data.sh`
- Permission denied → Check folder permissions

---

### **Problem: Can't edit crontab**

**Check default editor:**
```bash
echo $EDITOR
```

**Set editor to nano (easier):**
```bash
export EDITOR=nano
crontab -e
```

---

### **Problem: Cron job runs but no backup file**

**Test backup manually first:**
```bash
cd /home/user/Nifty-Trading
./backup_data.sh
```

**Check if it works. If yes, check cron job path:**
```bash
crontab -l
```

Make sure path is correct: `/home/user/Nifty-Trading`

---

## ✅ Verification Checklist

After setup, verify everything works:

- [ ] Run setup script: `bash setup_auto_backup.sh`
- [ ] Check cron job: `crontab -l`
- [ ] Test manual backup: `./backup_data.sh`
- [ ] Check backup folder: `ls -lh ~/trading_backups/`
- [ ] Wait until 3:45 PM and check if auto backup runs
- [ ] Check log file: `cat backup.log`

---

## 📅 First Automatic Backup

**When will first automatic backup run?**

- **Today (if before 3:45 PM):** Today at 3:45 PM
- **Today (if after 3:45 PM):** Tomorrow at 3:45 PM
- **Weekend:** Next Monday at 3:45 PM

**To see when next cron job runs:**
```bash
# Install cron utilities
sudo apt-get install cron

# Check cron logs
grep CRON /var/log/syslog | tail -10
```

---

## 💡 Best Practices

1. **Test it once** - Run manual backup before relying on automatic
2. **Check weekly** - Verify backups are being created
3. **Monitor disk space** - Ensure enough space for 30 backups
4. **External backup** - Copy important backups to USB weekly
5. **Test restore** - Try restoring once to ensure it works

---

## 📞 Quick Reference

| Task | Command |
|------|---------|
| Setup auto backup | `bash setup_auto_backup.sh` |
| View cron jobs | `crontab -l` |
| Edit cron jobs | `crontab -e` |
| View backup log | `tail -f backup.log` |
| List backups | `ls -lh ~/trading_backups/` |
| Manual backup | `./backup_data.sh` |
| Disable auto backup | `crontab -e` (delete line) |

---

**Need help? Check `backup.log` for error messages!**
