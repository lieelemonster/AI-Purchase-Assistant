"""从本地电子产品库按品类读出全部行，再用预算上限筛选。"""

import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from app.core.needs.normalize import BUDGET_TOPIC, _option_budget, stated_budget_cap_yuan
from app.schemas.need import NeedProfile

TABLES = {
    "laptop": "laptops",
    "phone": "phones",
    "tablet": "tablets",
    "headphones": "earbuds",
}

SPEC_COLUMNS = {
    "laptops": [
        "release_date", "processor", "gpu", "memory", "storage_type", "storage", "screen_size",
        "screen_resolution", "refresh_rate", "panel_type", "battery_capacity", "charging_power",
        "ports", "wifi", "bluetooth", "weight", "os",
    ],
    "phones": [
        "release_date", "processor", "memory", "storage", "screen_size", "screen_resolution",
        "refresh_rate", "rear_camera", "front_camera", "battery_capacity", "wired_charging_power",
        "wireless_charging_power", "os", "weight",
    ],
    "tablets": [
        "release_date", "processor", "memory", "storage", "screen_size", "screen_resolution",
        "refresh_rate", "panel_type", "rear_camera", "front_camera", "battery_capacity",
        "charging_power", "speakers", "stylus_support", "keyboard_support", "weight", "os",
    ],
    "earbuds": [
        "release_date", "earbud_type", "driver", "bluetooth_version", "audio_codecs", "anc",
        "transparency_mode", "call_noise_reduction", "single_battery_life", "total_battery_life",
        "charging_method", "ip_rating", "weight",
    ],
}


@dataclass(frozen=True)
class LibraryProduct:
    product_id: str
    row_id: int
    table: str
    brand: str
    model: str
    price_text: str
    price_yuan: Optional[int]
    source_url: str
    specs: Dict[str, str]

    @property
    def name(self) -> str:
        return f"{self.brand} {self.model}".strip()


def budget_bounds_yuan(need: NeedProfile) -> tuple:
    """预算区间（元）。选项里的上下限都会用：区间取更窄的那个，原文里写明的上限也算。没有某一端就不按那一端排除。"""
    floors: List[int] = []
    ceilings: List[int] = []
    for answer in need.option_answers:
        if answer.question_id != BUDGET_TOPIC:
            continue
        for option_id in answer.option_ids:
            bounds = _option_budget(option_id)
            if bounds is None:
                continue
            if bounds[0] is not None:
                floors.append(bounds[0])
            if bounds[1] is not None:
                ceilings.append(bounds[1])
    stated = stated_budget_cap_yuan(need.free_text)
    if stated is not None:
        ceilings.append(stated)
    for requirement in need.requirements:
        if requirement.topic != BUDGET_TOPIC:
            continue
        if requirement.budget_min_minor is not None:
            floors.append(requirement.budget_min_minor // 100)
        if requirement.budget_max_minor is not None:
            ceilings.append(requirement.budget_max_minor // 100)
    floor = max(floors) if floors else None
    ceiling = min(ceilings) if ceilings else None
    return floor, ceiling


def _price_yuan(raw: Optional[str]) -> Optional[int]:
    text = (raw or "").strip()
    return int(text) if text.isdigit() else None


def load_products(db_path: str, category_id: str) -> List[LibraryProduct]:
    table = TABLES[category_id]
    columns = ["id", "brand", "model", "reference_price", "source_url", *SPEC_COLUMNS[table]]
    db = sqlite3.connect(db_path)
    try:
        rows = db.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY id").fetchall()
    finally:
        db.close()
    products = []
    for row in rows:
        values = dict(zip(columns, row))
        specs = {}
        for column in SPEC_COLUMNS[table]:
            value = values.get(column)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                specs[column] = text
        products.append(LibraryProduct(
            product_id=f"{table}:{values['id']}",
            row_id=int(values["id"]),
            table=table,
            brand=str(values["brand"] or "").strip(),
            model=str(values["model"] or "").strip(),
            price_text=str(values["reference_price"] or "").strip(),
            price_yuan=_price_yuan(values["reference_price"]),
            source_url=str(values["source_url"] or "").strip(),
            specs=specs,
        ))
    return products


def _brand_aliases(brand: str) -> List[str]:
    names = [brand.strip()]
    if "（" in brand and "）" in brand:
        head, _, rest = brand.partition("（")
        names.append(head.strip())
        inner = rest.split("）", 1)[0]
        names.extend(part.strip() for part in re.split(r"[，,、/ ]", inner))
    return [name for name in names if len(name) >= 2 and not name.startswith("含")]


def _catalog_brands(products: List[LibraryProduct]) -> List[str]:
    return sorted({product.brand for product in products if product.brand})


def _brands_named(text: str, brands: List[str]) -> List[str]:
    found = []
    for brand in brands:
        if any(alias in text for alias in _brand_aliases(brand)):
            found.append(brand)
    return found


def _user_clauses(free_text: str) -> List[str]:
    clauses = []
    for raw in (free_text or "").splitlines():
        text = raw.strip()
        if "：" in text:
            text = text.split("：", 1)[1].strip()
        for piece in re.split(r"[，,。；;]", text):
            piece = piece.strip()
            if piece:
                clauses.append(piece)
    return clauses


def required_brands(free_text: str, products: List[LibraryProduct]) -> Set[str]:
    """用户写了「只要／必须」某品牌，或在品牌一栏只填了品牌名时，返回必须命中的库内品牌。"""
    brands = _catalog_brands(products)
    required: Set[str] = set()
    for clause in _user_clauses(free_text):
        named = _brands_named(clause, brands)
        if not named:
            continue
        if any(word in clause for word in ("不要", "不想要", "别推", "别买", "排除")):
            continue
        exclusive = any(word in clause for word in ("只要", "只看", "只买", "只想要", "必须", "一定要"))
        leftover = clause
        for brand in named:
            for alias in _brand_aliases(brand):
                leftover = leftover.replace(alias, "")
        leftover = re.sub(r"品牌|的|和|或|与|\s", "", leftover)
        if exclusive or not leftover:
            required.update(named)
    return required


def excluded_brands(free_text: str, products: List[LibraryProduct]) -> Set[str]:
    brands = _catalog_brands(products)
    excluded: Set[str] = set()
    for clause in _user_clauses(free_text):
        if not any(word in clause for word in ("不要", "不想要", "别推", "别买", "排除")):
            continue
        excluded.update(_brands_named(clause, brands))
    return excluded


def filter_by_brand(products: List[LibraryProduct], free_text: str, catalog: Optional[List[LibraryProduct]] = None) -> List[LibraryProduct]:
    names_from = products if catalog is None else catalog
    required = required_brands(free_text, names_from)
    excluded = excluded_brands(free_text, names_from)
    if not required and not excluded:
        return list(products)
    kept = []
    for product in products:
        if product.brand in excluded:
            continue
        if required and product.brand not in required:
            continue
        kept.append(product)
    return kept


def filter_candidates(products: List[LibraryProduct], floor_yuan: Optional[int], ceiling_yuan: Optional[int]) -> List[LibraryProduct]:
    """有数字参考价时必须落在预算区间内。价格未确认的行仍保留。不比较配件、蜂窝或国补。"""
    kept = []
    for product in products:
        price = product.price_yuan
        if price is None:
            kept.append(product)
            continue
        if floor_yuan is not None and price < floor_yuan:
            continue
        if ceiling_yuan is not None and price > ceiling_yuan:
            continue
        kept.append(product)
    return kept
