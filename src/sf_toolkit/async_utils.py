from asyncio import BoundedSemaphore, gather
from collections.abc import Iterable
from typing import Callable, TypeVar, Awaitable
from types import CoroutineType

T = TypeVar("T")


async def run_concurrently(
    limit: int,
    coroutines: Iterable[Awaitable[T]],
    task_callback: Callable[[T], Awaitable[None] | None] | None = None,
) -> list[T]:
    """Runs the provided coroutines with maxumum `n` concurrently running."""
    semaphore = BoundedSemaphore(limit)

    async def bounded_task(task: Awaitable[T]):
        async with semaphore:
            result = await task
            if task_callback:
                callback_result = task_callback(result)
                if isinstance(callback_result, CoroutineType):
                    await callback_result
            return result

    # Wrap all coroutines in the semaphore-controlled task
    tasks = [bounded_task(coro) for coro in coroutines]

    # Run and wait for all tasks to complete
    results: list[T] = await gather(*tasks)
    return results
