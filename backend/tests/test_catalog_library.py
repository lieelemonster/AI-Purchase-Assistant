from app.catalog.library import LibraryProduct, filter_by_brand, filter_candidates
from app.core.recommendation.catalog_select import _validate, _Selection


def product(row_id, price):
    return LibraryProduct(
        product_id=f"laptops:{row_id}",
        row_id=row_id,
        table="laptops",
        brand="示例",
        model=f"本{row_id}",
        price_text=price,
        price_yuan=int(price) if str(price).isdigit() else None,
        source_url="",
        specs={"memory": "16GB"},
    )


def test_budget_range_drops_prices_outside_either_end_and_keeps_unconfirmed():
    rows = [product(1, "4000"), product(2, "6000"), product(3, "6001"), product(4, "1000"), product(5, "未确认")]
    kept = filter_candidates(rows, 4000, 6000)
    assert [item.row_id for item in kept] == [1, 2, 5]


def test_only_xiaomi_drops_other_brands_and_keeps_xiaomi():
    rows = [
        product(1, "4599"),
        LibraryProduct("phones:2", 2, "phones", "华为", "Mate 60", "4999", 4999, "", {}),
        LibraryProduct("phones:3", 3, "phones", "红米（Redmi）", "K70", "2499", 2499, "", {}),
    ]
    rows[0] = LibraryProduct("phones:1", 1, "phones", "小米", "Xiaomi 14", "4599", 4599, "", {})
    kept = filter_by_brand(rows, "只要小米品牌")
    assert [item.brand for item in kept] == ["小米"]


def test_reason_digit_missing_from_the_row_is_rejected():
    rows = [product(1, "5999"), product(2, "6999"), product(3, "7999")]
    draft = _Selection.model_validate({
        "primary": {"product_id": "laptops:1", "reason": "适合 32GB 内存"},
        "alternatives": [
            {"product_id": "laptops:2", "reason": "适合写文档"},
            {"product_id": "laptops:3", "reason": "适合写文档"},
        ],
    })
    selection, problems = _validate(draft, rows)
    assert selection is None
    assert problems
