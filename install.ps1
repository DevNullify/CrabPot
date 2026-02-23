#Requires -Version 5.1
<#
.SYNOPSIS
    CrabPot Windows Installer — bootstraps WSL2 + Ubuntu + CrabPot from a fresh Windows machine.

.DESCRIPTION
    Run from PowerShell (as Administrator if WSL2 is not yet installed):
        irm https://raw.githubusercontent.com/DevNullify/crabpot/main/install.ps1 | iex

    This script will:
      1. Check for / enable WSL2
      2. Install Ubuntu if no WSL2 distro is present
      3. Run install.sh inside the distro to install Docker, Python, and CrabPot
      4. Print next steps

.NOTES
    Requires Windows 10 version 2004+ or Windows 11.
    A reboot may be required after enabling WSL2 for the first time.
#>

$ErrorActionPreference = "Stop"

$CRABPOT_VERSION = "2.0.0"
$REPO_RAW = "https://raw.githubusercontent.com/DevNullify/crabpot/main"

# ── Helpers ────────────────────────────────────────────────────────────

function Write-Step  { param([string]$msg) Write-Host "[*] $msg" -ForegroundColor Cyan }
function Write-Ok    { param([string]$msg) Write-Host "[+] $msg" -ForegroundColor Green }
function Write-Warn  { param([string]$msg) Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Fail  { param([string]$msg) Write-Host "[-] $msg" -ForegroundColor Red; exit 1 }

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# ── Banner ─────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "CrabPot v$CRABPOT_VERSION — Windows Installer" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Check Windows version ──────────────────────────────────────────

Write-Step "Checking Windows version..."

$osVersion = [System.Environment]::OSVersion.Version
if ($osVersion.Build -lt 19041) {
    Write-Fail "WSL2 requires Windows 10 version 2004 (build 19041) or later. You have build $($osVersion.Build)."
}
Write-Ok "Windows build $($osVersion.Build) — compatible"

# ── 2. Check / install WSL2 ───────────────────────────────────────────

Write-Step "Checking WSL2..."

$wslExe = Get-Command wsl.exe -ErrorAction SilentlyContinue

if (-not $wslExe) {
    Write-Step "WSL is not installed. Installing WSL2..."

    if (-not (Test-Admin)) {
        Write-Fail "Administrator privileges required to install WSL2. Please re-run this script as Administrator."
    }

    # wsl --install enables WSL2, installs the Linux kernel, and sets WSL2 as default
    wsl --install --no-distribution
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "WSL installation failed. Please install WSL2 manually: https://aka.ms/wsl2"
    }

    Write-Warn "WSL2 has been installed. A REBOOT is required before continuing."
    Write-Host ""
    Write-Host "After rebooting, re-run this installer:" -ForegroundColor Yellow
    Write-Host "  irm $REPO_RAW/install.ps1 | iex" -ForegroundColor Cyan
    Write-Host ""
    $reboot = Read-Host "Reboot now? (y/N)"
    if ($reboot -eq 'y' -or $reboot -eq 'Y') {
        Restart-Computer -Force
    }
    exit 0
}

# Ensure WSL default version is 2
wsl --set-default-version 2 2>$null | Out-Null
Write-Ok "WSL2 is available"

# ── 3. Check / install Ubuntu distro ──────────────────────────────────

Write-Step "Checking for a WSL2 Linux distribution..."

# Parse wsl -l -v to find running/stopped distros
$distroOutput = (wsl -l -v 2>&1) | Out-String

# Find any installed distro (look for version "2" lines)
$hasDistro = $false
$defaultDistro = $null

# wsl -l -v output has Unicode chars, normalize it
$cleanOutput = $distroOutput -replace '\x00', '' -replace '\r', ''
$lines = $cleanOutput -split "`n" | Where-Object { $_.Trim() -ne '' }

foreach ($line in $lines) {
    # Match lines like: "* Ubuntu    Running  2" or "  Ubuntu-22.04  Stopped  2"
    if ($line -match '^\s*\*?\s*([\w\-\.]+)\s+\w+\s+2\s*$') {
        $hasDistro = $true
        $distroName = $Matches[1].Trim()
        if ($line -match '^\s*\*') {
            $defaultDistro = $distroName
        }
        elseif (-not $defaultDistro) {
            $defaultDistro = $distroName
        }
    }
}

if (-not $hasDistro) {
    Write-Step "No WSL2 distro found. Installing Ubuntu..."

    if (-not (Test-Admin)) {
        Write-Warn "Installing Ubuntu may require Administrator privileges."
    }

    wsl --install -d Ubuntu
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Ubuntu installation failed. Try manually: wsl --install -d Ubuntu"
    }

    $defaultDistro = "Ubuntu"
    Write-Ok "Ubuntu installed"

    Write-Host ""
    Write-Warn "Ubuntu will launch to complete first-time setup (create username/password)."
    Write-Warn "After setup completes and you exit the Ubuntu shell, re-run this installer."
    Write-Host ""
    Write-Host "  irm $REPO_RAW/install.ps1 | iex" -ForegroundColor Cyan
    Write-Host ""
    exit 0
}

Write-Ok "Found WSL2 distro: $defaultDistro"

# ── 4. Run install.sh inside WSL2 ─────────────────────────────────────

Write-Step "Downloading and running CrabPot installer inside WSL2..."

# Download install.sh to a temp location accessible from WSL
$tempDir = $env:TEMP
$installScript = Join-Path $tempDir "crabpot-install.sh"

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri "$REPO_RAW/install.sh" -OutFile $installScript -UseBasicParsing
}
catch {
    Write-Fail "Failed to download install.sh: $_"
}

Write-Ok "Downloaded install.sh"

# Convert Windows path to WSL path
$wslTempPath = wsl wslpath -u ($installScript -replace '\\', '/')
$wslTempPath = $wslTempPath.Trim()

# Run install.sh inside the default WSL2 distro
Write-Step "Running installer inside $defaultDistro..."
Write-Host ""

wsl -d $defaultDistro -- bash -e $wslTempPath
$exitCode = $LASTEXITCODE

# Clean up
Remove-Item $installScript -Force -ErrorAction SilentlyContinue

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Fail "Installation inside WSL2 failed (exit code $exitCode)."
}

# ── 5. Done ───────────────────────────────────────────────────────────

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  CrabPot v$CRABPOT_VERSION installed!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "To get started, open your WSL2 terminal and run:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  wsl" -ForegroundColor White
Write-Host "  crabpot init          # Choose target, security level, OpenClaw version" -ForegroundColor White
Write-Host "  crabpot setup         # Generate configs + build" -ForegroundColor White
Write-Host "  crabpot start         # Launch everything" -ForegroundColor White
Write-Host ""
Write-Host "Then open http://localhost:18789 in your browser for the OpenClaw Gateway." -ForegroundColor Cyan
Write-Host ""
