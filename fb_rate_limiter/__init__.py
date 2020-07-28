import json
import time
from enum import Enum
from threading import Condition
from typing import List, Tuple, Union

from cachetools import Cache

__version__ = "0.0.1"


class BUCRateLimitType(Enum):
    ads_insights = "ads_insights"
    ads_management = "ads_management"
    custom_audience = "custom_audience"
    instagram = "instagram"
    leadgen = "leadgen"
    messenger = "messenger"
    pages = "pages"


class SandglassCache(Cache):
    """
    SandglassCache is a special kind of cache that reduces its value as time passes.
    @param sink_rate: how much amount reduces each time
    @param sink_seconds: how often each reduce occurs
    @param lower_limit: lower limit of the value
    """

    def __init__(
        self,
        maxsize: int,
        *,
        sink_rate: int,
        sink_seconds: int,
        lower_limit: Union[int, float] = float("-inf")
    ):
        super().__init__(maxsize)
        self.lower_limit = lower_limit
        self.sink_rate = sink_rate
        self.sink_seconds = sink_seconds

    def __setitem__(self, key, value):
        super().__setitem__(key, (value, time.monotonic()))

    def __getitem__(self, key):
        value, timestamp = super().__getitem__(key)
        elapsed = time.monotonic() - timestamp
        if elapsed > 0:
            n = int(elapsed // self.sink_seconds)
            value -= self.sink_rate * n
            return max(value, self.lower_limit)
        return value

    def set_and_freeze(self, key, value, freeze_seconds: Union[int, float]):
        """freeze a value for some time"""
        super().__setitem__(key, (value, time.monotonic() + freeze_seconds))

    def incr(self, key, value):
        val, ts = super().__getitem__(key)
        super().__setitem__(key, (val + value, ts))


class Strategy:
    def __init__(self, cache: SandglassCache, threshold: int = 80, increase_rate=5):
        self._cache = cache
        self._threshold = threshold
        self._increase_rate = increase_rate

    @classmethod
    def new(
        cls,
        maxsize: int = 10000,
        sink_rate: int = 1,
        sink_seconds: int = 10,
        lower_limit: int = 0,
        threshold: int = 80,
    ):
        return cls(
            SandglassCache(
                maxsize,
                sink_rate=sink_rate,
                sink_seconds=sink_seconds,
                lower_limit=lower_limit,
            ),
            threshold=threshold,
        )

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
                        freeze_seconds = 0
                    else:
                        freeze_seconds = estimated_time_to_regain_access * 60
                    max_percentage = max(usage_type_dic.values())
                    self._cache.set_and_freeze(
                        (business_object_id, usage_type), max_percentage, freeze_seconds
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
        # fb ads insights throttle strategy
        if "x-fb-ads-insights-throttle" in headers:
            d = json.loads(headers["x-fb-ads-insights-throttle"])
            max_percentage = max(d.values())
            self._cache["fb-ads-insights-throttle"] = max_percentage

    def check_keys(self, keys: List[Tuple[str, str]]) -> bool:
        r = all(self.check(key) for key in keys)
        if r:
            for key in keys:
                self._cache.incr(key, self._increase_rate)
        return r

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
