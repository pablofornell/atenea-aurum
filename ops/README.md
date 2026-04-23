# MT4 Setup Instructions for Aurum

## Quick Start

The Expert Advisor runs a TCP server on `127.0.0.1:5555` using direct **Winsock DLL imports** (standalone, no external headers required).

### Automated Installation

```powershell
powershell -ExecutionPolicy Bypass -File ops/install_ea.ps1
```

This copies `AURUM_Bridge.mq4` to your MT4 `Experts` folder automatically.

### Manual Setup (if needed)

1. Copy `ops/AURUM_Bridge.mq4` → `C:\Program Files (x86)\NMarkets Limited MT4 Terminal\MQL4\Experts\`
2. Reload MetaEditor or restart MT4
3. Verify: Open MetaEditor and check for "0 errors" when you browse to the file

### Enable DLL Imports in MT4

1. Tools → Options → **Expert Advisors** tab
2. Check: **"Allow DLL imports"** ✓
3. Click OK

### Attach EA to XAUUSD Chart

1. Open **XAUUSD** chart
2. Right-click → Expert Advisors → **Attach Expert Advisor**
3. Select: **AURUM_Bridge** → OK
4. Verify: Green smiley on chart (if red/none, check Experts tab for errors)

### Verify Server is Running

Open MT4 **Experts** tab, you should see:
```
[AURUM] Server listening on 127.0.0.1:5555
```

## Test Connection

```bash
python -c "from src.mt4.bridge import MT4Bridge; b = MT4Bridge(); b.connect(); print('✓ TCP Connected!' if b.ping() else '✗ Failed')"
```

## Troubleshooting

**Red smiley or no icon**
- Check Experts tab for errors
- Verify "Allow DLL imports" is enabled
- Port 5555 not in use

**Connection refused**
- Verify EA is running (green smiley)
- Check port 5555: `netstat -an | findstr 5555`
