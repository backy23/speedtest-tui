# Speedtest CLI Custom

A Python-based command-line interface for testing internet speed using Ookla's Speedtest.net servers. This client provides advanced metrics often hidden in the standard web interface.

## Screenshots

![Server Selection](https://github.com/user-attachments/assets/1200757f-a133-4700-a303-644f455b1bb3)
*Server selection and ping test*

![Download Test](https://github.com/user-attachments/assets/1c61e38d-522d-4731-9e92-0e30df48bb8f)
*Download speed measurement*

## Features

- **Detailed Latency**: Measures jitter, packet loss, and provides a histogram of ping times using WebSocket protocol.
- **Loaded Latency (Bufferbloat)**: Measures ping during download and upload to detect bufferbloat.
- **Parallel Testing**: Uses multiple concurrent connections for download and upload with warm-up discard and IQM-based speed calculation.
- **Rich Interface**: Beautiful terminal dashboard using the `rich` library.
- **Test History**: Automatically saves results with sparkline trend charts (`--history`).
- **JSON Export**: Full data export for automation and logging.
- **CSV Logging**: Append results to a CSV file for long-term monitoring (`--csv`).

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

### Options

| Flag | Description |
|------|-------------|
| `--simple`, `-s` | Text-only output (no dashboard) |
| `--json`, `-j` | Output JSON data |
| `--output FILE`, `-o` | Save JSON to file |
| `--csv FILE` | Append result as CSV row |
| `--history` | Show past test results with sparkline trends |
| `--list-servers` | List available servers and exit |
| `--server ID` | Use a specific server by ID |
| `--ping-count N` | Number of ping samples (default: 10) |
| `--download-duration SECS` | Duration of download test (default: 10) |
| `--upload-duration SECS` | Duration of upload test (default: 10) |
| `--connections N` | Number of concurrent connections (default: 4) |

### Examples

```bash
# Simple text output
python speedtest.py --simple

# Save to JSON and CSV
python speedtest.py -o result.json --csv speedlog.csv

# View test history with trend charts
python speedtest.py --history

# Use a specific server with more pings
python speedtest.py --server 12345 --ping-count 20
```

## Running Tests

```bash
python -m unittest discover -s tests -v
```
