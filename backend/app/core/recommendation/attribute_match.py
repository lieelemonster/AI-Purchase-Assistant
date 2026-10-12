"""把问卷里的用途和偏好对应到产品库字段，按命中条数排序。"""

import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from app.catalog.library import LibraryProduct
from app.core.recommendation.catalog_select import CatalogChoice
from app.schemas.need import OptionAnswer

CheckFn = Callable[[LibraryProduct], bool]


@dataclass(frozen=True)
class Check:
    check_id: str
    label: str
    ok: CheckFn


def _text(product: LibraryProduct, field: str) -> str:
    return product.specs.get(field, "")


def _known(text: str) -> bool:
    value = (text or "").strip()
    return bool(value) and value not in {"未确认", "未标注", "不适用"}


def _gb(text: str) -> Optional[int]:
    found = [int(item) for item in re.findall(r"(\d+)\s*GB", text, flags=re.I)]
    return max(found) if found else None


def _inches(text: str) -> Optional[float]:
    matched = re.search(r"(\d+(?:\.\d+)?)\s*英寸", text)
    return float(matched.group(1)) if matched else None


def _grams(text: str) -> Optional[float]:
    kilos = re.search(r"(\d+(?:\.\d+)?)\s*kg", text, flags=re.I)
    if kilos:
        return float(kilos.group(1)) * 1000
    grams = re.search(r"(\d+(?:\.\d+)?)\s*g", text, flags=re.I)
    return float(grams.group(1)) if grams else None


def _hz(text: str) -> Optional[int]:
    found = [int(item) for item in re.findall(r"(\d+)\s*Hz", text, flags=re.I)]
    return max(found) if found else None


def _wh(text: str) -> Optional[float]:
    matched = re.search(r"(\d+(?:\.\d+)?)\s*Wh", text, flags=re.I)
    return float(matched.group(1)) if matched else None


def _mah(text: str) -> Optional[int]:
    matched = re.search(r"(\d+)\s*mAh", text, flags=re.I)
    return int(matched.group(1)) if matched else None


def _rtx(text: str) -> Optional[int]:
    matched = re.search(r"RTX\s*(\d{4})", text, flags=re.I)
    return int(matched.group(1)) if matched else None


def _apple_gpu_cores(text: str) -> Optional[int]:
    matched = re.search(r"(\d+)\s*核GPU", text)
    return int(matched.group(1)) if matched else None


def _mp_wan(text: str) -> Optional[float]:
    yi = re.search(r"(\d+(?:\.\d+)?)\s*亿", text)
    if yi:
        return float(yi.group(1)) * 10000
    found = [int(item) for item in re.findall(r"(\d+)\s*万", text)]
    return max(found) if found else None


def _hours(text: str) -> Optional[int]:
    found = [int(item) for item in re.findall(r"(\d+)\s*(?:小时|\bh\b)", text, flags=re.I)]
    return max(found) if found else None


def _driver_mm(text: str) -> Optional[int]:
    matched = re.search(r"(\d+)\s*mm", text, flags=re.I)
    return int(matched.group(1)) if matched else None


def _release_key(product: LibraryProduct) -> tuple:
    matched = re.match(r"(\d{4})-(\d{2})(?:-(\d{2}))?$", _text(product, "release_date").strip())
    if matched is None:
        return (0, 0, 0)
    year, month, day = matched.groups()
    return (int(year), int(month), int(day or 0))


def _phone_flagship(text: str) -> bool:
    return bool(re.search(r"骁龙\s*8|骁龙8|天玑\s*9\d{3}|A1[7-9]", text))


def _tablet_flagship(text: str) -> bool:
    return _phone_flagship(text) or bool(re.search(r"Apple M|M[1-5]", text))


