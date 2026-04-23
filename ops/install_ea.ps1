# Install AURUM_Bridge EA and dependencies to MT4
# Run this with: powershell -ExecutionPolicy Bypass -File install_ea.ps1

param(
    [string]$MT4Path = "C:\Program Files (x86)\NMarkets Limited MT4 Terminal"
)

Write-Host "=================================="
Write-Host "AURUM MT4 EA Installation Script"
Write-Host "=================================="
Write-Host ""

# Verify MT4 path exists
if (-not (Test-Path $MT4Path)) {
    Write-Host "ERROR: MT4 path not found: $MT4Path" -ForegroundColor Red
    Write-Host "Please specify correct MT4 path with: .\install_ea.ps1 -MT4Path 'C:\Your\MT4\Path'" -ForegroundColor Yellow
    exit 1
}

$includeDir = Join-Path $MT4Path "MQL4\Include"
$expertsDir = Join-Path $MT4Path "MQL4\Experts"

# Create directories if they don't exist
Write-Host "Creating directories..."
New-Item -ItemType Directory -Path $includeDir -Force | Out-Null
New-Item -ItemType Directory -Path $expertsDir -Force | Out-Null

# Get current script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Copy header file
$headerSource = Join-Path $scriptDir "socket-library-mt4-mt5.mqh"
$headerDest = Join-Path $includeDir "socket-library-mt4-mt5.mqh"

if (-not (Test-Path $headerSource)) {
    Write-Host "ERROR: Header file not found: $headerSource" -ForegroundColor Red
    exit 1
}

Write-Host "Copying header file..."
Write-Host "  From: $headerSource"
Write-Host "  To:   $headerDest"
Copy-Item $headerSource $headerDest -Force
if ($?) {
    Write-Host "  ✓ Header copied successfully" -ForegroundColor Green
} else {
    Write-Host "  ✗ Failed to copy header" -ForegroundColor Red
    exit 1
}

# Copy EA file
$eaSource = Join-Path $scriptDir "AURUM_Bridge.mq4"
$eaDest = Join-Path $expertsDir "AURUM_Bridge.mq4"

if (-not (Test-Path $eaSource)) {
    Write-Host "ERROR: EA file not found: $eaSource" -ForegroundColor Red
    exit 1
}

Write-Host "Copying Expert Advisor..."
Write-Host "  From: $eaSource"
Write-Host "  To:   $eaDest"
Copy-Item $eaSource $eaDest -Force
if ($?) {
    Write-Host "  ✓ EA copied successfully" -ForegroundColor Green
} else {
    Write-Host "  ✗ Failed to copy EA" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=================================="
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host "=================================="
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Open MetaEditor (Ctrl+E in MT4)"
Write-Host "2. Open MQL4/Experts/AURUM_Bridge.mq4"
Write-Host "3. Compile (F5)"
Write-Host "4. In MT4: Tools > Options > Expert Advisors > Enable 'Allow DLL imports'"
Write-Host "5. Attach AURUM_Bridge EA to XAUUSD chart"
Write-Host "6. Verify green smiley face icon appears on chart"
Write-Host ""
