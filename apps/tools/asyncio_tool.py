import asyncio


class ConcurrencyManager:
    def __init__(self, max_concurrent=3):
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def execute(self, func, *args, **kwargs):
        async with self.semaphore:
            # 如果是协程则 await，否则直接执行
            return await func(*args, **kwargs)

