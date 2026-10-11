from typing import Any, Dict, Iterable, List, Set

DATA_KEY = "data"


def build_model_prompt(instructions: str, page_text: str) -> Dict[str, Any]:
    """网页正文只放在数据区，不能写进任务说明。"""
    return {"instructions": instructions, "data": {"page_text": page_text}}


def keep_known_candidates(proposed_ids: Iterable[str], allowed_ids: Iterable[str]) -> List[str]:
    allowed: Set[str] = set(allowed_ids)
    return [candidate_id for candidate_id in proposed_ids if candidate_id in allowed]


def page_links_are_not_fetched(links: Iterable[str]) -> List[str]:
    """页面里的链接只作为文字保存，不会据此再去访问。"""
    return []
