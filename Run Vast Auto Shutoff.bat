@echo off
echo Starting Vast Auto Shutoff...

:: Try different possible locations for the executable
if exist "clean_build\VastAutoShutoff\VastAutoShutoff.exe" (
    start "" "clean_build\VastAutoShutoff\VastAutoShutoff.exe"
) else if exist "VastAutoShutoff.exe" (
    start "" "VastAutoShutoff.exe"
) else if exist "monitor_process.exe" (
    :: In the distributed package
    start "" "VastAutoShutoff.exe"
) else (
    echo ERROR: Could not find VastAutoShutoff.exe
    echo Please make sure you extracted all files from the ZIP package.
    pause
) 