import asyncio

_queue: "asyncio.Queue[dict]" = asyncio.Queue()


def get_queue() -> "asyncio.Queue[dict]":
    return _queue


async def publish(data: dict) -> None:
    _queue.put_nowait(data)


async def consume() -> dict:
    return await _queue.get()
