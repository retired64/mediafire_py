#!/usr/bin/env python3
"""
MediaFire Downloader - Enterprise Grade
- External YAML configuration
- Structured logging
- Enhanced CLI with argparse
- Metrics and observability
- Robust error handling with error codes
"""

from __future__ import annotations

import asyncio
import aiohttp
import hashlib
import random
import re
import sys
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import IntEnum

import yaml
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
)
from rich.live import Live
from rich.traceback import install
from rich.table import Table
import argparse

install()
console = Console()

# ==========================================================
# Error Codes
# ==========================================================
class ErrorCode(IntEnum):
    SUCCESS = 0
    INVALID_URL = 1
    DOWNLOAD_FAILED = 2
    RATE_LIMITED = 3
    NETWORK_ERROR = 4
    HASH_MISMATCH = 5
    CONFIG_ERROR = 6
    API_ERROR = 7

# ==========================================================
# Configuration
# ==========================================================
@dataclass
class Config:
    """Application configuration"""
    max_workers: int = 10
    rate_limit: int = 5
    proxies: List[str] = None
    proxy_downloads: bool = False
    retry_attempts: int = 4
    retry_base_delay: float = 1.0
    chunk_size: int = 65536
    timeout: int = 300
    output_dir: str = "."
    log_level: str = "INFO"
    log_file: Optional[str] = None
    
    def __post_init__(self):
        if self.proxies is None:
            self.proxies = []
    
    @classmethod
    def from_yaml(cls, path: Path) -> Config:
        """Load configuration from YAML file"""
        try:
            if not path.exists():
                return cls()
            
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            
            return cls(**data)
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to load config: {e}[/yellow]")
            return cls()
    
    def save_yaml(self, path: Path):
        """Save configuration to YAML file"""
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(asdict(self), f, default_flow_style=False)

    @classmethod
    def get_default_config_path(cls) -> Path:
        """Get default configuration file path"""
        home = Path.home()
        return home / ".mediafire-py.yaml"

# ==========================================================
# Structured Logger
# ==========================================================
class StructuredLogger:
    """Structured logging with JSON output support"""
    
    LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    
    def __init__(self, level: str = "INFO", log_file: Optional[Path] = None):
        self.level = self.LEVELS.get(level.upper(), 20)
        self.log_file = log_file
    
    def _log(self, level: str, message: str, **extra):
        if self.LEVELS[level] < self.level:
            return
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
            **extra
        }
        
        # Console output
        color_map = {
            "DEBUG": "dim",
            "INFO": "cyan",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold red"
        }
        console.print(f"[{color_map.get(level, 'white')}]{level}[/]: {message}")
        
        # File output
        if self.log_file:
            try:
                with self.log_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry) + "\n")
            except Exception:
                pass
    
    def debug(self, msg: str, **extra):
        self._log("DEBUG", msg, **extra)
    
    def info(self, msg: str, **extra):
        self._log("INFO", msg, **extra)
    
    def warning(self, msg: str, **extra):
        self._log("WARNING", msg, **extra)
    
    def error(self, msg: str, **extra):
        self._log("ERROR", msg, **extra)
    
    def critical(self, msg: str, **extra):
        self._log("CRITICAL", msg, **extra)

# Global logger instance
logger: StructuredLogger = None

