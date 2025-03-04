# Vast Auto Shutoff

A utility to automatically shut down your Vast.ai instances when specific processes are no longer running.

## Features

- Monitor specific processes on your Vast.ai instance
- Automatically shut down instances when processes are not running for a specified timeout
- Simple and intuitive GUI interface
- Real-time status updates
- Test countdown feature for verification
- Works with multiple Vast.ai instances

## Screenshots

(Add screenshots of your application here)

## Installation

### Option 1: Run from Pre-built Executable

1. Download the latest release from the [Releases](https://github.com/YourUsername/vast-auto-shutoff/releases) page
2. Extract the ZIP file to a location of your choice
3. **Important**: Make sure Python is installed on your system (see Prerequisites in INSTALL.md)
4. Run the application by double-clicking "Run Vast Auto Shutoff.bat"

### Option 2: Run from Source

1. Clone this repository
2. Create a virtual environment: `python -m venv .venv`
3. Activate the virtual environment:
   - Windows: `.venv\Scripts\activate`
4. Install the requirements: `pip install -r requirements.txt`
5. Run the application: `python vast_auto_shutoff_gui.py`

## Usage

1. Enter your Vast.ai API key in the Configuration tab
2. Specify the processes to monitor (e.g., `skyrimvr.exe,skyrim.exe`)
3. Set the shutdown timeout in minutes
4. Select an instance to monitor from the dropdown
5. Click "Start Monitoring"

See the [INSTALL.md](INSTALL.md) file for detailed installation and usage instructions.

## Building from Source

To build the executable yourself:

```
pip install pyinstaller
pyinstaller nowindow.spec -y
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 