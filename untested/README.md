# MediaFire Downloader - Enterprise Grade Edition

A production-ready, enterprise-grade MediaFire downloader with advanced features for professional use.

## New Features (v2.0)

### External Configuration
- YAML-based configuration file (`~/.mediafire-py.yaml`)
- Easy proxy management without code modification
- CLI argument overrides for all settings

### Structured Logging
- JSON-formatted logs for easy parsing
- Configurable log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Optional file logging with rotation support
- Color-coded console output

### Enhanced CLI
- Comprehensive command-line interface with argparse
- `--init-config` to create default configuration
- `--show-config` to display current settings
- Override any config option via CLI arguments

### ✅ Metrics & Observability
- Real-time download statistics
- Success/failure tracking with error codes
- Speed calculations and time estimates
- Detailed error reporting by error type

### Robust Error Handling
- Specific error codes for different failure types
- Structured error tracking and reporting
- Better error messages for troubleshooting

## 📋 Requirements

Install dependencies:

```bash
pip install aiohttp beautifulsoup4 rich pyyaml
```

## 🔧 Quick Start

### 1. Initialize Configuration

Create your configuration file:

```bash
python app.py --init-config
```

This creates `~/.mediafire-py.yaml` with default settings.

### 2. Configure Proxies (Optional)

Edit `~/.mediafire-py.yaml`:

```yaml
proxies:
  - "http://proxy1.example.com:8080"
  - "socks5://proxy2.example.com:1080"

proxy_downloads: true
max_workers: 15
```

### 3. Download Files

```bash
# Simple download
python app.py https://www.mediafire.com/file/abc123/file.zip

# Custom output directory
python app.py https://www.mediafire.com/folder/xyz789 --output-dir ./downloads

# Override workers and rate limit
python app.py <url> --max-workers 20 --rate-limit 10

# Enable debug logging
python app.py <url> --log-level DEBUG --log-file ./download.log
```

## Advanced Usage

### View Current Configuration

```bash
python app.py --show-config
```

### Custom Configuration File

```bash
python app.py <url> --config-file /path/to/custom-config.yaml
```

### Enable File Logging

```bash
python app.py <url> --log-file ./mediafire-download.log
```

### Maximum Performance

```bash
python app.py <url> \
  --max-workers 25 \
  --rate-limit 15 \
  --output-dir /fast/ssd/downloads
```

## Proxy Configuration

### Supported Proxy Types
- HTTP: `http://proxy.example.com:8080`
- HTTPS: `https://proxy.example.com:8080`
- SOCKS5: `socks5://proxy.example.com:1080`
- Authenticated: `http://user:pass@proxy.example.com:8080`

### Proxy Behavior
- **API Requests**: Always use proxies if configured
- **Downloads**: Controlled by `proxy_downloads` setting
- **Rotation**: Automatic random selection per request
- **Fallback**: Direct connection if all proxies fail

## Metrics Display

After completion, you'll see:

```
┌──────────────── Download Metrics ─────────────────┐
│ Metric          │ Value                            │
├─────────────────┼──────────────────────────────────┤
│ Total Files     │ 42                               │
│ Successful      │ 40                               │
│ Failed          │ 2                                │
│ Total Data      │ 1,234.56 MB                      │
│ Elapsed Time    │ 125.34s                          │
│ Avg Speed       │ 9.85 MB/s                        │
│                 │                                  │
│ Errors by Code  │                                  │
│   RATE_LIMITED  │ 1                                │
│   NETWORK_ERROR │ 1                                │
└─────────────────┴──────────────────────────────────┘
```

## Error Codes

| Code | Name | Description |
|------|------|-------------|
| 0 | SUCCESS | Operation completed successfully |
| 1 | INVALID_URL | Invalid MediaFire URL provided |
| 2 | DOWNLOAD_FAILED | File download failed |
| 3 | RATE_LIMITED | Rate limited by server |
| 4 | NETWORK_ERROR | Network connectivity issue |
| 5 | HASH_MISMATCH | SHA256 verification failed |
| 6 | CONFIG_ERROR | Configuration file error |
| 7 | API_ERROR | MediaFire API error |

## 🏗️ Architecture Improvements

### Design Patterns

1. **Configuration Management**
   - External YAML configuration
   - Environment-agnostic settings
   - Runtime override capability

2. **Observability**
   - Structured logging with JSON output
   - Comprehensive metrics tracking
   - Error classification and reporting

3. **Reliability**
   - Specific error codes for debugging
   - Enhanced retry logic with backoff
   - Graceful degradation

4. **Maintainability**
   - Dataclass-based configuration
   - Type hints throughout
   - Clear separation of concerns

5. **Extensibility**
   - Pluggable logging backends
   - Configurable retry strategies
   - Modular architecture

## 🔍 Troubleshooting

### Enable Debug Logging

```bash
python app.py <url> --log-level DEBUG --log-file debug.log
```

### Check Configuration

```bash
python app.py --show-config
```

### Common Issues

**Rate Limiting**
- Reduce `rate_limit` in config
- Add more proxies
- Increase `retry_base_delay`

**Network Errors**
- Check proxy configuration
- Increase `timeout` setting
- Verify network connectivity

**Hash Mismatches**
- Re-download affected files
- Check disk space
- Verify proxy reliability

## 📝 Configuration Reference

```yaml
# Worker Configuration
max_workers: 10           # Concurrent downloads
rate_limit: 5             # API requests per second

# Proxy Configuration
proxies: []               # List of proxy URLs
proxy_downloads: false    # Use proxies for downloads

# Retry Configuration
retry_attempts: 4         # Number of retry attempts
retry_base_delay: 1.0     # Initial retry delay (seconds)

# Performance Configuration
chunk_size: 65536         # Download chunk size (bytes)
timeout: 300              # HTTP timeout (seconds)

# Output Configuration
output_dir: "."           # Default output directory

# Logging Configuration
log_level: "INFO"         # DEBUG|INFO|WARNING|ERROR|CRITICAL
log_file: null            # Optional log file path
```

