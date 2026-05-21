@echo off
REM クイック翻訳 起動スクリプト (黒い窓を出さず常駐)
cd /d "%~dp0"

REM pythonw.exe を探索 (1) ストア版 Python 3.13 → (2) PATH 上の pythonw
set "PYW=%LOCALAPPDATA%\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\pythonw.exe"
if not exist "%PYW%" (
  for %%P in (pythonw.exe) do set "PYW=%%~$PATH:P"
)
if not exist "%PYW%" (
  echo pythonw.exe が見つかりません。Python 3.13 をインストールしてください。
  pause
  exit /b 1
)

start "" /B "%PYW%" "%~dp0main.py"
