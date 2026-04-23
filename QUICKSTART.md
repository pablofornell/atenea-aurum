# Aurum Quick Start Guide

## Prerequisites
- Python 3.8+
- MetaTrader 4 with NMarkets Limited or compatible terminal
- Claude Code CLI installed and working
- Port 5555 available (for MT4 ↔ Python communication)

## 🚀 Automated Start (Recommended)

Run this single command:

```bash
python setup.py
```

This automates everything and will guide you through the few manual MT4 steps.

**See `START_HERE.md` for detailed step-by-step guide.**

---

## Manual Installation (if needed)

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Copy EA to MT4

```powershell
copy "ops\AURUM_Bridge.mq4" "C:\Program Files (x86)\NMarkets Limited MT4 Terminal\MQL4\Experts\"
```

### 3. Compile & Attach

1. **Ctrl+E** in MT4 → Open `MQL4/Experts/AURUM_Bridge.mq4`
2. **F5** to compile → "0 errors"
3. Tools → Options → Expert Advisors → **Enable "Allow DLL imports"** ✓
4. Open XAUUSD chart → Right-click → Expert Advisors → **Attach AURUM_Bridge**
5. Verify green **😊** smiley on chart

### 4. Test Connection

```bash
python -c "from src.mt4.bridge import MT4Bridge; b = MT4Bridge(); b.connect(); print('✓ Connected!' if b.ping() else '✗ Failed')"
```

Expected: `✓ Connected!`

### 5. Run Aurum

```bash
python aurum.py
```

Expected output:
```
[2024-04-23 10:15:00] root — INFO — ================================================================================
[2024-04-23 10:15:00] root — INFO — AURUM Trading System Starting
[2024-04-23 10:15:00] root — INFO — Connecting to MT4...
[2024-04-23 10:15:00] root — INFO — MT4 connected successfully
[2024-04-23 10:15:00] root — INFO — Database ready
[2024-04-23 10:15:00] root — INFO — Agent initialized, starting main loop...
[2024-04-23 10:15:00] root — INFO — Press Ctrl+C to stop
[2024-04-23 10:15:05] src.agent.agent — INFO — Starting new cycle: 3f4a8c2d-...
[2024-04-23 10:15:06] src.mt4.screenshot — INFO — Screenshot saved: C:\...\mt4_20240423_101506.png
```

System will:
1. Take screenshot of MT4 every 15 minutes
2. Send to Claude for analysis
3. Execute trades automatically
4. Log all activity to `aurum.log`

Stop with: **Ctrl+C**

---

## Troubleshooting

### "Cannot connect to MT4"
- [ ] EA has green smiley on chart?
- [ ] Port 5555 available? (check `netstat -an | findstr 5555`)
- [ ] DLL imports enabled in MT4?

### "Can't compile AURUM_Bridge.mq4"
- [ ] Is `socket-library-mt4-mt5.mqh` in `MQL4/Include/`?
- [ ] Did you run the install script?
- See `ops/README.md` for manual steps

### "Screenshot fails"
- [ ] Is MT4 window minimized? (System auto-restores but verify)
- [ ] `pywin32` installed? `pip install pywin32`

### Claude not responding
- [ ] Is `claude` CLI working? Test: `echo "say hello" | claude`
- [ ] Using `--dangerously-skip-permissions` flag? (Check `src/bridge/claude_bridge.py`)

---

## Files Overview

```
├── aurum.py                # Main trading loop — launched by setup.py
├── requirements.txt        # Dependencies: pytest, pywin32, Pillow
├── aurum.log              # Auto-created log file
├── aurum.db               # Auto-created SQLite database
├── CLAUDE.md              # Project context (loaded automatically)
├── ops/
│   ├── install_ea.ps1     # Automatic setup script
│   ├── AURUM_Bridge.mq4   # MT4 Expert Advisor
│   ├── socket-library-mt4-mt5.mqh  # Winsock header
│   └── README.md          # Detailed setup instructions
└── src/
    ├── agent/             # Trading agent logic
    ├── bridge/            # Claude CLI wrapper
    ├── db/                # SQLite storage
    ├── mt4/               # MT4 TCP client + screenshot
    └── tests/             # Unit & integration tests
```

---

## What Happens During a Cycle

1. **Screenshot**: Captures current MT4 chart (H1 by default)
2. **Claude Analysis**: Sends to Claude: screenshot + system prompt + previous context
3. **Action**: Claude responds with JSON action:
   - `BUY` / `SELL` → Place trade
   - `CLOSE` / `MODIFY` → Adjust existing trade
   - `CHANGE_TIMEFRAME` → Switch to different timeframe, re-analyze
   - `DONE` → Wait 15 minutes
4. **Log**: All actions and decisions logged to SQLite + `aurum.log`
5. **Wait**: Sleep 15 minutes until next cycle

---

## Testing (Optional)

Run tests:
```bash
pytest src/tests/unit/                # Unit tests (no MT4 required)
pytest src/tests/integration/ -m mt4  # Integration tests (MT4 required)
```

---

## Next: Production Setup

For long-term operation:
- [ ] Set up log rotation (aurum.log grows over time)
- [ ] Consider running in tmux/screen so it survives SSH disconnection
- [ ] Monitor aurum.db size (clean old cycles periodically)
- [ ] Adjust `cycle_interval` in `aurum.py` if needed (default: 900s = 15 min)

---

**Questions?** Check `CLAUDE.md` for full architecture or `ops/README.md` for MT4-specific details.