def _checks_for(category_id: str, selected: set, free_text: str) -> List[Check]:
    found: List[Check] = []
    seen = set()

    def add(check_id: str, label: str, ok: CheckFn, *triggers: str) -> None:
        if check_id in seen:
            return
        if not any(trigger in selected or trigger in free_text for trigger in triggers):
            return
        seen.add(check_id)
        found.append(Check(check_id, label, ok))

    if category_id == "laptop":
        add("mem16", "内存至少 16GB", lambda p: (_gb(_text(p, "memory")) or 0) >= 16, "office", "programming", "creative")
        add("mem32", "内存至少 32GB", lambda p: (_gb(_text(p, "memory")) or 0) >= 32, "data_ai")
        add("ssd512", "硬盘至少 512GB", lambda p: (_gb(_text(p, "storage")) or 0) >= 512, "programming")
        add("gpu5060", "独立显卡不低于 RTX 5060", lambda p: (_rtx(_text(p, "gpu")) or 0) >= 5060, "gaming", "大型游戏", "玩游戏")
        add("hz144", "屏幕刷新率至少 144Hz", lambda p: (_hz(_text(p, "refresh_rate")) or 0) >= 144, "gaming", "大型游戏")
        add("ai_gpu", "有较强显卡或至少 16 核图形核心", lambda p: (_rtx(_text(p, "gpu")) or 0) >= 4060 or (_apple_gpu_cores(_text(p, "gpu")) or 0) >= 16, "data_ai")
        add("panel", "屏幕为 OLED 或 Mini-LED", lambda p: any(word in _text(p, "panel_type") for word in ("OLED", "Mini-LED")), "creative", "screen")
        add("light15", "重量不超过 1.5kg", lambda p: (_grams(_text(p, "weight")) or 9999) <= 1500, "often", "light", "轻薄")
        add("carry18", "重量不超过 1.8kg", lambda p: (_grams(_text(p, "weight")) or 9999) <= 1800, "sometimes")
        add("desk15", "屏幕至少 15 英寸", lambda p: (_inches(_text(p, "screen_size")) or 0) >= 15, "desk")
        add("size1314", "屏幕在 13–14.9 英寸", lambda p: 13 <= (_inches(_text(p, "screen_size")) or 0) < 15, "13_14")
        add("size1516", "屏幕在 15–16.9 英寸", lambda p: 15 <= (_inches(_text(p, "screen_size")) or 0) < 17, "15_16")
        add("macos", "系统为 macOS", lambda p: "macOS" in _text(p, "os") or "Apple" in _text(p, "processor"), "macos")
        add("windows", "系统为 Windows", lambda p: "Windows" in _text(p, "os"), "windows")
        add("battery75", "电池至少 75Wh", lambda p: (_wh(_text(p, "battery_capacity")) or 0) >= 75, "battery", "续航")
        add("hz120", "屏幕刷新率至少 120Hz", lambda p: (_hz(_text(p, "refresh_rate")) or 0) >= 120, "screen")
        add("perf", "处理器或显卡属于高性能", lambda p: (_rtx(_text(p, "gpu")) or 0) >= 4060 or any(word in _text(p, "processor") for word in ("Ultra 7", "Ultra 9", "i7", "i9", "HX", "M4", "M5")), "performance", "性能")
        add("quiet", "没有 RTX 40/50 系列独显", lambda p: _known(_text(p, "gpu")) and _rtx(_text(p, "gpu")) is None, "quiet", "安静")
        add("ports", "接口含 HDMI、USB-A 或网口", lambda p: any(word in _text(p, "ports") for word in ("HDMI", "USB-A", "RJ45", "雷电", "雷雳")), "ports", "接口")
        add("gaming_body", "游戏本机身（RTX 4050 及以上）", lambda p: (_rtx(_text(p, "gpu")) or 0) >= 4050, "gaming_body")
    elif category_id == "phone":
        add("mem8", "运行内存至少 8GB", lambda p: (_gb(_text(p, "memory")) or 0) >= 8, "daily")
        add("mem12", "运行内存至少 12GB", lambda p: (_gb(_text(p, "memory")) or 0) >= 12, "business")
        add("camera", "后置有长焦或主摄至少 5000 万", lambda p: "长焦" in _text(p, "rear_camera") or (_mp_wan(_text(p, "rear_camera")) or 0) >= 5000, "camera", "拍照")
        add("flagship", "处理器为骁龙 8 系、天玑 9000 系或 A17 及更新", lambda p: _phone_flagship(_text(p, "processor")), "gaming", "performance", "玩游戏", "性能")
        add("hz120", "屏幕刷新率至少 120Hz", lambda p: (_hz(_text(p, "refresh_rate")) or 0) >= 120, "gaming", "high_refresh", "高刷新")
        add("bat5000", "电池至少 5000mAh", lambda p: (_mah(_text(p, "battery_capacity")) or 0) >= 5000, "business", "elder", "battery", "续航")
        add("bat5500", "电池至少 5500mAh", lambda p: (_mah(_text(p, "battery_capacity")) or 0) >= 5500, "battery", "续航")
        add("big", "屏幕至少 6.7 英寸", lambda p: (_inches(_text(p, "screen_size")) or 0) >= 6.7, "elder", "big_screen", "大屏")
        add("compact", "重量不超过 190g", lambda p: (_grams(_text(p, "weight")) or 9999) <= 190, "compact", "轻薄", "小巧")
        add("ios", "系统为 iOS", lambda p: "iOS" in _text(p, "os"), "ios")
        add("android", "系统为安卓或基于安卓的系统", lambda p: _known(_text(p, "os")) and "iOS" not in _text(p, "os"), "android")
        add("updates", "系统版本较新", lambda p: any(word in _text(p, "os") for word in ("iOS", "Android 15", "Android 16", "Android 17", "HyperOS", "OriginOS 5", "OriginOS 6", "OriginOS 7")), "long_updates")
    elif category_id == "tablet":
        add("screen11", "屏幕至少 11 英寸", lambda p: (_inches(_text(p, "screen_size")) or 0) >= 11, "entertainment")
        add("battery", "电池至少 8000mAh 或 30Wh", lambda p: (_mah(_text(p, "battery_capacity")) or 0) >= 8000 or (_wh(_text(p, "battery_capacity")) or 0) >= 30, "entertainment")
        add("stylus", "支持手写笔", lambda p: any(word in _text(p, "stylus_support") for word in ("支持", "Pencil", "Pen", "笔")), "notes", "drawing", "stylus", "手写")
        add("keyboard", "支持键盘", lambda p: _known(_text(p, "keyboard_support")) and "未确认" not in _text(p, "keyboard_support"), "office", "keyboard", "键盘")
        add("mem8", "运行内存至少 8GB", lambda p: (_gb(_text(p, "memory")) or 0) >= 8, "office")
        add("draw_screen", "屏幕至少 12 英寸或刷新率至少 120Hz", lambda p: (_inches(_text(p, "screen_size")) or 0) >= 12 or (_hz(_text(p, "refresh_rate")) or 0) >= 120, "drawing")
        add("kids", "重量不超过 600g", lambda p: (_grams(_text(p, "weight")) or 9999) <= 600, "kids")
        add("flagship", "处理器为高通 8 系、天玑 9000 系或 Apple M 系列", lambda p: _tablet_flagship(_text(p, "processor")), "gaming", "玩游戏")
        add("hz120", "屏幕刷新率至少 120Hz", lambda p: (_hz(_text(p, "refresh_rate")) or 0) >= 120, "gaming")
        add("around11", "屏幕小于 12 英寸", lambda p: 0 < (_inches(_text(p, "screen_size")) or 99) < 12, "around_11")
        add("size12", "屏幕至少 12 英寸", lambda p: (_inches(_text(p, "screen_size")) or 0) >= 12, "12_13")
        add("apple", "系统为 iPadOS", lambda p: "iPadOS" in _text(p, "os") or "iOS" in _text(p, "os"), "apple")
        add("android", "系统不是 iPadOS", lambda p: _known(_text(p, "os")) and "iPadOS" not in _text(p, "os") and "iOS" not in _text(p, "os"), "android_windows")
    elif category_id == "headphones":
        add("anc", "支持降噪", lambda p: _text(p, "anc").startswith("有"), "commute", "anc", "降噪")
        add("ip", "防护等级至少 IPX4 或 IP54", lambda p: bool(re.search(r"IPX?[4-9]", _text(p, "ip_rating"), flags=re.I)), "sports", "waterproof", "防水")
        add("calls", "入耳或头戴，适合通话", lambda p: any(word in _text(p, "earbud_type") for word in ("入耳", "头戴")), "calls", "通话")
        add("media", "头戴或驱动单元至少 10mm", lambda p: "头戴" in _text(p, "earbud_type") or (_driver_mm(_text(p, "driver")) or 0) >= 10, "home_media", "sound", "音质")
        add("latency", "支持低延迟编码或游戏形态", lambda p: any(word in _text(p, "audio_codecs") + _text(p, "earbud_type") for word in ("aptX", "LHDC", "L2HC", "游戏")), "gaming", "low_latency", "低延迟", "打游戏")
        add("sleep", "不是头戴式", lambda p: _known(_text(p, "earbud_type")) and "头戴" not in _text(p, "earbud_type"), "sleep", "睡觉")
        add("tws", "入耳式真无线", lambda p: "真无线" in _text(p, "earbud_type") and "入耳" in _text(p, "earbud_type"), "true_wireless")
        add("over", "头戴式", lambda p: "头戴" in _text(p, "earbud_type"), "over_ear")
        add("open", "开放式或耳夹式", lambda p: any(word in _text(p, "earbud_type") for word in ("开放", "耳夹")), "open_ear")
        add("wired", "有线", lambda p: "有线" in _text(p, "earbud_type"), "wired")
        add("aac", "支持 AAC", lambda p: "AAC" in _text(p, "audio_codecs"), "iphone")
        add("ldac", "支持 LDAC、aptX 或 LHDC", lambda p: any(word in _text(p, "audio_codecs") for word in ("LDAC", "aptX", "LHDC", "L2HC")), "android")
        add("bt", "蓝牙 5.2 或更新", lambda p: any(word in _text(p, "bluetooth_version") for word in ("5.2", "5.3", "5.4", "6.0", "6.1")), "multi", "computer")
        add("hours", "单次续航至少 8 小时", lambda p: (_hours(_text(p, "single_battery_life")) or 0) >= 8, "battery", "续航")
    return found


