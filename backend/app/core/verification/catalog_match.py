from typing import Dict, List, Literal, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.catalog.pconline import CATEGORY_DIRS, CatalogHit, CatalogSearchError
from app.adapters.model.base import ModelGateway
from app.core.verification.budget import SearchBudget
from app.schemas.candidate import Candidate
from app.schemas.need import NeedProfile

KEYWORD_TASK = (
    "为每个候选产品写一条太平洋电脑网产品库的站内搜索关键词，用来找到这个型号的各个配置。要求：\n"
    "1. 不超过 20 个字，只写品牌和型号（必要时加代际或年份），例如“华为MateBook 14”“苹果iPad Air”；\n"
    "2. 不写内存、存储等配置，不写价格、颜色和评价性词语。"
)
SELECT_TASK = (
    "下面是每个候选产品在太平洋电脑网产品库的搜索结果。请为每个候选选出最符合候选型号和配置线索的一条结果，"
    "填写它的 product_id；没有任何一条对应这个候选时，product_id 填 null。只能从该候选自己的结果里选。"
)


class CatalogLike(Protocol):
    async def search(self, keyword: str) -> List[CatalogHit]: ...


class CatalogMatch(BaseModel):
    candidate_id: str
    status: Literal["matched", "unknown"]
    reason: Optional[str] = None
    keyword: str = ""
    hit: Optional[CatalogHit] = None
    alternatives: List[CatalogHit] = []


class _Keyword(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    keyword: str = Field(min_length=1)


class _Keywords(BaseModel):
    model_config = ConfigDict(extra="ignore")

    keywords: List[_Keyword] = []


class _Choice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    product_id: Optional[str] = None


class _Choices(BaseModel):
    model_config = ConfigDict(extra="ignore")

    choices: List[_Choice] = []


def _fallback_keyword(candidate: Candidate) -> str:
    return " ".join(p for p in (candidate.brand_hint, candidate.model_hint, candidate.generation_hint) if p)


async def match_candidates(
    candidates: List[Candidate],
    need: NeedProfile,
    model: ModelGateway,
    catalog: CatalogLike,
    budget: SearchBudget,
    keyword_overrides: Optional[Dict[str, str]] = None,
) -> List[CatalogMatch]:
    """关键词和“哪条结果对应候选”交给模型；程序只把未停产、品类一致的结果交给模型选，并核对所选编号。

    传入 keyword_overrides 时（如补查）直接使用这些关键词，不再请模型写。
    """
    if keyword_overrides is None:
        written = await model.generate_json(
            task=KEYWORD_TASK,
            payload={"category_id": need.category_id, "candidates": [c.model_dump() for c in candidates]},
            output_schema=_Keywords,
        )
        keywords = {k.candidate_id: k.keyword.strip() for k in written.keywords}
    else:
        keywords = keyword_overrides
    allowed_dirs = set(CATEGORY_DIRS[need.category_id])

    matches: Dict[str, CatalogMatch] = {}
    offered: Dict[str, Dict[str, CatalogHit]] = {}
    excluded: Dict[str, Dict[str, str]] = {}
    for candidate in candidates:
        keyword = keywords.get(candidate.candidate_id) or _fallback_keyword(candidate)
        match = CatalogMatch(candidate_id=candidate.candidate_id, status="unknown", keyword=keyword)
        matches[candidate.candidate_id] = match
        if not budget.take():
            match.reason = "search_limit"
            continue
        try:
            hits = await catalog.search(keyword)
        except CatalogSearchError as e:
            match.reason = f"search_unavailable:{e.reason}"
            continue
        excluded[candidate.candidate_id] = {
            h.product_id: "discontinued" if h.discontinued else "category_mismatch"
            for h in hits if h.discontinued or h.category_dir not in allowed_dirs
        }
        usable = {h.product_id: h for h in hits if h.product_id not in excluded[candidate.candidate_id]}
        if usable:
            offered[candidate.candidate_id] = usable
        else:
            match.reason = "all_discontinued" if hits and all(h.discontinued for h in hits) else "not_in_catalog"

    if offered:
        chosen = await model.generate_json(
            task=SELECT_TASK,
            payload={
                "candidates": [c.model_dump() for c in candidates if c.candidate_id in offered],
                "results": {
                    cid: [{"product_id": h.product_id, "name": h.name, "summary": h.summary} for h in hits.values()]
                    for cid, hits in offered.items()
                },
            },
            output_schema=_Choices,
        )
        picks = {c.candidate_id: c.product_id for c in chosen.choices}
        for cid, hits in offered.items():
            match = matches[cid]
            product_id = picks.get(cid)
            if product_id is None:
                match.reason = "not_in_catalog"
            elif product_id in hits:
                match.status, match.hit = "matched", hits[product_id]
            else:
                match.reason = excluded.get(cid, {}).get(product_id, "choice_not_in_results")
            match.alternatives = [h for pid, h in hits.items() if pid != product_id]

    return [matches[c.candidate_id] for c in candidates]
