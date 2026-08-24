$ErrorActionPreference = "Stop"

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Assert-ExitCode($Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step Р·Р°РІРµСЂС€РёР»СЃСЏ СЃ РєРѕРґРѕРј $LASTEXITCODE"
    }
}

try {
    Write-Host "AI Reels Editor v1.3.4 вЂ” Р±РµР·РѕРїР°СЃРЅР°СЏ РїРµСЂРІРѕРЅР°С‡Р°Р»СЊРЅР°СЏ РЅР°СЃС‚СЂРѕР№РєР°" -ForegroundColor Cyan
    $ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $ProjectRoot

    if (-not (Test-Command "python")) {
        throw "Python РЅРµ РЅР°Р№РґРµРЅ. РЈСЃС‚Р°РЅРѕРІРёС‚Рµ Python 3.11+ Рё РІРєР»СЋС‡РёС‚Рµ Add Python to PATH."
    }
    $VersionText = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    Assert-ExitCode "РџСЂРѕРІРµСЂРєР° Python"
    if ([version]$VersionText -lt [version]"3.11") {
        throw "РќСѓР¶РµРЅ Python 3.11+, РЅР°Р№РґРµРЅ $VersionText"
    }

    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-Host "РЎРѕР·РґР°СЋ .venv..."
        & python -m venv .venv
        Assert-ExitCode "РЎРѕР·РґР°РЅРёРµ .venv"
    }

    Write-Host "РЈСЃС‚Р°РЅР°РІР»РёРІР°СЋ Р·Р°РєСЂРµРїР»С‘РЅРЅС‹Рµ Python-Р·Р°РІРёСЃРёРјРѕСЃС‚Рё..."
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    Assert-ExitCode "РћР±РЅРѕРІР»РµРЅРёРµ pip"
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    Assert-ExitCode "РЈСЃС‚Р°РЅРѕРІРєР° Python-Р·Р°РІРёСЃРёРјРѕСЃС‚РµР№"

    if (-not (Test-Command "ffmpeg") -or -not (Test-Command "ffprobe")) {
        throw "FFmpeg/ffprobe РЅРµ РЅР°Р№РґРµРЅС‹. РЈСЃС‚Р°РЅРѕРІРёС‚Рµ FFmpeg Рё РґРѕР±Р°РІСЊС‚Рµ bin РІ PATH."
    }
    & ffmpeg -version | Select-Object -First 1
    Assert-ExitCode "РџСЂРѕРІРµСЂРєР° FFmpeg"
    & ffprobe -version | Select-Object -First 1
    Assert-ExitCode "РџСЂРѕРІРµСЂРєР° ffprobe"

    if (-not (Test-Command "node") -or -not (Test-Command "npm")) {
        throw "Node.js/npm РЅРµ РЅР°Р№РґРµРЅС‹. РЈСЃС‚Р°РЅРѕРІРёС‚Рµ Node.js 22+."
    }
    $NodeVersion = & node -p "process.versions.node"
    Assert-ExitCode "РџСЂРѕРІРµСЂРєР° Node.js"
    if ([version]$NodeVersion -lt [version]"22.0") {
        throw "HyperFrames 0.8.12 С‚СЂРµР±СѓРµС‚ Node.js 22+, РЅР°Р№РґРµРЅ $NodeVersion"
    }

    Write-Host "РЈСЃС‚Р°РЅР°РІР»РёРІР°СЋ HyperFrames 0.8.12 РёР· lockfile..."
    Push-Location "node_tools\hyperframes"
    try {
        & npm ci
        Assert-ExitCode "npm ci HyperFrames"
        $env:HYPERFRAMES_NO_UPDATE_CHECK = "1"
        $env:HYPERFRAMES_NO_TELEMETRY = "1"
        & .\node_modules\.bin\hyperframes.cmd browser ensure
        Assert-ExitCode "РЈСЃС‚Р°РЅРѕРІРєР° HyperFrames browser"
    } finally {
        Pop-Location
    }

    Write-Host "РЈСЃС‚Р°РЅР°РІР»РёРІР°СЋ Motion Canvas 3.17.2 РёР· lockfile Рё Chromium..."
    Push-Location "node_tools\motion_canvas"
    try {
        & npm ci
        Assert-ExitCode "npm ci Motion Canvas"
        & .\node_modules\.bin\playwright.cmd install chromium
        Assert-ExitCode "РЈСЃС‚Р°РЅРѕРІРєР° Playwright Chromium"
    } finally {
        Pop-Location
    }

    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "РЎРѕР·РґР°РЅ .env. Р РµР°Р»СЊРЅС‹Рµ РєР»СЋС‡Рё С…СЂР°РЅРёС‚Рµ С‚РѕР»СЊРєРѕ Р·РґРµСЃСЊ." -ForegroundColor Yellow
    }
    Write-Host "РџСЂРё TRANSCRIPTION_PROVIDER=faster_whisper РјРѕРґРµР»СЊ СЃРєР°С‡РёРІР°РµС‚СЃСЏ РїСЂРё РїРµСЂРІРѕРј Reel; doctor РѕС‚РґРµР»СЊРЅРѕ РїРѕРєР°Р·С‹РІР°РµС‚ РіРѕС‚РѕРІРЅРѕСЃС‚СЊ cache." -ForegroundColor Yellow

    Write-Host "Р—Р°РїСѓСЃРєР°СЋ РѕР±СЏР·Р°С‚РµР»СЊРЅС‹Р№ doctor..."
    & .\.venv\Scripts\python.exe main.py doctor --json
    Assert-ExitCode "Doctor"
    Write-Host "РќР°СЃС‚СЂРѕР№РєР° Р·Р°РІРµСЂС€РµРЅР°. Р—Р°РїСѓСЃРє: start_editor.bat" -ForegroundColor Green
} catch {
    Write-Host "РќРђРЎРўР РћР™РљРђ РћРЎРўРђРќРћР’Р›Р•РќРђ: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Assert-ExitCode "Установка HyperFrames browser"
