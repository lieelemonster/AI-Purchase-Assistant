import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional, Tuple
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OFFICIAL_CHANNELS_FILE = Path(__file__).resolve().parents[2] / "config" / "official_channels.json"

ChannelType = Literal["official", "jd", "tmall"]

JD_ITEM_HOSTS = {"item.jd.com", "item.m.jd.com"}
TMALL_ITEM_HOSTS = {"detail.tmall.com", "detail.m.tmall.com"}
JD_SHOP_PAGE = re.compile(r"^/(?:index|shoplevel|introduction)-(\d+)\.html$")


def _normalize_name(name: str) -> str:
    return "".join(name.split()).lower()


def _normalize_prefix(prefix: str) -> str:
    if not (prefix.startswith("/") and prefix.endswith("/")):
        raise ValueError(f"路径前缀必须以 / 开头和结尾：{prefix}")
    return prefix.lower()


def _split(url: str) -> Optional[Tuple[str, str]]:
    """返回 (主机名, 以 / 结尾的小写路径)；非 http/https 返回 None。支持 //host/path 形式的链接。"""
    parts = urlsplit(url if not url.startswith("//") else "https:" + url)
    if parts.scheme.lower() not in ("http", "https"):
        return None
    host = (parts.hostname or "").rstrip(".").lower()
    path = (parts.path or "/").lower()
    return host, path if path.endswith("/") else path + "/"


def _on_host(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


class OfficialChannel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ChannelType
    domain: Optional[str] = Field(default=None, pattern=r"^[a-z0-9.-]+\.[a-z]{2,}$")
    path_prefix: Optional[str] = None
    exclude_path_prefixes: List[str] = []
    store_host: Optional[str] = Field(default=None, pattern=r"^[a-z0-9-]+\.(jd|tmall)\.com$")
    shop_id: Optional[str] = Field(default=None, pattern=r"^\d+$")

    @field_validator("path_prefix")
    @classmethod
    def check_prefix(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _normalize_prefix(value)

    @field_validator("exclude_path_prefixes")
    @classmethod
    def check_excludes(cls, values: List[str]) -> List[str]:
        return [_normalize_prefix(v) for v in values]

    @model_validator(mode="after")
    def fields_match_type(self):
        if self.type == "official":
            if not self.domain or self.store_host or self.shop_id:
                raise ValueError("官网渠道只能填写 domain")
        else:
            if self.domain or self.path_prefix or self.exclude_path_prefixes:
                raise ValueError("电商渠道不能填写 domain 或路径")
            if (self.store_host is None) == (self.shop_id is None):
                raise ValueError("电商渠道必须且只能填写 store_host 或 shop_id 之一")
            if self.shop_id and self.type != "jd":
                raise ValueError("shop_id 只用于京东店铺")
            if self.store_host and not self.store_host.endswith(f".{self.type}.com"):
                raise ValueError(f"store_host 与渠道类型不符：{self.store_host}")
        return self

    def owns_page(self, host: str, path: str) -> bool:
        """URL 本身就属于这个渠道（官网页面或店铺自己的页面）。"""
        if self.type == "official":
            if not _on_host(host, self.domain):
                return False
            if self.path_prefix and not path.startswith(self.path_prefix):
                return False
            return not any(path.startswith(p) for p in self.exclude_path_prefixes)
        if self.store_host:
            return _on_host(host, self.store_host)
        match = JD_SHOP_PAGE.match(path.rstrip("/"))
        return host == "mall.jd.com" and match is not None and match.group(1) == self.shop_id


class OfficialBrand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    names: List[str] = Field(min_length=1)
    channels: List[OfficialChannel] = Field(min_length=1)


class OfficialChannels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = ""
    channel_priority: Dict[ChannelType, int]
    brands: List[OfficialBrand]

    @model_validator(mode="after")
    def names_are_unique(self):
        seen: Dict[str, str] = {}
        for brand in self.brands:
            for name in brand.names:
                key = _normalize_name(name)
                if key in seen and seen[key] != brand.id:
                    raise ValueError(f"品牌名 {name} 同时属于 {seen[key]} 和 {brand.id}")
                seen[key] = brand.id
        return self


class ChannelCheck(BaseModel):
    """status=store_check_required 表示这是京东/天猫商品详情页，还需在页面里找到指向官方店铺的链接才算官方。"""

    status: Literal["official", "store_check_required", "unknown"]
    brand_id: Optional[str] = None
    channel: Optional[ChannelType] = None
    priority: Optional[int] = None
    store_channels: List[OfficialChannel] = []


@lru_cache(maxsize=1)
def load_official_channels() -> OfficialChannels:
    return OfficialChannels.model_validate(json.loads(OFFICIAL_CHANNELS_FILE.read_text(encoding="utf-8")))


def find_brand(brand_hint: str) -> Optional[OfficialBrand]:
    key = _normalize_name(brand_hint)
    for brand in load_official_channels().brands:
        if key in (_normalize_name(n) for n in brand.names):
            return brand
    return None


def check_channel(url: str, brand_hint: str) -> ChannelCheck:
    """判断 URL 是否属于该品牌在中国大陆的官方渠道；多个渠道都匹配时取优先级最高（数字最小）的。"""
    brand = find_brand(brand_hint)
    split = _split(url)
    if brand is None or split is None:
        return ChannelCheck(status="unknown")
    host, path = split
    priority = load_official_channels().channel_priority

    owned = sorted((c for c in brand.channels if c.owns_page(host, path)), key=lambda c: priority[c.type])
    if owned:
        best = owned[0]
        return ChannelCheck(status="official", brand_id=brand.id, channel=best.type, priority=priority[best.type])

    platform: Optional[ChannelType] = "jd" if host in JD_ITEM_HOSTS else "tmall" if host in TMALL_ITEM_HOSTS else None
    stores = [c for c in brand.channels if c.type == platform]
    if platform and stores:
        return ChannelCheck(status="store_check_required", brand_id=brand.id, channel=platform,
                            priority=priority[platform], store_channels=stores)
    return ChannelCheck(status="unknown")


def links_confirm_store(links: Iterable[str], check: ChannelCheck) -> bool:
    """商品详情页中是否有链接指向该品牌的官方店铺。"""
    for link in links:
        split = _split(link)
        if split and any(store.owns_page(*split) for store in check.store_channels):
            return True
    return False
