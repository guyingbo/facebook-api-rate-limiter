# facebook-api-rate-limiter
facebook api rate limiter for multithread execution.

## Installation

~~~
pip3 install facebook-api-rate-limiter
~~~

## Usage

First, create the limiter object,

```python
from fb_rate_limiter import RateLimiter, Strategy
limiter = RateLimiter(Strategy(threshold=80))
```

Then, acquire privilege. There are three types of limits

```python
limiter.acquire(("business_id_xxx", "ads_insights"))
```

or

```python
limiter.acquire("app-usage")
```

or

```python
limiter.acquire("ad-account-usage")
```

or use them together, for example:

```python
limiter.acquire("app-usage", "ad-account-usage")
```

After calling the facebook api, one need to update information from the latest response headers:

```python
limiter.update_from_headers({"x-business-use-case-usage": facebook_response.headers()})
```
