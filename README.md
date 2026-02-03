# Speedtest CLI Custom

A Python-based command-line interface for testing internet speed using Ookla's Speedtest.net servers. This client provides advanced metrics often hidden in the standard web interface.

## Screenshots

![Server Selection](https://github.com/user-attachments/assets/1200757f-a133-4700-a303-644f455b1bb3)
*Server selection and ping test*

![Download Test](https://github.com/user-attachments/assets/1c61e38d-522d-4731-9e92-0e30df48bb8f)
*Download speed measurement*

## Features

- **Detailed Latency**: Measures jitter and provides a histogram of ping times using WebSocket protocol.
- **Parallel Testing**: Uses multiple concurrent connections for download and upload synchronization.
- **Rich Interface**: Beautiful terminal dashboard using the `rich` library.
- **JSON Export**: Full data export for automation and logging.

## Installation

### Desktop / Server (Linux, macOS, Windows)

```bash
pip install -r requirements.txt
```

### Android (Termux)

Works perfectly on Android using Termux!

1. Install [Termux](https://termux.dev/en/)
2. Run these commands:
```bash
pkg update && pkg upgrade
pkg install python
pip install -r requirements.txt
```

## Usage

Run the speedtest:

```bash
python speedtest.py
```

Options:
- `--simple`: Text-only output (no dashboard)
- `--json`: Output JSON data
- `--output FILE`: Save JSON to file
- `--ping-count N`: Number of ping samples
- `--download-duration SECS`: Duration of download test
- `--upload-duration SECS`: Duration of upload test
