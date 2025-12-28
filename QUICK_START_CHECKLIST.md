# ✅ Quick Start Checklist - Print This!

## Before You Start
- [ ] Computer with internet
- [ ] Kite API credentials ready
- [ ] 30 minutes of free time

---

## Step 1: Download Code
```bash
cd Documents
git clone https://github.com/sscchandra-hub/Nifty-Trading.git
cd Nifty-Trading
```
**Done?** [ ] Yes

---

## Step 2: Check Python
```bash
python3 --version
```
**See Python 3.x.x?** [ ] Yes

**If NO, install from:** https://www.python.org/downloads/

---

## Step 3: Setup Credentials

1. **Copy file:** `.env.example` → `.env`
2. **Edit `.env` file and add:**
   ```
   KITE_API_KEY=___________________________
   KITE_API_SECRET=________________________
   ```
3. **Save file**

**Done?** [ ] Yes

---

## Step 4: Install Packages

**Option A - Easy (Linux/Mac):**
```bash
chmod +x setup.sh
./setup.sh
```

**Option B - Manual:**
```bash
python3 -m venv venv
source venv/bin/activate        # Mac/Linux
# OR
venv\Scripts\activate           # Windows
pip install -r requirements.txt
```

**Installed?** [ ] Yes

---

## Step 5: Run App
```bash
streamlit run app.py
```

**Browser opened?** [ ] Yes
**See dashboard?** [ ] Yes

---

## 🎉 Success!

Your app is running at: **http://localhost:8501**

---

## To Stop:
- Press `Ctrl+C` in terminal
- Type: `deactivate`

---

## To Run Again:
```bash
cd Nifty-Trading
source venv/bin/activate    # Mac/Linux
streamlit run app.py
```

---

## Problems?
See **BEGINNER_GUIDE.md** for detailed help!

---

## Important Commands Reference

| Task | Command |
|------|---------|
| Go to folder | `cd Nifty-Trading` |
| Activate environment | `source venv/bin/activate` |
| Run app | `streamlit run app.py` |
| Stop app | Press `Ctrl+C` |
| Deactivate | `deactivate` |
| Check Python | `python3 --version` |
| Install packages | `pip install -r requirements.txt` |

---

**Print this page and keep it handy!** 📄
