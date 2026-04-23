# 🚀 AURUM — Start Here

## Quick Start (5 minutes)

### 1. Open Windows Terminal

Navigate to the Aurum repository:
```bash
cd C:\Users\hefesto-w10x64\Documents\repos\atenea-aurum
```

### 2. Run the Automated Startup

```bash
python start.py
```

That's it! The script will:
- ✅ Install Python dependencies automatically
- ✅ Copy the EA and header files to MT4
- ⚠️ Guide you through manual MT4 steps (compilation, permissions, attaching EA)
- ✅ Wait for MT4 to be ready
- ✅ Launch the trading system

---

## What Happens During Each Step

### 1️⃣ Python Dependencies
Automatically installs: `pytest`, `pywin32`, `Pillow`

### 2️⃣ EA Installation
Copies `AURUM_Bridge.mq4` and `socket-library-mt4-mt5.mqh` to MT4 folders

### 3️⃣ EA Compilation
**You'll be prompted to:**
1. Open MetaTrader 4
2. Press **Ctrl+E** (MetaEditor)
3. Open `MQL4/Experts/AURUM_Bridge.mq4`
4. Press **F5** to compile
5. Verify "0 errors" appears
6. Return to terminal and press Enter

### 4️⃣ DLL Imports Permission
**You'll be prompted to:**
1. In MT4: **Tools → Options**
2. Click **Expert Advisors** tab
3. Check ✓ **Allow DLL imports**
4. Click **OK**
5. Return to terminal and press Enter

### 5️⃣ EA Attachment
**You'll be prompted to:**
1. Open **XAUUSD** chart in MT4
2. Right-click → **Expert Advisors → Attach Expert Advisor**
3. Select **AURUM_Bridge** → OK
4. Verify green 😊 smiley appears on chart
5. Return to terminal and press Enter

### 6️⃣ MT4 Connection
Script automatically waits and confirms MT4 is listening on port 5555

### 7️⃣ System Launch
Automatically launches the trading system

---

## Expected Output

Once running, you'll see:
```
[2026-04-23 10:15:00] root — INFO — ================================================================================
[2026-04-23 10:15:00] root — INFO — AURUM Trading System Starting
[2026-04-23 10:15:00] root — INFO — Connecting to MT4...
[2026-04-23 10:15:00] root — INFO — MT4 connected successfully
[2026-04-23 10:15:00] root — INFO — Database ready
[2026-04-23 10:15:00] root — INFO — Agent initialized, starting main loop...
[2026-04-23 10:15:00] root — INFO — Press Ctrl+C to stop
```

System will then:
- Take a screenshot every 15 minutes
- Send it to Claude for analysis
- Execute trades automatically
- Log everything to `aurum.log`

---

## Stop the System

Press **Ctrl+C** in the terminal

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "MT4 path not found" | Update `MT4_PATH` in `start.py` if your MT4 is installed elsewhere |
| "Cannot compile EA" | Make sure `socket-library-mt4-mt5.mqh` was copied to `MQL4/Include/` |
| "MT4 did not respond" | Ensure EA has green smiley on chart, DLL imports enabled, port 5555 is free |
| "Cannot connect to MT4" | Run: `netstat -an \| findstr 5555` to verify port is listening |
| Python import errors | Run `python start.py` again to reinstall dependencies |

---

## Files Created

During startup, these files are created automatically:
- `aurum.log` — Complete trading log
- `aurum.db` — SQLite database with trade history

---

## Next: Advanced Usage

Once the system is running:
- Check `QUICKSTART.md` for detailed features
- Check `CLAUDE.md` for system architecture
- Check `ops/README.md` for MT4-specific details
- View trading logs: `tail -f aurum.log`
- View database: `sqlite3 aurum.db`

---

**Ready?** Run: `python start.py`
