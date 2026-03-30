@echo off
title Chamber Live Monitor - Team Edition

:: Get current IP automatically every time
for /f "tokens=*" %%i in ('C:\Users\1000333409\AppData\Local\Programs\Python\Python314\python.exe -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));print(s.getsockname()[0]);s.close()"') do set MY_IP=%%i
for /f "tokens=*" %%h in ('hostname') do set MY_HOST=%%h

echo.
echo  =========================================================
echo   CHAMBER LIVE MONITOR  ^|  Mochi WS-02A  ^|  Team Edition
echo  =========================================================
echo.
echo   LOCAL     ^>  http://localhost:5050
echo.
echo   PERMANENT ^>  http://%MY_HOST%:5050
echo              ^^ SAVE THIS - works every day, never changes
echo.
echo   TODAY IP  ^>  http://%MY_IP%:5050
echo              ^^ changes daily, use hostname above instead
echo.
echo  =========================================================
echo   Press Ctrl+C to stop the server
echo  =========================================================
echo.

:: Open browser automatically after 2s
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:5050"

C:\Users\1000333409\AppData\Local\Programs\Python\Python314\python.exe "%~dp0app.py"
pause
