from app.catalog.library import LibraryProduct
from app.core.recommendation.attribute_match import rank_by_attributes
from app.schemas.need import OptionAnswer


def laptop(row_id, gpu, released, price="5999"):
    return LibraryProduct(
        product_id=f"laptops:{row_id}",
        row_id=row_id,
        table="laptops",
        brand="示例",
        model=f"本{row_id}",
        price_text=price,
        price_yuan=int(price),
        source_url="",
        specs={"gpu": gpu, "release_date": released, "refresh_rate": "165Hz"},
    )


def test_gaming_prefers_rtx_5060_or_newer_then_release_date():
    rows = [
        laptop(1, "NVIDIA GeForce RTX 4060", "2026-09"),
        laptop(2, "NVIDIA GeForce RTX 5060", "2025-01"),
        laptop(3, "NVIDIA GeForce RTX 5070", "2024-06"),
        laptop(4, "NVIDIA GeForce RTX 5060", "2026-03"),
    ]
    ranked = rank_by_attributes(
        "laptop",
        [OptionAnswer(question_id="usage", option_ids=["gaming"])],
        "",
        rows,
    )
    assert [item.product_id for item in ranked] == ["laptops:4", "laptops:2", "laptops:3"]
    assert "RTX 5060" in ranked[0].reason
    assert "4060" not in ranked[0].product_id


def phone(row_id, os, battery="8000 mAh", screen="6.85 英寸", released="2026-09"):
    return LibraryProduct(
        product_id=f"phones:{row_id}",
        row_id=row_id,
        table="phones",
        brand="示例",
        model=f"机{row_id}",
        price_text="6999",
        price_yuan=6999,
        source_url="",
        specs={
            "os": os,
            "battery_capacity": battery,
            "screen_size": screen,
            "rear_camera": "5000万长焦",
            "release_date": released,
        },
    )


def test_ios_requirement_excludes_known_android_even_when_it_matches_more_attributes():
    rows = [
        phone(1, "OriginOS 7（Android 17）"),
        phone(2, "Flyme AIOS", battery="未确认", screen="6.1英寸", released="2024-02"),
        phone(3, "iOS 27", battery="未确认", screen="6.3英寸", released="2026-09"),
        phone(4, "未确认", battery="未确认", screen="6.1英寸", released="2020-01"),
    ]
    ranked = rank_by_attributes(
        "phone",
        [
            OptionAnswer(question_id="os", option_ids=["ios"]),
            OptionAnswer(question_id="priorities", option_ids=["battery", "big_screen", "camera"]),
        ],
        "要iOS系统",
        rows,
    )
    assert [item.product_id for item in ranked] == ["phones:3"]
    assert "系统为 iOS" in ranked[0].reason


def test_ios_in_free_text_is_case_insensitive_and_does_not_match_originos():
    rows = [
        phone(1, "OriginOS 7（Android 17）"),
        phone(2, "iOS 26", battery="未确认", screen="6.1英寸", released="2025-09"),
    ]
    ranked = rank_by_attributes("phone", [], "系统要 IOS", rows)
    assert [item.product_id for item in ranked] == ["phones:2"]
