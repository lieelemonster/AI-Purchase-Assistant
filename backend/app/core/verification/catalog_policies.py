import re
from typing import List, Literal, Set, Tuple

from app.adapters.model.base import ModelGateway
from app.core.verification.budget import SearchBudget
from app.core.verification.catalog_match import CatalogLike, CatalogMatch, match_candidates
from app.schemas.candidate import Candidate
from app.schemas.need import NeedProfile

RESULT_SIZE = 3
# 这些原因说明换个更宽的关键词可能找到；停产、品类不符、搜索失败、达到搜索上限不补查。
RETRYABLE_REASONS = {"not_in_catalog", "choice_not_in_results"}


def broader_keyword(candidate: Candidate) -> str:
    """D-02 补查用的关键词：只保留品牌和型号，去掉代际和配置。"""
    return f"{candidate.brand_hint} {candidate.model_hint}".strip()


def base_model(name: str) -> str:
    """配置名称去掉括号里的配置部分，例如“华为 MateBook 14 鸿蒙版(32GB/1TB)”→“华为matebook14鸿蒙版”。"""
    return "".join(re.split(r"[（(]", name, maxsplit=1)[0].split()).lower()


async def match_with_retry(
    candidates: List[Candidate],
    need: NeedProfile,
    model: ModelGateway,
    catalog: CatalogLike,
    budget: SearchBudget,
) -> List[CatalogMatch]:
    """D-02：第一次没在产品库里找到的候选，用更宽的关键词补查 1 次，补查同样计入搜索次数。"""
    matches = await match_candidates(candidates, need, model, catalog, budget)
    retry = [
        c for c, m in zip(candidates, matches)
        if m.status == "unknown" and m.reason in RETRYABLE_REASONS and broader_keyword(c) != m.keyword
    ]
    if not retry:
        return matches
    retried = await match_candidates(retry, need, model, catalog, budget,
                                     keyword_overrides={c.candidate_id: broader_keyword(c) for c in retry})
    by_id = {m.candidate_id: m for m in retried}
    return [by_id.get(m.candidate_id, m) for m in matches]


def dedupe_same_model(matches: List[CatalogMatch]) -> List[CatalogMatch]:
    """D-03：同一型号的不同配置只占一个名额，保留排在前面的候选。"""
    seen: Set[str] = set()
    result = []
    for match in matches:
        if match.status == "matched" and match.hit is not None:
            key = base_model(match.hit.name)
            if key in seen:
                match = match.model_copy(update={"status": "unknown", "reason": "same_model_duplicate", "hit": None})
            else:
                seen.add(key)
        result.append(match)
    return result


def discover_candidates(
    candidates: List[Candidate],
    matches: List[CatalogMatch],
    needed: int = RESULT_SIZE,
) -> Tuple[List[Candidate], List[CatalogMatch]]:
    """D-03：有效候选不足时，可以从检索结果里新发现的其他型号补足，来源标为“检索中发现”。

    新候选同样要经过后续的读取、身份和停产核对；补完仍不足时不虚构。
    """
    matched = [m for m in matches if m.status == "matched" and m.hit is not None]
    if len(matched) >= needed:
        return [], []
    taken = {base_model(m.hit.name) for m in matched}
    brands = {c.candidate_id: c.brand_hint for c in candidates}
    next_number = max(int(c.candidate_id[1:]) for c in candidates) + 1 if candidates else 1

    new_candidates: List[Candidate] = []
    new_matches: List[CatalogMatch] = []
    for match in matches:
        for hit in match.alternatives:
            if len(matched) + len(new_matches) >= needed:
                return new_candidates, new_matches
            key = base_model(hit.name)
            if key in taken or hit.discontinued:
                continue
            taken.add(key)
            candidate_id = f"c{next_number}"
            next_number += 1
            new_candidates.append(Candidate(candidate_id=candidate_id, brand_hint=brands[match.candidate_id],
                                            model_hint=hit.name, origin="search_discovered"))
            new_matches.append(CatalogMatch(candidate_id=candidate_id, status="matched", keyword=match.keyword, hit=hit))
    return new_candidates, new_matches


def result_status(valid_count: int) -> Literal["success", "insufficient_candidates"]:
    """D-02：有效候选不足三款时有几款给几款，并说明原因；不虚构。"""
    return "success" if valid_count >= RESULT_SIZE else "insufficient_candidates"
