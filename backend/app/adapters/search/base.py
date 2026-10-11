from abc import ABC, abstractmethod
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict

SearchErrorKind = Literal["timeout", "auth", "quota", "network", "invalid_response", "unknown"]


class SearchHit(BaseModel):
    """搜索结果只用来定位网页；摘要不能当作商品事实，必须读取网页后才能形成证据。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str
    title: str = ""
    snippet: str = ""


class SearchGatewayError(Exception):
    def __init__(self, kind: SearchErrorKind, message: str = ""):
        super().__init__(f"{kind}: {message}" if message else kind)
        self.kind = kind


class SearchGateway(ABC):
    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        region: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 10,
        include_sites: Optional[List[str]] = None,
    ) -> List[SearchHit]:
        """include_sites 为希望限定的站点；供应商不支持时可以忽略，调用方会再按官方渠道规则过滤。失败时抛出 SearchGatewayError。"""
