import asyncio
import ipaddress
import socket
from typing import Awaitable, Callable, List
from urllib.parse import urlsplit

Resolver = Callable[[str], Awaitable[List[str]]]

ALLOWED_SCHEMES = {"http", "https"}


class UnsafeUrlError(Exception):
    def __init__(self, reason: str, url: str):
        super().__init__(f"{reason}: {url}")
        self.reason = reason
        self.url = url


async def system_resolve(host: str) -> List[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def _is_public(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text.split("%", 1)[0])
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def check_url(url: str, resolve: Resolver = system_resolve) -> None:
    """只允许访问公网 http/https 地址；所有网页请求（含每次重定向）都必须先经过这里。"""
    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("unsupported_scheme", url)
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeUrlError("missing_host", url)
    if host == "localhost" or host.endswith(".localhost"):
        raise UnsafeUrlError("local_host", url)

    try:
        ips = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            ips = await resolve(host)
        except OSError as e:
            raise UnsafeUrlError("dns_failed", url) from e
        if not ips:
            raise UnsafeUrlError("dns_failed", url)

    if not all(_is_public(ip) for ip in ips):
        raise UnsafeUrlError("non_public_address", url)