def _selected(option_answers: Sequence[OptionAnswer], free_text: str) -> set:
    selected = {option_id for answer in option_answers for option_id in answer.option_ids}
    selected.discard("not_sure")
    selected.discard("either")
    selected.discard("unfamiliar")
    selected.discard("not_important")
    selected.discard("none")
    selected.discard("mixed")
    return selected


def rank_by_attributes(
    category_id: str,
    option_answers: Sequence[OptionAnswer],
    free_text: str,
    products: Sequence[LibraryProduct],
) -> List[CatalogChoice]:
    checks = _checks_for(category_id, _selected(option_answers, free_text), free_text or "")
    scored: List[Tuple[int, tuple, int, LibraryProduct, List[str]]] = []
    for product in products:
        labels = [check.label for check in checks if check.ok(product)]
        scored.append((len(labels), _release_key(product), -product.row_id, product, labels))
    scored.sort(reverse=True)
    choices = []
    for _count, _released, _row, product, labels in scored[:3]:
        if labels:
            reason = "匹配：" + "；".join(labels) + "。"
        else:
            reason = "在预算和品牌范围内，按发布时间更近优先。"
        if product.price_yuan is None:
            reason += "参考价未确认。"
        choices.append(CatalogChoice(product_id=product.product_id, reason=reason))
    return choices
