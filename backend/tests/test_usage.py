from app.core.usage import RequestUsage, format_usage, start_usage, add_model_call, add_search


def test_summary_has_counts_and_not_the_user_text():
    usage = RequestUsage(stages_ms={"需求": 12, "读取": 340}, model_calls=4, model_tokens=800, searches=3, pages_read=6, cache_hits=1)
    text = format_usage(usage)
    secret = "我想买笔记本，主要写文档，预算还没想好"
    assert "模型调用=4" in text
    assert "token=800" in text
    assert "搜索=3" in text
    assert "读取页面=6" in text
    assert "缓存命中=1" in text
    assert "需求12ms" in text
    assert secret not in text


def test_counters_only_change_inside_a_request():
    usage = start_usage()
    add_model_call()
    add_search()
    assert usage.model_calls == 1
    assert usage.searches == 1
