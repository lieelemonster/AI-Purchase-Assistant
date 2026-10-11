import asyncio

import pytest

from app.adapters.pages.url_safety import UnsafeUrlError, check_url

FAKE_DNS = {
    "www.apple.com.cn": ["17.253.144.10"],
    "evil-to-localhost.example": ["127.0.0.1"],
    "mixed.example": ["93.184.216.34", "10.0.0.8"],
}


async def fake_resolve(host):
    if host not in FAKE_DNS:
        raise OSError("not found")
    return FAKE_DNS[host]


def check(url):
    asyncio.run(check_url(url, resolve=fake_resolve))


@pytest.mark.parametrize(
    "url, reason",
    [
        ("http://127.0.0.1", "non_public_address"),
        ("http://localhost", "local_host"),
        ("http://10.0.0.5", "non_public_address"),
        ("http://192.168.1.1", "non_public_address"),
        ("http://169.254.169.254/latest/meta-data", "non_public_address"),
        ("http://[::1]", "non_public_address"),
        ("http://[::ffff:127.0.0.1]", "non_public_address"),
        ("file:///etc/passwd", "unsupported_scheme"),
        ("ftp://example.com", "unsupported_scheme"),
        ("http://evil-to-localhost.example", "non_public_address"),
        ("http://mixed.example", "non_public_address"),
        ("https://no-such-host.example", "dns_failed"),
    ],
)
def test_unsafe_urls_are_rejected(url, reason):
    with pytest.raises(UnsafeUrlError) as e:
        check(url)
    assert e.value.reason == reason


def test_public_official_site_is_allowed():
    check("https://www.apple.com.cn/")
