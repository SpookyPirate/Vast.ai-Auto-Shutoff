@echo off
echo Starting Vast.ai Auto Shutoff Monitor
echo Processes to monitor: %~1
echo Timeout: %~2 minutes
echo API Key: [HIDDEN]
echo Instance ID: %~4

:: Get the directory where the batch file is located
set "BATCH_DIR=%~dp0"

:: Check if the monitor_process.exe exists in the same directory
if exist "%BATCH_DIR%monitor_process.exe" (
    echo Running monitor_process.exe...
    start "" "%BATCH_DIR%monitor_process.exe" --processes "%~1" --timeout "%~2" --api_key "%~3" --label "%~4"
) else (
    echo ERROR: monitor_process.exe not found in %BATCH_DIR%
    echo This feature requires the monitor_process.exe to be in the same directory as this batch file.
    exit /b 1
)

echo Monitor process started successfully.
exit /b 0 