# 🖥️ WINDOWS VPS DEPLOYMENT GUIDE
## Run Your Dashboard 24/7 in the Cloud (With All Your Data)

---

## WHY YOU NEED THIS

Your dashboard requires:
- ✅ Live Kite API data fetching
- ✅ Cache data (stored locally)
- ✅ Historical data (stored locally)
- ✅ Backups (stored locally)
- ✅ Session state (in memory)

**Simple cloud deployment (Streamlit Cloud) won't work** because it can't access your local data.

**Solution:** Deploy your ENTIRE project (app + data) to a Windows VPS.

---

## WHAT IS WINDOWS VPS?

**VPS = Virtual Private Server**
- Your own Windows computer in the cloud
- Runs 24/7 (even when your laptop is off)
- You control it via Remote Desktop (like using your own PC)
- Access your dashboard from anywhere

**Think of it as:** Renting a computer in a professional data center that never shuts down.

---

## RECOMMENDED PROVIDER: CONTABO

**Why Contabo:**
- ✅ Cheapest Windows VPS: €8.99/month (~₹800/month)
- ✅ Good performance
- ✅ No credit card verification hassles
- ✅ European servers (stable)
- ✅ 24/7 support

**Other Options:**
- **Vultr:** $12/month
- **DigitalOcean:** $24/month
- **Kamatera:** Free 30-day trial

---

## STEP-BY-STEP SETUP (30 MINUTES)

### STEP 1: Purchase Windows VPS

1. **Go to Contabo:**
   - Visit: https://contabo.com/en/vps/
   - Click "VPS S" or "VPS M" (recommend VPS M for better performance)

2. **Configuration:**
   - **Operating System:** Windows Server 2019 or 2022
   - **Location:** Choose closest to India (Singapore if available)
   - **Storage:** 400GB NVMe (included)
   - **RAM:** 8GB (VPS M) - recommended
   - **Period:** Monthly (can cancel anytime)

3. **Checkout:**
   - Create account
   - Pay via PayPal or Credit Card
   - **Cost:** €8.99 - €14.99/month

4. **Wait for Setup Email:**
   - Takes 30-60 minutes
   - You'll receive email with:
     - IP Address: `123.456.789.101`
     - Username: `Administrator`
     - Password: `YourPassword123`

---

### STEP 2: Connect to Your VPS

1. **Open Remote Desktop Connection:**
   - **Windows:** Press `Win + R`, type `mstsc`, press Enter
   - **Mac:** Download "Microsoft Remote Desktop" from App Store
   - **Linux:** Install Remmina

2. **Connect:**
   - **Computer:** Enter your VPS IP address
   - Click "Connect"
   - **Username:** Administrator
   - **Password:** (from email)
   - Click "Yes" to certificate warning

3. **You're In!**
   - You now see a Windows desktop running in the cloud
   - This computer runs 24/7

---

### STEP 3: Setup Windows Environment

1. **Install Chrome:**
   - Open Edge browser (pre-installed)
   - Download Chrome: https://www.google.com/chrome/
   - Install Chrome

2. **Install Python:**
   - Download Python 3.11: https://www.python.org/downloads/
   - **IMPORTANT:** Check "Add Python to PATH"
   - Click "Install Now"

3. **Install Git (Optional):**
   - Download: https://git-scm.com/download/win
   - Install with default settings

---

### STEP 4: Copy Your Project to VPS

**Method 1: Drag and Drop (Easiest)**

1. **On Your Laptop:**
   - Compress `Nifty-Trading` folder to ZIP
   - Right-click folder → "Send to" → "Compressed (zipped) folder"

2. **In Remote Desktop:**
   - Your laptop's drives appear in VPS
   - Open "This PC" → You'll see your laptop drives
   - Copy the ZIP file to VPS Desktop
   - Extract it

**Method 2: GitHub (If project is on GitHub)**

1. **In VPS Command Prompt:**
   ```bash
   cd Desktop
   git clone https://github.com/sscchandra-hub/Nifty-Trading.git
   cd Nifty-Trading
   git checkout claude/analyze-repository-clYhi
   ```

**Method 3: Direct File Transfer**

1. **Use FileZilla or WinSCP:**
   - Download WinSCP: https://winscp.net/
   - Connect to VPS
   - Transfer files

---

### STEP 5: Setup Dashboard

1. **Open Command Prompt on VPS:**
   - Press `Win + R`
   - Type `cmd`
   - Press Enter

2. **Navigate to Project:**
   ```bash
   cd Desktop\Nifty-Trading
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create .env File:**
   - Copy your `.env` file from laptop to VPS
   - Or create new one:
   ```
   API_KEY=your_kite_api_key
   API_SECRET=your_kite_api_secret
   TELEGRAM_BOT_TOKEN=your_telegram_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id
   ```

---

### STEP 6: Run Dashboard

**Option 1: Double-Click (Easiest)**
- Double-click `START_TRADING.bat`
- Dashboard opens in Chrome

**Option 2: Command Line**
```bash
streamlit run app.py
```

**Option 3: Auto-Restart (Most Stable)**
```bash
pip install psutil
python auto_restart_chrome.py
```

---

### STEP 7: Access Dashboard from Anywhere

**From Your Laptop/Phone/Tablet:**

1. **Open any browser**
2. **Go to:** `http://YOUR_VPS_IP:8501`
   - Replace `YOUR_VPS_IP` with IP from email
   - Example: `http://123.456.789.101:8501`

