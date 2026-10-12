from app.scripts.catalog_crawl import list_product_urls, parse_release

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>http://product.pconline.com.cn/notebook/lenovo/2916211.html</loc></url>
  <url><loc>http://product.pconline.com.cn/notebook/lenovo/2916211_detail.html</loc></url>
  <url><loc>http://product.pconline.com.cn/notebook/lenovo/2916211_price.html</loc></url>
  <url><loc>http://product.pconline.com.cn/notebook/unknownbrand/1.html</loc></url>
  <url><loc>http://ks.pconline.com.cn/product.shtml?q=联想</loc></url>
  <url><loc>http://product.pconline.com.cn/mobile/apple/10.html</loc></url>
  <url><loc>http://product.pconline.com.cn/dc/canon/635604.html</loc></url>
</urlset>
""".encode("utf-8")


def test_only_allowed_product_homepages_are_kept():
    urls = list_product_urls(SITEMAP)
    assert urls == [
        ("2916211", "laptop", "lenovo", "https://product.pconline.com.cn/notebook/lenovo/2916211.html"),
        ("10", "phone", "apple", "https://product.pconline.com.cn/mobile/apple/10.html"),
    ]


def test_release_within_two_years():
    assert parse_release("上市时间 | 2025年3月")[0] is True
    assert parse_release("发布时间 | 2024年10月11日")[0] is True
    assert parse_release("上市时间 | 2024年9月")[0] is False
    assert parse_release("上市时间 | 2024年")[0] is False
    assert parse_release("处理器 | 示例芯片")[0] is False
