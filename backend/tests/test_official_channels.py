import pytest
from pydantic import ValidationError

from app.core.verification.official_sources import (
    OfficialChannels,
    check_channel,
    links_confirm_store,
    load_official_channels,
)


@pytest.mark.parametrize("url, brand, brand_id, channel, priority", [
    ("https://www.apple.com.cn/iphone/", "Apple", "apple", "official", 1),
    ("https://www.apple.com.cn/iphone/", "苹果", "apple", "official", 1),
    ("https://store.apple.com/cn/buy-mac", "Apple", "apple", "official", 1),
    ("https://www.mi.com/shop/buy", "Redmi", "xiaomi", "official", 1),
    ("https://www.vmall.com/product/123.html", "华为", "huawei", "official", 1),
    ("https://www.hpstore.cn/notebook.html", "惠普", "hp", "official", 1),
    ("https://www.samsung.com.cn/monitors/", "三星", "samsung", "official", 1),
    ("https://www.sonystyle.com.cn/products/headphone/", "索尼", "sony", "official", 1),
    ("https://huawei.jd.com/", "Huawei", "huawei", "jd", 2),
    ("https://mall.jd.com/index-12894711.html", "联想", "lenovo", "jd", 2),
    ("https://mall.jd.com/shopLevel-10075831.html", "Sony", "sony", "jd", 2),
    ("https://huaweistore.tmall.com/category.htm", "华为", "huawei", "tmall", 3),
])
def test_official_channels_are_recognised_with_priority(url, brand, brand_id, channel, priority):
    result = check_channel(url, brand)
    assert (result.status, result.brand_id, result.channel, result.priority) == ("official", brand_id, channel, priority)


@pytest.mark.parametrize("url, brand", [
    ("https://apple.com.cn.evil.com/", "Apple"),
    ("https://fakeapple.com/", "Apple"),
    ("https://apple.com.cn@evil.com/iphone/", "Apple"),
    ("https://www.apple.com.cn/iphone/", "Xiaomi"),
    ("https://www.apple.com.cn/iphone/", "某不在表中的品牌"),
    ("https://www.mi.com/global/product/", "小米"),
    ("https://consumer.huawei.com/en/phones/", "华为"),
    ("https://mall.jd.com/index-99999999.html", "联想"),
    ("https://fakehuawei.jd.com/", "华为"),
    ("https://www.jd.com/", "华为"),
    ("https://item.jd.com/100012345.html", "Apple"),
    ("https://www.taobao.com/item/1.htm", "华为"),
    ("ftp://apple.com.cn/", "Apple"),
])
def test_everything_else_is_unknown(url, brand):
    assert check_channel(url, brand).status == "unknown"


def test_jd_item_page_needs_a_link_to_the_official_store():
    check = check_channel("https://item.jd.com/100012345.html", "华为")
    assert (check.status, check.channel, check.priority) == ("store_check_required", "jd", 2)
    assert links_confirm_store(["https://www.jd.com/", "//huawei.jd.com/"], check)
    assert not links_confirm_store(["//mall.jd.com/index-1000000001.html", "https://fakehuawei.jd.com/"], check)


def test_jd_item_page_store_can_be_confirmed_by_shop_id():
    check = check_channel("https://item.jd.com/100012345.html", "Lenovo")
    assert links_confirm_store(["//mall.jd.com/index-12894711.html"], check)
    assert not links_confirm_store(["//mall.jd.com/index-12894712.html"], check)


def test_tmall_item_page_needs_a_link_to_the_official_store():
    check = check_channel("https://detail.tmall.com/item.htm?id=123", "Apple")
    assert (check.status, check.channel, check.priority) == ("store_check_required", "tmall", 3)
    assert links_confirm_store(["https://apple.tmall.com/shop/view_shop.htm"], check)
    assert not links_confirm_store(["https://huaweistore.tmall.com/"], check)


def test_official_site_outranks_e_commerce():
    priority = load_official_channels().channel_priority
    assert priority["official"] < priority["jd"] < priority["tmall"]


def test_brand_names_must_not_belong_to_two_brands():
    data = {"channel_priority": {"official": 1, "jd": 2, "tmall": 3}, "brands": [
        {"id": "a", "names": ["Same"], "channels": [{"type": "official", "domain": "a.com"}]},
        {"id": "b", "names": ["same"], "channels": [{"type": "official", "domain": "b.com"}]},
    ]}
    with pytest.raises(ValidationError, match="同时属于"):
        OfficialChannels.model_validate(data)


@pytest.mark.parametrize("channel", [
    {"type": "official", "domain": "https://apple.com.cn"},
    {"type": "official", "domain": "Apple.com.cn"},
    {"type": "official", "domain": "apple.com.cn", "path_prefix": "cn"},
    {"type": "official", "store_host": "apple.jd.com"},
    {"type": "jd", "store_host": "apple.tmall.com"},
    {"type": "jd", "store_host": "apple.jd.com", "shop_id": "1"},
    {"type": "jd"},
    {"type": "tmall", "shop_id": "1"},
    {"type": "jd", "domain": "jd.com", "shop_id": "1"},
])
def test_malformed_channel_rules_are_rejected(channel):
    data = {"channel_priority": {"official": 1, "jd": 2, "tmall": 3},
            "brands": [{"id": "x", "names": ["X"], "channels": [channel]}]}
    with pytest.raises(ValidationError):
        OfficialChannels.model_validate(data)


def test_config_file_loads_all_brands():
    assert len(load_official_channels().brands) == 49
