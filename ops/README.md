# MT4 Setup Instructions for Aurum

## One-Time Setup (TCP Sockets)

The Expert Advisor runs a TCP server on `127.0.0.1:5555` using direct Winsock DLL imports (no external headers).

### Step 1: Copy EA to MT4 Experts Folder

```powershell
copy "ops\AURUM_Bridge.mq4" "C:\Program Files (x86)\NMarkets Limited MT4 Terminal\MQL4\Experts\"
```

### Step 2: Compile in MetaEditor

1. **Ctrl+E** in MT4 (open MetaEditor)
2. Open: `MQL4/Experts/AURUM_Bridge.mq4`
3. Compile: **F5**
4. Verify: "0 errors" (no external headers needed)

### Step 3: Enable DLL Imports

In MT4:
1. Tools → Options → **Expert Advisors** tab
2. Check: **"Allow DLL imports"** ✓
3. OK

### Step 4: Attach to Chart

1. Open **XAUUSD** chart
2. Right-click → Expert Advisors → **Attach Expert Advisor**
3. Select: **AURUM_Bridge** → OK
4. Verify: Green 😊 smiley on chart

### Step 5: Check Logs

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
