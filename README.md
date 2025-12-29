# mediafire_py

<p align="center">
  <img src="src/img/logo-mediafire-py.png" alt="MediaFire-py Logo">
</p>

mediafire_py is a command-line tool that downloads files and folders from MediaFire with enterprise-grade features including resume support, concurrent downloads, proxy rotation, and hash verification.

## Downloads

| OS | Arch | Link |
|-------------------|--------------|-------------------|
| Linux | x64 | [mediafire-py-linux-x64.zip](https://github.com/retired64/mediafire_py/releases/download/v1.0.0/mediafire-py-linux-x64.zip) |
| Linux | ARM64 | [linux-arm64.tar.gz](https://github.com/retired64/mediafire_py/releases/download/v1.0.0/linux-arm64.tar.gz) |
| Windows | x64 | [mediafire-py-windows-x64.zip](https://github.com/retired64/mediafire_py/releases/download/v1.0.0/mediafire-py-windows-x64.zip) |
| macOS | x64 | [macOS-app.zip](https://github.com/retired64/mediafire_py/releases/download/v1.0.0/macOS-app.zip) |

## Usage

### Using Pre-built Binaries

Download the appropriate binary for your system from the [Downloads](#downloads) section above.

**Linux/macOS:**
```bash
# Extract the archive
unzip mediafire-py-linux-x64.zip  # or tar -xzf linux-arm64.tar.gz

# Make executable
chmod +x mediafire-py

# Run
./mediafire-py <mediafire_url>
```

**Windows:**
```cmd
# Extract the zip file
# Run from Command Prompt or PowerShell
mediafire-py.exe <mediafire_url>
```

**Example:**
```bash
./mediafire-py https://www.mediafire.com/file/example/file.zip
```

The file will be downloaded to your current directory with progress indicators and speed information displayed in real-time.

---

## Features

* Asynchronous downloads powered by `asyncio` and `aiohttp`
* Full support for MediaFire files and folders
* Recursive folder traversal using the official MediaFire API
* Concurrent download workers with task queue
* Resume support via HTTP Range requests
* SHA256 hash verification
* Robust retry logic with exponential backoff
* Rate limiting to prevent API throttling
* Dual HTTP clients (API / downloads), mirroring the Rust architecture
* Per-request proxy support with optional proxy rotation
* Rich-based multi-progress UI for terminal usage
* Designed for Linux, macOS, Termux, and server environments

---

## Requirements

* Python **3.10+**
* pip packages:

  * `aiohttp`
  * `beautifulsoup4`
  * `rich`

Install dependencies:

```bash
pip install aiohttp beautifulsoup4 rich
```

---

## Installation

Clone the repository:

```bash
git clone https://github.com/retired64/mediafire_py.git
cd mediafire_py
```

Make the script executable (optional):

```bash
chmod +x app.py
```

---

## Basic Usage

### Download a single file

```bash
python app.py <mediafire_url>
```

The file will be downloaded into the current directory.

---

### Download an entire folder (recursive)

```bash
python app.py <https://www.mediafire.com/folder_url>
```

* Subfolders are downloaded recursively
* Original folder structure is preserved
* Downloads are processed concurrently

---

## Concurrency Model

* Downloads are handled by a global asynchronous task queue
* A configurable number of worker tasks process downloads concurrently
* Each worker:

  * Pulls a job from the queue
  * Resolves the real download URL if needed
  * Streams data to disk
  * Updates progress bars
  * Reports success or failure

This closely mirrors the worker-based architecture used in the original Rust implementation.

---

## Resume Support

If a partially downloaded file already exists:

* The downloader automatically sends an HTTP `Range` request
* Download resumes from the last written byte
* Progress bars correctly reflect resumed state
* Hash verification is performed after completion (if available)

No additional flags are required.

---

## Proxy Support

### Proxy List Configuration

You can provide a list of proxies directly in the code:

```python
MediaFireClient(
    proxies=[
        "http://proxy1:8080",
        "socks5://proxy2:1080",
    ],
    proxy_downloads=True
)
```

### Behavior

* Proxies are selected **per request**
* API requests and download requests are handled independently
* Optional proxy usage for downloads only
* Automatic proxy rotation via random selection
* Supports HTTP, HTTPS, and SOCKS proxies

This design provides more flexibility than static proxy assignment.

---

## Rate Limiting and Retries

* API calls are protected by a semaphore-based rate limiter
* HTTP 429 and transient network errors trigger retries
* Retries use exponential backoff
* Ensures stability on slow or restricted networks

---

## Progress Display

The terminal UI uses `rich` to provide:

* A global progress bar tracking total jobs
* Individual progress bars for each active download
* Live speed, remaining time, and byte counters
* Clean refresh without flicker

This is conceptually equivalent to Rust’s `indicatif::MultiProgress`.

---

## Error Handling

The downloader handles and reports:

* Invalid MediaFire URLs
* Missing or malformed download pages
* API failures
* Rate limiting responses
* Network timeouts
* Hash mismatches
* Partial or corrupted downloads

Failed jobs are tracked separately from successful ones.

---

## Project Structure

```
app.py
```

This is intentionally a single-file implementation to simplify distribution and usage.
The internal structure is modular and can be split into packages if needed.

---

## Design Goals

* Remain readable and maintainable
* Prefer correctness and resilience over micro-optimizations
* Be suitable for real-world usage, not just experimentation

---
## Disclaimer

This project is not affiliated with MediaFire.
It relies on publicly available APIs and standard HTTP behavior.
Use responsibly and respect MediaFire’s terms of service.
