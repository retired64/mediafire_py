#!/usr/bin/env python3
"""
- Compatible con Termux
- Retry + backoff
- Rate limiting
- Proxies por request
"""

from __future__ import annotations

import asyncio
import aiohttp
import hashlib
import random
import re
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Awaitable

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

install()
console = Console()

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
# Estado global
# ==========================================================
TASK_QUEUE: asyncio.Queue["DownloadJob"] = asyncio.Queue()
SUCCESSFUL: List["DownloadJob"] = []
FAILED: List["DownloadJob"] = []

# ==========================================================
# Modelos
# ==========================================================
class DownloadJob:
    def __init__(self, url: str, path: Path, expected_hash: Optional[str]):
        self.url = url
        self.path = path
        self.expected_hash = expected_hash


# ==========================================================
# Excepciones
# ==========================================================
class MediaFireError(Exception): ...
class InvalidURL(MediaFireError): ...
class DownloadFailed(MediaFireError): ...
class RateLimited(MediaFireError): ...


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
        except (aiohttp.ClientError, asyncio.TimeoutError, RateLimited):
            if attempt == retries - 1:
                raise
            await asyncio.sleep(base_delay * (2 ** attempt))


# ==========================================================
# MediaFire Client
# ==========================================================
class MediaFireClient:
    def __init__(
        self,
        max_workers: int = 10,
        proxies: Optional[List[str]] = None,
        proxy_downloads: bool = False,
        rate_limit: int = 5,
    ):
        self.max_workers = max_workers
        self.proxies = proxies or []
        self.proxy_downloads = proxy_downloads

        self.api_client: aiohttp.ClientSession | None = None
        self.download_client: aiohttp.ClientSession | None = None

        self.rate_semaphore = asyncio.Semaphore(rate_limit)

    # ------------------------------------------------------
    # Client sessions
    # ------------------------------------------------------
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=None)

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
        return self

    async def __aexit__(self, *_):
        if self.api_client:
            await self.api_client.close()
        if self.download_client:
            await self.download_client.close()

    # ------------------------------------------------------
    # Proxy selector
    # ------------------------------------------------------
    def _get_proxy_for_request(self, is_download: bool) -> Optional[str]:
        if not self.proxies:
            return None
        if is_download and not self.proxy_downloads:
            return None
        return random.choice(self.proxies)

    # ------------------------------------------------------
    # Utils
    # ------------------------------------------------------
    @staticmethod
    def parse_url(url: str) -> tuple[str, str]:
        m = MEDIAFIRE_RE.search(url)
        if not m:
            raise InvalidURL(f"Invalid MediaFire URL: {url}")
        return m.group(1), m.group(2)

    @staticmethod
    def sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    # ------------------------------------------------------
    # API
    # ------------------------------------------------------
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
                        raise MediaFireError(data)
                    return data["response"]

        return await with_retry(_call)

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

        return await with_retry(_call)

    # ------------------------------------------------------
    # Resolver metadata archivo (NORMAL + PREMIUM)
    # ------------------------------------------------------
    async def resolve_file_metadata(self, url: str) -> tuple[str, str]:
        assert self.download_client
        proxy = self._get_proxy_for_request(True)

        async with self.download_client.get(url, proxy=proxy) as r:
            html = await r.text()

        soup = BeautifulSoup(html, "html.parser")

        btn = soup.find("a", id="downloadButton")
        if not btn or not btn.get("href"):
            raise DownloadFailed("Download link not found")

        filename = None

        filename_div = soup.find("div", class_="filename")
        if filename_div:
            filename = filename_div.text.strip()

        if not filename:
            filename = btn["href"].split("/")[-1].split("?")[0]

        return btn["href"], filename

    # ------------------------------------------------------
    # Worker
    # ------------------------------------------------------
    async def worker(self, progress: Progress, total_task_id: int):
        while True:
            job: DownloadJob = await TASK_QUEUE.get()
            try:
                await self.download_job(job, progress)
                SUCCESSFUL.append(job)
            except Exception:
                FAILED.append(job)
            finally:
                progress.advance(total_task_id, 1)
                TASK_QUEUE.task_done()

    # ------------------------------------------------------
    # Download
    # ------------------------------------------------------
    async def download_job(self, job: DownloadJob, progress: Progress):
        headers = {}
        start = 0

        if job.path.exists():
            start = job.path.stat().st_size
            headers["Range"] = f"bytes={start}-"

        proxy = self._get_proxy_for_request(True)

        async def _call():
            async with self.download_client.get(
                job.url, headers=headers, proxy=proxy
            ) as r:
                if r.status == 429:
                    raise RateLimited()

                await self.stream(job, r, progress, start)

        await with_retry(_call)

        if job.expected_hash:
            if self.sha256(job.path) != job.expected_hash.lower():
                raise DownloadFailed("SHA256 mismatch")

    async def stream(self, job, r, progress, start):
        total = int(r.headers.get("Content-Length", 0)) + start
        task_id = progress.add_task(job.path.name, total=total)

        job.path.parent.mkdir(parents=True, exist_ok=True)

        with job.path.open("ab") as f:
            async for chunk in r.content.iter_chunked(65536):
                f.write(chunk)
                progress.update(task_id, advance=len(chunk))


# ==========================================================
# Folder traversal
# ==========================================================
async def enqueue_folder(client, key, base, chunk=1):
    info = await client.get_folder_info(key)
    path = base / info["folder_info"]["name"]
    path.mkdir(parents=True, exist_ok=True)

    files = await client.api_get(
        {
            "response_format": "json",
            "folder_key": key,
            "content_type": "files",
            "chunk": chunk,
        }
    )

    for f in files["folder_content"].get("files", []) or []:
        await TASK_QUEUE.put(
            DownloadJob(
                f["links"]["normal_download"],
                path / f["filename"],
                f.get("hash"),
            )
        )

    folders = await client.api_get(
        {
            "response_format": "json",
            "folder_key": key,
            "content_type": "folders",
            "chunk": chunk,
        }
    )

    for d in folders["folder_content"].get("folders", []) or []:
        await enqueue_folder(client, d["folderkey"], path)

    if (
        files["folder_content"].get("more_chunks") == "yes"
        or folders["folder_content"].get("more_chunks") == "yes"
    ):
        await enqueue_folder(client, key, base, chunk + 1)


# ==========================================================
# Main
# ==========================================================
async def main():
    if len(sys.argv) < 2:
        console.print("Usage: python app.py <mediafire_url>")
        return

    url = sys.argv[1]
    output = Path(".")

    progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    )

    total_task_id = progress.add_task("Total", total=0)

    with Live(progress, refresh_per_second=10):
        async with MediaFireClient(
            max_workers=10,
            proxies=[],           # ← agrega proxies si quieres
            proxy_downloads=True
        ) as client:

            kind, key = client.parse_url(url)

            for _ in range(client.max_workers):
                asyncio.create_task(client.worker(progress, total_task_id))

            if kind == "folder":
                await enqueue_folder(client, key, output)
            else:
                real_url, filename = await client.resolve_file_metadata(url)
                await TASK_QUEUE.put(
                    DownloadJob(
                        real_url,
                        output / filename,
                        None
                    )
                )

            progress.update(total_task_id, total=TASK_QUEUE.qsize())
            await TASK_QUEUE.join()

    console.print(
        f"Completed: {len(SUCCESSFUL)} successful / {len(FAILED)} failed"
    )


if __name__ == "__main__":
    asyncio.run(main())
