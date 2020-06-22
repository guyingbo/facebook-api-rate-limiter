import json
from enum import Enum
from threading import Condition
from typing import List, Tuple

from cachetools import TTLCache

__version__ = "0.0.1"


class BUCRateLimitType(Enum):
    ads_insights = "ads_insights"
    ads_management = "ads_management"
    custom_audience = "custom_audience"
    instagram = "instagram"
    leadgen = "leadgen"
    messenger = "messenger"
    pages = "pages"


class MyTTLCache(TTLCache):
    def ttl_set(self, key, value, ttl):
        origin_ttl = self._TTLCache__ttl
        self._TTLCache__ttl = ttl
        self[key] = value
        self._TTLCache__ttl = origin_ttl


class Strategy:
    def __init__(self, maxsize: int = 10000, ttl: int = 60, threshold: int = 80):
        self._cache = MyTTLCache(maxsize=maxsize, ttl=ttl)
        self._threshold = threshold

    def update_from_headers(self, headers: dict):
        # {"business_id_xxx":[{"type":"ads_insights","call_count":1,"total_cputime":1,"total_time":1,"estimated_time_to_regain_access":0}]}'
        # business use case usage strategy
        if "x-business-use-case-usage" in headers:
            d = json.loads(headers["x-business-use-case-usage"])
            for business_object_id, lst in d.items():
                for usage_type_dic in lst:
                    usage_type = usage_type_dic.pop("type")
                    estimated_time_to_regain_access = usage_type_dic.pop(
                        "estimated_time_to_regain_access"
                    )
                    if estimated_time_to_regain_access == 0:
                        ttl = self._cache.ttl
                    else:
                        ttl = (estimated_time_to_regain_access + 1) * 60
                    max_percentage = max(usage_type_dic.values())
                    self._cache.ttl_set(
                        (business_object_id, usage_type), max_percentage, ttl
                    )
        # ad account usage strategy
        if "x-ad-account-usage" in headers:
            d = json.loads(headers["x-ad-account-usage"])
            acc_id_util_pct = d["acc_id_util_pct"]
            self._cache["ad-account-usage"] = acc_id_util_pct
        # app usage strategy
        if "x-app-usage" in headers:
            d = json.loads(headers["x-app-usage"])
            max_percentage = max(d.values())
            self._cache["app-usage"] = max_percentage

    def check_keys(self, keys: List[Tuple[str, str]]) -> bool:
        return all(self.check(key) for key in keys)

    def check(self, key: Tuple[str, str]) -> bool:
        percentage = self._cache.get(key)
        if percentage is None:
            return True
        return percentage < self._threshold


class RateLimiter:
    def __init__(self, strategy: Strategy):
        self._strategy = strategy
        self._cond = Condition()

    def acquire(self, *keys, check_interval=5):
        with self._cond:
            wait = True
            while wait:
                wait = not self._cond.wait_for(
                    lambda: self._strategy.check_keys(keys), check_interval
                )

    def update_from_headers(self, headers):
        with self._cond:
            self._strategy.update_from_headers(headers)
            self._cond.notify()
