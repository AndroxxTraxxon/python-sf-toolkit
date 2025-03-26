from asyncio import BoundedSemaphore, gather
from collections.abc import Iterable
from typing import Callable, TypeVar, Any, Coroutine
from types import CoroutineType
import inspect

T = TypeVar("T")


async def run_with_concurrency(
    limit: int,
    coroutines: Iterable[CoroutineType[Any, Any, T]],
    task_callback: Callable[[T], Coroutine | None] | None = None,
) -> list[T]:
    """Runs the provided coroutines with maxumum `n` concurrently running."""
    semaphore = BoundedSemaphore(limit)

    async def bounded_task(task):
        async with semaphore:
            result = await task
            if task_callback:
                callback_result = task_callback(result)
                if inspect.iscoroutine(callback_result):
                    await callback_result
            return result

    # Wrap all coroutines in the semaphore-controlled task
    tasks = [bounded_task(coro) for coro in coroutines]

    # Run and wait for all tasks to complete
    results: list[T] = await gather(*tasks)
    return results