# ==========================================================
# Metrics
# ==========================================================
@dataclass
class Metrics:
    """Download metrics and statistics"""
    start_time: float
    end_time: Optional[float] = None
    total_files: int = 0
    successful_downloads: int = 0
    failed_downloads: int = 0
    total_bytes: int = 0
    errors_by_code: Dict[ErrorCode, int] = None
    
    def __post_init__(self):
        if self.errors_by_code is None:
            self.errors_by_code = {}
    
    def record_error(self, code: ErrorCode):
        self.errors_by_code[code] = self.errors_by_code.get(code, 0) + 1
    
    def finish(self):
        self.end_time = time.time()
    
    def elapsed_time(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time
    
    def avg_speed(self) -> float:
        elapsed = self.elapsed_time()
        return self.total_bytes / elapsed if elapsed > 0 else 0
    
    def display(self):
        """Display metrics in a rich table"""
        table = Table(title="Download Metrics", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Total Files", str(self.total_files))
        table.add_row("Successful", str(self.successful_downloads))
        table.add_row("Failed", str(self.failed_downloads))
        table.add_row("Total Data", f"{self.total_bytes / (1024**2):.2f} MB")
        table.add_row("Elapsed Time", f"{self.elapsed_time():.2f}s")
        table.add_row("Avg Speed", f"{self.avg_speed() / (1024**2):.2f} MB/s")
        
        if self.errors_by_code:
            table.add_row("", "")
            table.add_row("[bold]Errors by Code[/bold]", "")
            for code, count in self.errors_by_code.items():
                table.add_row(f"  {code.name}", str(count))
        
        console.print(table)

# ==========================================================
# Regex MediaFire
# ==========================================================
MEDIAFIRE_RE = re.compile(
    r"https?://(?:www\.)?mediafire\.com/(file|file_premium|folder|download)/([A-Za-z0-9]+)",
    re.IGNORECASE,
)

# ==========================================================
# API URLs
# ==========================================================
API_INFO = "https://www.mediafire.com/api/1.5/folder/get_info.php"
API_CONTENT = "https://www.mediafire.com/api/1.5/folder/get_content.php"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept-Encoding": "gzip",
}

# ==========================================================
# Global State
# ==========================================================
TASK_QUEUE: asyncio.Queue["DownloadJob"] = asyncio.Queue()
SUCCESSFUL: List["DownloadJob"] = []
FAILED: List[tuple["DownloadJob", ErrorCode, str]] = []
METRICS: Metrics = None

# ==========================================================
# Models
# ==========================================================
@dataclass
class DownloadJob:
    url: str
    path: Path
    expected_hash: Optional[str]
    size: Optional[int] = None

# ==========================================================
# Exceptions
# ==========================================================
class MediaFireError(Exception):
    def __init__(self, message: str, code: ErrorCode = ErrorCode.API_ERROR):
        super().__init__(message)
        self.code = code

class InvalidURL(MediaFireError):
    def __init__(self, message: str):
        super().__init__(message, ErrorCode.INVALID_URL)

class DownloadFailed(MediaFireError):
    def __init__(self, message: str):
        super().__init__(message, ErrorCode.DOWNLOAD_FAILED)

class RateLimited(MediaFireError):
    def __init__(self):
        super().__init__("Rate limited by server", ErrorCode.RATE_LIMITED)

class HashMismatch(MediaFireError):
    def __init__(self):
        super().__init__("SHA256 hash mismatch", ErrorCode.HASH_MISMATCH)

# ==========================================================
# Retry helper
# ==========================================================
async def with_retry(
    func: Callable[[], Awaitable[Any]],
    retries: int = 4,
    base_delay: float = 1.0,
):
    for attempt in range(retries):
        try:
            return await func()
        except (aiohttp.ClientError, asyncio.TimeoutError, RateLimited) as e:
            if attempt == retries - 1:
                logger.error(f"Max retries exceeded", error=str(e), attempt=attempt)
                raise
            delay = base_delay * (2 ** attempt)
            logger.debug(f"Retry {attempt + 1}/{retries} after {delay}s", error=str(e))
            await asyncio.sleep(delay)

# ==========================================================
# MediaFire Client
# ==========================================================
class MediaFireClient:
    def __init__(self, config: Config):
        self.config = config
        self.api_client: Optional[aiohttp.ClientSession] = None
        self.download_client: Optional[aiohttp.ClientSession] = None
        self.rate_semaphore = asyncio.Semaphore(config.rate_limit)
        
        logger.info("MediaFire client initialized", 
                   max_workers=config.max_workers,
                   rate_limit=config.rate_limit,
                   proxies_count=len(config.proxies))

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        
        self.api_client = aiohttp.ClientSession(
            headers=HEADERS,
            timeout=timeout,
            connector=aiohttp.TCPConnector(limit=0),
        )
        self.download_client = aiohttp.ClientSession(
            headers=HEADERS,
            timeout=timeout,
            connector=aiohttp.TCPConnector(limit=0),
        )
        logger.debug("HTTP clients initialized")
        return self

    async def __aexit__(self, *_):
        if self.api_client:
            await self.api_client.close()
        if self.download_client:
            await self.download_client.close()
        logger.debug("HTTP clients closed")

    def _get_proxy_for_request(self, is_download: bool) -> Optional[str]:
        if not self.config.proxies:
            return None
        if is_download and not self.config.proxy_downloads:
            return None
        proxy = random.choice(self.config.proxies)
        logger.debug(f"Selected proxy", proxy=proxy, is_download=is_download)
        return proxy

    @staticmethod
    def parse_url(url: str) -> tuple[str, str]:
        m = MEDIAFIRE_RE.search(url)
        if not m:
            logger.error("Invalid MediaFire URL", url=url)
            raise InvalidURL(f"Invalid MediaFire URL: {url}")
        return m.group(1), m.group(2)

    @staticmethod
    def sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    async def api_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        assert self.api_client

        async def _call():
            async with self.rate_semaphore:
                proxy = self._get_proxy_for_request(False)
                async with self.api_client.get(
                    API_CONTENT,
                    params=params,
                    proxy=proxy,
                ) as r:
                    if r.status == 429:
                        raise RateLimited()
                    r.raise_for_status()
                    data = await r.json()
                    if data["response"]["result"] != "Success":
                        logger.error("API error", response=data)
                        raise MediaFireError(f"API error: {data}")
                    return data["response"]

        return await with_retry(_call, self.config.retry_attempts, self.config.retry_base_delay)

    async def get_folder_info(self, key: str) -> Dict[str, Any]:
        assert self.api_client

        async def _call():
            async with self.rate_semaphore:
                proxy = self._get_proxy_for_request(False)
                async with self.api_client.get(
                    API_INFO,
                    params={"response_format": "json", "folder_key": key},
                    proxy=proxy,
                ) as r:
                    if r.status == 429:
                        raise RateLimited()
                    r.raise_for_status()
                    return (await r.json())["response"]

        return await with_retry(_call, self.config.retry_attempts, self.config.retry_base_delay)

    async def resolve_file_metadata(self, url: str) -> tuple[str, str]:
        assert self.download_client
        proxy = self._get_proxy_for_request(True)

        async with self.download_client.get(url, proxy=proxy) as r:
            html = await r.text()

        soup = BeautifulSoup(html, "html.parser")
        btn = soup.find("a", id="downloadButton")
        
        if not btn or not btn.get("href"):
            logger.error("Download button not found", url=url)
            raise DownloadFailed("Download link not found")

        filename = None
        filename_div = soup.find("div", class_="filename")
        if filename_div:
            filename = filename_div.text.strip()

        if not filename:
            filename = btn["href"].split("/")[-1].split("?")[0]

        logger.info("File metadata resolved", filename=filename, url=btn["href"])
        return btn["href"], filename

    async def worker(self, progress: Progress, total_task_id: int):
        while True:
            job: DownloadJob = await TASK_QUEUE.get()
            try:
                await self.download_job(job, progress)
                SUCCESSFUL.append(job)
                METRICS.successful_downloads += 1
                if job.size:
                    METRICS.total_bytes += job.size
                logger.info("Download completed", file=job.path.name)
            except MediaFireError as e:
                FAILED.append((job, e.code, str(e)))
                METRICS.failed_downloads += 1
                METRICS.record_error(e.code)
                logger.error("Download failed", file=job.path.name, error=str(e), code=e.code.name)
            except Exception as e:
                FAILED.append((job, ErrorCode.DOWNLOAD_FAILED, str(e)))
                METRICS.failed_downloads += 1
                METRICS.record_error(ErrorCode.DOWNLOAD_FAILED)
                logger.error("Unexpected error", file=job.path.name, error=str(e))
            finally:
                progress.advance(total_task_id, 1)
                TASK_QUEUE.task_done()

    async def download_job(self, job: DownloadJob, progress: Progress):
        headers = {}
        start = 0

        if job.path.exists():
            start = job.path.stat().st_size
            headers["Range"] = f"bytes={start}-"
            logger.debug("Resuming download", file=job.path.name, start_byte=start)

        proxy = self._get_proxy_for_request(True)

        async def _call():
            async with self.download_client.get(
                job.url, headers=headers, proxy=proxy
            ) as r:
                if r.status == 429:
                    raise RateLimited()
                await self.stream(job, r, progress, start)

        await with_retry(_call, self.config.retry_attempts, self.config.retry_base_delay)

        if job.expected_hash:
            actual_hash = self.sha256(job.path)
            if actual_hash != job.expected_hash.lower():
                logger.error("Hash mismatch", 
                           file=job.path.name,
                           expected=job.expected_hash,
                           actual=actual_hash)
                raise HashMismatch()

    async def stream(self, job, r, progress, start):
        total = int(r.headers.get("Content-Length", 0)) + start
        task_id = progress.add_task(job.path.name, total=total)
        
        if not job.size and total > 0:
            job.size = total

        job.path.parent.mkdir(parents=True, exist_ok=True)

        with job.path.open("ab") as f:
            async for chunk in r.content.iter_chunked(self.config.chunk_size):
                f.write(chunk)
                progress.update(task_id, advance=len(chunk))

# ==========================================================
# Folder traversal
# ==========================================================
async def enqueue_folder(client: MediaFireClient, key: str, base: Path, chunk: int = 1):
    info = await client.get_folder_info(key)
    path = base / info["folder_info"]["name"]
    path.mkdir(parents=True, exist_ok=True)
    
    logger.info("Processing folder", folder=info["folder_info"]["name"], chunk=chunk)

    files = await client.api_get({
        "response_format": "json",
        "folder_key": key,
        "content_type": "files",
        "chunk": chunk,
    })

    file_list = files["folder_content"].get("files", []) or []
    for f in file_list:
        size = int(f.get("size", 0))
        await TASK_QUEUE.put(
            DownloadJob(
                f["links"]["normal_download"],
                path / f["filename"],
                f.get("hash"),
                size
            )
        )
        METRICS.total_files += 1

    folders = await client.api_get({
        "response_format": "json",
        "folder_key": key,
        "content_type": "folders",
        "chunk": chunk,
    })

    for d in folders["folder_content"].get("folders", []) or []:
        await enqueue_folder(client, d["folderkey"], path)

    if (files["folder_content"].get("more_chunks") == "yes" or
        folders["folder_content"].get("more_chunks") == "yes"):
        await enqueue_folder(client, key, base, chunk + 1)

# ==========================================================
# CLI
# ==========================================================
def parse_args():
    parser = argparse.ArgumentParser(
        description="MediaFire Downloader - Enterprise Grade",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://www.mediafire.com/file/abc123/file.zip
  %(prog)s https://www.mediafire.com/folder/xyz789 --output-dir ./downloads
  %(prog)s --init-config  # Create default config file
  %(prog)s --show-config  # Display current configuration
        """
    )
    
    parser.add_argument("url", nargs="?", help="MediaFire URL to download")
    parser.add_argument("-o", "--output-dir", help="Output directory (default: current dir)")
    parser.add_argument("-w", "--max-workers", type=int, help="Max concurrent downloads")
    parser.add_argument("-r", "--rate-limit", type=int, help="API rate limit")
    parser.add_argument("--config-file", help="Configuration file path")
    parser.add_argument("--init-config", action="store_true", help="Initialize default config file")
    parser.add_argument("--show-config", action="store_true", help="Show current configuration")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], 
                       help="Logging level")
    parser.add_argument("--log-file", help="Log file path")
    
    return parser.parse_args()

# ==========================================================
# Main
# ==========================================================
async def main():
    global logger, METRICS
    
    args = parse_args()
    
    # Load configuration
    config_path = Path(args.config_file) if args.config_file else Config.get_default_config_path()
    config = Config.from_yaml(config_path)
    
    # Handle --init-config
    if args.init_config:
        config.save_yaml(config_path)
        console.print(f"[green]✓[/green] Configuration file created: {config_path}")
        console.print("\nEdit this file to customize your settings (proxies, workers, etc.)")
        return ErrorCode.SUCCESS
    
    # Handle --show-config
    if args.show_config:
        table = Table(title=f"Configuration ({config_path})")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        
        for key, value in asdict(config).items():
            table.add_row(key, str(value))
        
        console.print(table)
        return ErrorCode.SUCCESS
    
    # CLI overrides
    if args.output_dir:
        config.output_dir = args.output_dir
    if args.max_workers:
        config.max_workers = args.max_workers
    if args.rate_limit:
        config.rate_limit = args.rate_limit
    if args.log_level:
        config.log_level = args.log_level
    if args.log_file:
        config.log_file = args.log_file
    
    # Initialize logger
    log_file = Path(config.log_file) if config.log_file else None
    logger = StructuredLogger(config.log_level, log_file)
    
    # Validate URL argument
    if not args.url:
        console.print("[red]Error:[/red] MediaFire URL is required")
        console.print("Use --help for usage information")
        return ErrorCode.INVALID_URL
    
    # Initialize metrics
    METRICS = Metrics(start_time=time.time())
    
    url = args.url
    output = Path(config.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    
    logger.info("Starting download", url=url, output_dir=str(output))

    progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    )

    total_task_id = progress.add_task("Total", total=0)

    try:
        with Live(progress, refresh_per_second=10):
            async with MediaFireClient(config) as client:
                kind, key = client.parse_url(url)

                # Start workers
                for _ in range(config.max_workers):
                    asyncio.create_task(client.worker(progress, total_task_id))

                # Enqueue jobs
                if kind == "folder":
                    await enqueue_folder(client, key, output)
                else:
                    real_url, filename = await client.resolve_file_metadata(url)
                    METRICS.total_files = 1
                    await TASK_QUEUE.put(DownloadJob(real_url, output / filename, None))

                progress.update(total_task_id, total=TASK_QUEUE.qsize())
                await TASK_QUEUE.join()

        METRICS.finish()
        
        # Display results
        console.print("\n" + "="*60)
        METRICS.display()
        
        if FAILED:
            console.print(f"\n[red]Failed downloads ({len(FAILED)}):[/red]")
            for job, code, error in FAILED[:10]:  # Show first 10
                console.print(f"  • {job.path.name}: [{code.name}] {error}")
            if len(FAILED) > 10:
                console.print(f"  ... and {len(FAILED) - 10} more")
        
        return ErrorCode.SUCCESS if not FAILED else ErrorCode.DOWNLOAD_FAILED
        
    except InvalidURL as e:
        logger.critical("Invalid URL", error=str(e))
        return e.code
    except Exception as e:
        logger.critical("Unexpected error", error=str(e))
        return ErrorCode.API_ERROR

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
