# Vast Auto Shutoff - Installation Guide

This guide will help you install and configure the Vast Auto Shutoff utility.

## Prerequisites

- **Windows**: The application is designed to run on Windows.

## Installation Options

### Option 1: Run from Pre-built Executable (Recommended for most users)

1. Download the latest release ZIP file from the releases section.
2. Extract the ZIP file to a location of your choice.
3. Run the application by double-clicking "Run Vast Auto Shutoff.bat"

### Option 2: Run from Source Code (For developers)

1. Clone or download the repository.
2. Create a virtual environment:
   ```
   python -m venv .venv
   ```
3. Activate the virtual environment:
   - Windows: `.venv\Scripts\activate`
4. Install the requirements:
   ```
   pip install -r requirements.txt
   ```
5. Run the application:
   ```
   python vast_auto_shutoff_gui.py
   ```

## First-Time Setup

1. After launching the application, go to the "Configuration" tab.
2. Enter your Vast.ai API key.
3. Set the processes to monitor (e.g., `skyrim.exe,skyrimvr.exe`).
4. Set the shutdown timeout in minutes.
5. Click "Save Configuration".

## How to Use

1. Go to the "Monitoring" tab.
2. Use the "Select Instance to Monitor" button to choose the Vast.ai instance you want to monitor.
3. Click "Start Monitoring" to begin monitoring the specified processes.
4. The utility will automatically shut down your instance if no monitored processes are running for the specified timeout period.

## Troubleshooting

- If monitoring doesn't start, verify that Python is installed and added to your PATH.
- Check the log tab for any error messages.
- Ensure you have entered a valid Vast.ai API key.
- Make sure you've selected an instance to monitor before starting.

## Upgrading

To upgrade to a newer version:

1. Download the latest release.
2. Extract it to a new location.
3. Copy your config.ini file from the old installation to the new one (if you want to keep your settings). 
