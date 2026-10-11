from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class RequestUsage:
    stages_ms: Dict[str, int] = field(default_factory=dict)
    model_calls: int = 0
    model_tokens: int = 0
    searches: int = 0
    pages_read: int = 0
    cache_hits: int = 0


_current: ContextVar[Optional[RequestUsage]] = ContextVar("request_usage", default=None)


def start_usage() -> RequestUsage:
    usage = RequestUsage()
    _current.set(usage)
    return usage


def current_usage() -> Optional[RequestUsage]:
    return _current.get()


def add_model_call() -> None:
    usage = _current.get()
    if usage is not None:
        usage.model_calls += 1


def add_model_tokens(tokens: int) -> None:
    usage = _current.get()
    if usage is not None:
        usage.model_tokens += tokens


def add_search() -> None:
    usage = _current.get()
    if usage is not None:
        usage.searches += 1


def add_page_read() -> None:
    usage = _current.get()
    if usage is not None:
        usage.pages_read += 1


def add_cache_hit() -> None:
    usage = _current.get()
    if usage is not None:
        usage.cache_hits += 1


def format_usage(usage: RequestUsage) -> str:
    stages = " ".join(f"{name}{elapsed}ms" for name, elapsed in usage.stages_ms.items())
    return (
        f"汇总 {stages} 模型调用={usage.model_calls} token={usage.model_tokens} "
        f"搜索={usage.searches} 读取页面={usage.pages_read} 缓存命中={usage.cache_hits}"
    )
