from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Union

from app.adapters.search.base import SearchGateway, SearchGatewayError, SearchHit

ScriptedResult = Union[Sequence[SearchHit], SearchGatewayError]
Responder = Callable[[str, Optional[List[str]]], ScriptedResult]


class FakeSearchGateway(SearchGateway):
    """按查询词（或自定义函数）返回预设结果的模拟搜索，供测试使用。未预设的查询返回空列表。"""

    def __init__(self, responses: Optional[Mapping[str, ScriptedResult]] = None, responder: Optional[Responder] = None):
        self._responses = dict(responses or {})
        self._responder = responder
        self.calls: List[Dict[str, Any]] = []

    async def search(
        self,
        query: str,
        *,
        region: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 10,
        include_sites: Optional[List[str]] = None,
    ) -> List[SearchHit]:
        self.calls.append({"query": query, "region": region, "language": language, "limit": limit,
                           "include_sites": include_sites})
        if self._responder is not None:
            result = self._responder(query, include_sites)
        else:
            result = self._responses.get(query, [])
        if isinstance(result, SearchGatewayError):
            raise result
        return list(result)[:limit]
