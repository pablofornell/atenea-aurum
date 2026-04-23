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

$includeDir    = Join-Path $MT4Path "MQL4\Include"
$expertsDir    = Join-Path $MT4Path "MQL4\Experts"
$indicatorsDir = Join-Path $MT4Path "MQL4\Indicators"

# Create directories if they don't exist
Write-Host "Creating directories..."
New-Item -ItemType Directory -Path $includeDir    -Force | Out-Null
New-Item -ItemType Directory -Path $expertsDir    -Force | Out-Null
New-Item -ItemType Directory -Path $indicatorsDir -Force | Out-Null

# Get current script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ---- Copy EA ----
$eaSource = Join-Path $scriptDir "AURUM_Bridge.mq4"
$eaDest   = Join-Path $expertsDir "AURUM_Bridge.mq4"

if (-not (Test-Path $eaSource)) {
    Write-Host "ERROR: EA file not found: $eaSource" -ForegroundColor Red
    exit 1
}

Write-Host "Copying Expert Advisor..."
Write-Host "  From: $eaSource"
Write-Host "  To:   $eaDest"
Copy-Item $eaSource $eaDest -Force
if ($?) {
    Write-Host "  ✓ AURUM_Bridge EA copied successfully" -ForegroundColor Green
} else {
    Write-Host "  ✗ Failed to copy EA" -ForegroundColor Red
    exit 1
}

# ---- Copy Indicator package ----
$indSource = Join-Path $scriptDir "AURUM_Indicators.mq4"
$indDest   = Join-Path $indicatorsDir "AURUM_Indicators.mq4"

if (-not (Test-Path $indSource)) {
    Write-Host "WARNING: Indicator file not found: $indSource — skipping" -ForegroundColor Yellow
} else {
    Write-Host "Copying Indicator package..."
    Write-Host "  From: $indSource"
    Write-Host "  To:   $indDest"
    Copy-Item $indSource $indDest -Force
    if ($?) {
        Write-Host "  ✓ AURUM_Indicators copied successfully" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Failed to copy indicator" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=================================="
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host "=================================="
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Reload MetaEditor (or restart MT4)"
Write-Host "2. In MT4: Tools > Options > Expert Advisors > Enable 'Allow DLL imports'"
Write-Host "3. Attach AURUM_Bridge EA to XAUUSD chart"
Write-Host "4. Attach AURUM_Indicators to the same XAUUSD chart"
Write-Host "5. Verify green smiley face icon appears on chart"
Write-Host "6. Check Experts tab for: '[AURUM] Server listening on 127.0.0.1:5555'"
Write-Host ""
