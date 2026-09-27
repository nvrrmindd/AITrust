"""Outbound HTTP with SSRF protection.

We fetch URLs that come from untrusted text, so every hop (including redirects) is resolved and
rejected if it points to a private, loopback, link-local or otherwise internal address.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

from .config import settings

MAX_BYTES = 6_000_000
MAX_REDIRECTS = 5

_client: Optional[httpx.AsyncClient] = None
_sem = asyncio.Semaphore(12)


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout, connect=6.0),
            follow_redirects=False,
            headers={
                "User-Agent": f"Mozilla/5.0 (compatible; {settings.user_agent})",
                "Accept-Language": "ru,en;q=0.8",
            },
        )
    return _client


class BlockedURL(Exception):
    pass


class DNSFailure(Exception):
    pass


def _is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (
        addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast
        or addr.is_reserved or addr.is_unspecified
        or (addr.version == 6 and addr.ipv4_mapped and not _is_public(str(addr.ipv4_mapped)))
    )


async def assert_public(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise BlockedURL(f"unsupported url: {url}")
    host = p.hostname
    try:
        ipaddress.ip_address(host)
        ips = [host]
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise DNSFailure(host) from e
        ips = list({i[4][0] for i in infos})
    if not ips or not all(_is_public(ip) for ip in ips):
        raise BlockedURL(f"non-public address for {host}")


@dataclass
class FetchResult:
    url: str
    status: int
    content_type: str
    body: bytes


async def safe_get(url: str, *, check_ssrf: bool = True, headers: Optional[dict] = None) -> FetchResult:
    """GET with manual redirect handling so each hop is SSRF-checked. Hard wall-clock limit: httpx timeouts
    are per read, so a server trickling bytes could otherwise hold a check forever."""
    try:
        async with asyncio.timeout(settings.http_timeout * 3):
            return await _safe_get(url, check_ssrf=check_ssrf, headers=headers)
    except TimeoutError as e:
        raise httpx.ReadTimeout(f"too slow: {url}") from e


async def _safe_get(url: str, *, check_ssrf: bool, headers: Optional[dict]) -> FetchResult:
    current = url
    async with _sem:
        for _ in range(MAX_REDIRECTS + 1):
            if check_ssrf:
                await assert_public(current)
            async with client().stream("GET", current, headers=headers) as r:
                if r.status_code in (301, 302, 303, 307, 308) and "location" in r.headers:
                    current = urljoin(current, r.headers["location"])
                    continue
                chunks, size = [], 0
                async for part in r.aiter_bytes():
                    size += len(part)
                    if size > MAX_BYTES:
                        break
                    chunks.append(part)
                return FetchResult(str(r.url), r.status_code, r.headers.get("content-type", ""), b"".join(chunks))
        raise httpx.TooManyRedirects(f"too many redirects: {url}")


async def get_json(url: str, params: Optional[dict] = None) -> tuple[int, Optional[dict]]:
    """For well-known public APIs (Crossref, OpenAlex, doi.org, Wikipedia): no SSRF check needed."""
    if url.startswith("https://api.openalex.org"):
        params = {**(params or {}), "mailto": settings.contact_email}
        if settings.openalex_api_key:
            params["api_key"] = settings.openalex_api_key
    async with _sem:
        r = await client().get(url, params=params, headers={"Accept": "application/json"}, follow_redirects=True)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, None
