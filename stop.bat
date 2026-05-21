@echo off
REM クイック翻訳 強制終了
taskkill /F /FI "WINDOWTITLE eq Quick Translate*" >NUL 2>&1
wmic process where "name='pythonw.exe' and commandline like '%%quick-translate%%main.py%%'" delete >NUL 2>&1
echo Quick Translate を停止しました
timeout /t 2 >NUL
