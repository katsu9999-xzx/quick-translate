# クイック翻訳 1行インストーラ
#
# 使い方 (PowerShell をユーザー権限で):
#   irm https://raw.githubusercontent.com/katsu9999-xzx/quick-translate/main/install.ps1 | iex
#
# 何をするか:
#   1) Python 3.13 (pythonw.exe) を検索 / 無ければ winget で導入を試行
#   2) %LOCALAPPDATA%\Programs\QuickTranslate\ にソースを展開
#   3) pip install --user で依存導入
#   4) デスクトップショートカット作成
#   5) Windows スタートアップ登録
#   6) アプリ起動

$ErrorActionPreference = "Stop"

$REPO  = "katsu9999-xzx/quick-translate"
$BRANCH = "main"
$RAW = "https://raw.githubusercontent.com/$REPO/$BRANCH"
$FILES = @(
  "main.py",
  "requirements.txt",
  "config.example.json",
  "start.bat",
  "start_admin.bat",
  "stop.bat",
  "install_ocr_langs.ps1",
  "icon.ico",
  "README.md",
  "LICENSE"
)

$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\QuickTranslate"

function Write-Step($msg) {
  Write-Host "==> $msg" -ForegroundColor Cyan
}

# ---- 1) Python 確認 ----
Write-Step "Python (pythonw.exe) を確認"
$pyw = $null
# Microsoft Store 版 Python 3.13
$storePy = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\pythonw.exe"
if (Test-Path $storePy) {
  $pyw = $storePy
} else {
  $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
  if ($cmd) { $pyw = $cmd.Path }
}

if (-not $pyw) {
  Write-Host "Python 3.13 が見つかりません。winget で導入を試みます..." -ForegroundColor Yellow
  try {
    winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements
  } catch {
    Write-Host "winget での導入に失敗。手動で Python 3.13 を入れてからもう一度実行してください。" -ForegroundColor Red
    Write-Host "  https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
  }
  if (Test-Path $storePy) { $pyw = $storePy }
  else {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd) { $pyw = $cmd.Path }
  }
}
if (-not $pyw) {
  Write-Host "Python 導入後に PATH 反映のため PowerShell を開き直してから再実行してください。" -ForegroundColor Red
  exit 1
}
Write-Host "  pythonw: $pyw"

$py = $pyw -replace "pythonw\.exe$", "python.exe"
if (-not (Test-Path $py)) {
  $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
  if ($cmd) { $py = $cmd.Path }
}

# ---- 2) インストール先準備 + ファイル取得 ----
Write-Step "インストール先: $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

foreach ($f in $FILES) {
  $url = "$RAW/$f"
  $dest = Join-Path $InstallDir $f
  Write-Host "  - $f"
  if ($f -eq "icon.ico") {
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
  } else {
    $bytes = (Invoke-WebRequest -Uri $url -UseBasicParsing).Content
    if ($bytes -is [byte[]]) {
      [System.IO.File]::WriteAllBytes($dest, $bytes)
    } else {
      Set-Content -Path $dest -Value $bytes -Encoding UTF8 -NoNewline
    }
  }
}

# config.json が無ければ example をコピー
$cfg = Join-Path $InstallDir "config.json"
if (-not (Test-Path $cfg)) {
  Copy-Item (Join-Path $InstallDir "config.example.json") $cfg
}

# ---- 3) 依存導入 ----
Write-Step "依存パッケージを pip install"
& $py -m pip install --user --upgrade --quiet -r (Join-Path $InstallDir "requirements.txt")

# ---- 4) デスクトップショートカット ----
Write-Step "デスクトップショートカットを作成"
$ws = New-Object -ComObject WScript.Shell
$desk = [Environment]::GetFolderPath('Desktop')
$lnkD = Join-Path $desk 'QuickTranslate.lnk'
$l = $ws.CreateShortcut($lnkD)
$l.TargetPath = $pyw
$l.Arguments = "`"$InstallDir\main.py`""
$l.WorkingDirectory = $InstallDir
$l.WindowStyle = 7
$l.IconLocation = "$InstallDir\icon.ico"
$l.Description = 'クイック翻訳 (Alt+Q / Ctrl+Shift+S)'
$l.Save()

# ---- 5) スタートアップ登録 ----
Write-Step "スタートアップに登録"
$startup = [Environment]::GetFolderPath('Startup')
$lnkS = Join-Path $startup 'QuickTranslate.lnk'
$s = $ws.CreateShortcut($lnkS)
$s.TargetPath = $pyw
$s.Arguments = "`"$InstallDir\main.py`""
$s.WorkingDirectory = $InstallDir
$s.WindowStyle = 7
$s.IconLocation = "$InstallDir\icon.ico"
$s.Save()

# ---- 6) 既存プロセスを止めて起動 ----
Write-Step "アプリを起動"
Get-Process -Name pythonw* -ErrorAction SilentlyContinue | Where-Object {
  $_.Path -eq $pyw
} | ForEach-Object {
  try { $_.CloseMainWindow() | Out-Null } catch {}
}
Start-Sleep -Milliseconds 600
Start-Process -FilePath $pyw -ArgumentList "`"$InstallDir\main.py`"" -WindowStyle Hidden

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host " インストール完了" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host " 場所       : $InstallDir"
Write-Host " ホットキー : Alt+Q (テキスト翻訳) / Ctrl+Shift+S (スクショ翻訳)"
Write-Host " 設定変更   : システムトレイの『訳』アイコンを右クリック"
Write-Host " 再起動後も: スタートアップ登録済み"
Write-Host ""