3. **Bookmark it!**

**Now your dashboard is accessible 24/7 from ANY device!**

---

## FIREWALL SETUP (IMPORTANT)

**Allow Port 8501 for Dashboard Access:**

1. **In VPS, Open Windows Firewall:**
   - Control Panel → System and Security → Windows Defender Firewall
   - Click "Advanced settings"

2. **Add Inbound Rule:**
   - Click "Inbound Rules" → "New Rule"
   - Rule Type: **Port**
   - Protocol: **TCP**
   - Port: **8501**
   - Action: **Allow**
   - Name: **Streamlit Dashboard**
   - Click "Finish"

3. **Test Access:**
   - From your laptop browser: `http://VPS_IP:8501`
   - Should see your dashboard!

---

## KEEP VPS RUNNING 24/7

**Prevent VPS from Sleeping:**

1. **Disable Sleep Mode:**
   - Control Panel → Power Options
   - Choose "High performance"
   - Click "Change plan settings"
   - Set "Turn off display" to **Never**
   - Set "Put computer to sleep" to **Never**

2. **Disable Automatic Updates Restart:**
   - Settings → Update & Security
   - Windows Update → Advanced options
   - Turn OFF "Restart this device as soon as possible"

3. **Run Dashboard on Startup:**
   - Press `Win + R`, type `shell:startup`
   - Create shortcut to `START_TRADING.bat`
   - Dashboard auto-starts on VPS reboot

---

## COPY YOUR DATA TO VPS

**Important Files to Copy:**

1. **Cache Directory:**
   - Copy your entire cache folder to VPS
   - Preserves all historical data

2. **Backup Files:**
   - Copy all `.json`, `.csv`, `.db` files

3. **.env File:**
   - Must have API credentials

4. **Any Data Directories:**
   - Copy everything in your project folder

---

## MAINTENANCE

**Weekly Tasks:**
- None! It just runs.

**Monthly Tasks:**
- Pay VPS bill (auto-renewal available)
- Optional: Update Windows security patches

**When Market Closed:**
- Keep VPS running or stop Streamlit
- VPS runs 24/7 regardless

---

## SECURITY RECOMMENDATIONS

1. **Change Default Password:**
   - In VPS, press `Ctrl+Alt+End`
   - Choose "Change password"
   - Use strong password

2. **Use VPN (Optional):**
   - Install Tailscale for secure access
   - Access via private network

3. **Backup Important Data:**
   - Download backups to your laptop weekly

---

## COST BREAKDOWN

| Provider | RAM | Storage | CPU | Price/Month |
|----------|-----|---------|-----|-------------|
| **Contabo VPS S** | 4GB | 200GB | 4 cores | €8.99 (~₹800) |
| **Contabo VPS M** | 8GB | 400GB | 6 cores | €14.99 (~₹1,300) |
| **Vultr** | 4GB | 128GB | 2 cores | $12 (~₹1,000) |
| **DigitalOcean** | 4GB | 80GB | 2 cores | $24 (~₹2,000) |

**Recommendation:** Contabo VPS M (best performance for price)

---

## TROUBLESHOOTING

**Can't Connect to Remote Desktop:**
- Check VPS IP address is correct
- Ensure VPS is running (check Contabo panel)
- Check your internet connection

**Can't Access Dashboard from Laptop:**
- Verify firewall port 8501 is open
- Check Streamlit is running on VPS
- Try: `http://VPS_IP:8501` not `https://`

**Dashboard Crashes on VPS:**
- Use auto_restart_chrome.py
- Or just restart VPS

**Kite API Not Working:**
- Verify .env file has correct credentials
- Check Kite API session is valid

---

## ADVANTAGES OF THIS SETUP

✅ **Dashboard runs 24/7** (even when laptop is off)
✅ **Access from anywhere** (phone, tablet, any device)
✅ **All your data preserved** (cache, backups, everything)
✅ **No Chrome crashes** (better memory management)
✅ **Professional setup** (like real trading firms)
✅ **Your laptop is free** (no need to keep it running)
✅ **Scales easily** (upgrade VPS if needed)

---

## NEXT STEPS

1. **Choose VPS Provider** (Contabo recommended)
2. **Purchase VPS** (takes 5 minutes)
3. **Wait for Setup Email** (30-60 minutes)
4. **Follow Steps Above** (30 minutes setup)
5. **Start Trading Tomorrow!** 🚀

---

## SUPPORT

**VPS Provider Support:**
- Contabo: support@contabo.com
- Vultr: https://www.vultr.com/support/
- DigitalOcean: https://www.digitalocean.com/support/

**Your Dashboard Issues:**
- Check logs in VPS
- Verify dependencies installed
- Test locally first

---

## ALTERNATIVE: USE YOUR OLD LAPTOP AS SERVER

**If you have an old laptop you don't use:**

1. **Install Ubuntu/Windows**
2. **Setup dashboard** (same as above)
3. **Keep it running 24/7** at home
4. **Access remotely** via Tailscale (free)
5. **Cost:** FREE (just electricity ~₹100/month)

---

**This is the production-grade solution that keeps ALL your features and data!** 🚀
