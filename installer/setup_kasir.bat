@echo off
rem Setup CNdesktop portable (PC kasir): shortcut Startup + firewall TCP 8765.
rem Taruh file ini SEFOLDER dengan CNdesktop.exe, lalu double-click.
rem Butuh admin sekali (UAC) untuk shortcut semua-user + firewall rule.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Meminta hak admin...
    powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

set EXE=%~dp0CNdesktop.exe
if not exist "%EXE%" (
    echo GAGAL: CNdesktop.exe tidak ketemu sefolder dengan script ini.
    pause
    exit /b 1
)

powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\CNdesktop.lnk');$s.TargetPath='%EXE%';$s.WorkingDirectory='%~dp0';$s.Save()"
netsh advfirewall firewall add rule name="CNdesktop" dir=in action=allow program="%EXE%" protocol=TCP localport=8765 profile=private

echo.
echo Selesai. Jalankan CNdesktop.exe sekali, cek tray-icon muncul.
pause
