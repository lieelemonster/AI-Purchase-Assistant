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
