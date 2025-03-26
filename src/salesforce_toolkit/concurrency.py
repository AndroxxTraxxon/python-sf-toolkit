from asyncio import BoundedSemaphore, gather
from typing import Callable, Coroutine, TypeVar, Any

T = TypeVar("T")

async def run_with_concurrency(
    limit: int, coroutines: list[Coroutine[Any, Any, T]], task_callback: Callable[[T], None] | None = None
) -> list[T]:
    """Runs the provided coroutines with maxumum `n` concurrently running."""
    semaphore = BoundedSemaphore(limit)

    async def bounded_task(task):
        async with semaphore:
            result = await task
            if task_callback:
                task_callback(result)
            return await task

    # Wrap all coroutines in the semaphore-controlled task
    tasks = [bounded_task(coro) for coro in coroutines]

    # Run and wait for all tasks to complete
    results = await gather(*tasks)
    return results
