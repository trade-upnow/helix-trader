import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable


class ExchangeRateLimiter:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def execute(self, key: str, coroutine_factory: Callable[[], Awaitable]):
        async with self._locks[key]:
            result = await coroutine_factory()
            await asyncio.sleep(0.15)
            return result


rate_limiter = ExchangeRateLimiter()
