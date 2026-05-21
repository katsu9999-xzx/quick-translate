@echo off
REM クイック翻訳 管理者権限で起動
REM (タスクマネージャ等の管理者権限アプリ上でホットキーを使う場合のみ使用)
cd /d "%~dp0"

set "PYW=%LOCALAPPDATA%\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\pythonw.exe"
if not exist "%PYW%" (
  for %%P in (pythonw.exe) do set "PYW=%%~$PATH:P"
)
if not exist "%PYW%" (
  echo pythonw.exe が見つかりません。
  pause
  exit /b 1
)

powershell -Command "Start-Process -FilePath '%PYW%' -ArgumentList '%~dp0main.py' -Verb RunAs -WindowStyle Hidden"
