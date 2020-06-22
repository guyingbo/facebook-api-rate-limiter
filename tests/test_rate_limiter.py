import json
import random
from concurrent.futures import ThreadPoolExecutor
from time import sleep

from fb_rate_limiter import RateLimiter, Strategy

limiter = RateLimiter(Strategy(threshold=50))


def job(limiter, i):
    limiter.acquire(("business_id_xxx", "ads_insights"))
    try:
        print(i)
        sleep(0.01)
        d = {
            "business_id_xxx": [
                {
                    "type": "ads_insights",
                    "call_count": i,
                    "total_cputime": i,
                    "total_time": i,
                    "estimated_time_to_regain_access": 0,
                }
            ]
        }
        limiter.update_from_headers({"x-business-use-case-usage": json.dumps(d)})
    except Exception as e:
        print(e)


def test_rate_limiter():
    executor = ThreadPoolExecutor(5)
    lst = [i for i in range(100)]
    random.shuffle(lst)
    executor.map(job, lst)
