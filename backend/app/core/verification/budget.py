class SearchBudget:
    """一次推荐请求内共享的搜索次数上限。"""

    def __init__(self, max_calls: int):
        self.max_calls = max_calls
        self.used = 0

    def take(self) -> bool:
        if self.used >= self.max_calls:
            return False
        self.used += 1
        return True
