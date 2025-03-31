import pytest
import asyncio
from salesforce_toolkit.concurrency import run_with_concurrency

@pytest.mark.asyncio
async def test_concurrency_limit():
    """Test that concurrency limit is enforced."""
    execution_times = []
    max_concurrent = 0
    current_concurrent = 0

    async def task(delay: float):
        nonlocal current_concurrent, max_concurrent
        current_concurrent += 1
        max_concurrent = max(max_concurrent, current_concurrent)

        start_time = asyncio.get_event_loop().time()
        await asyncio.sleep(delay)
        execution_times.append(asyncio.get_event_loop().time() - start_time)

        current_concurrent -= 1
        return delay

    concurrency_limit = 3
    delays = [0.1] * 10  # 10 tasks with 0.1s delay each

    # Record the start time before running all tasks
    overall_start_time = asyncio.get_event_loop().time()

    results = await run_with_concurrency(concurrency_limit, [task(d) for d in delays])

    # Calculate total run time
    overall_execution_time = asyncio.get_event_loop().time() - overall_start_time

    assert max_concurrent <= concurrency_limit
    assert results == delays

    # If concurrency is working, execution time should be less than running sequentially
    assert max(execution_times) >= 0.1
    total_execution_time = sum(execution_times)

    # The total time should be approximately (total_execution_time / concurrency_limit)
    # But we need to allow for some overhead, so just verify it's not sequential
    assert overall_execution_time < total_execution_time


@pytest.mark.asyncio
async def test_callback_function():
    """Test that callback function is called for each task."""
    callback_results = []

    async def task(value):
        await asyncio.sleep(0.01)
        return value

    def callback(result):
        callback_results.append(result)

    values = [1, 2, 3, 4, 5]
    results = await run_with_concurrency(2, [task(v) for v in values], callback)

    assert results == values
    assert sorted(callback_results) == values

@pytest.mark.asyncio
async def test_async_callback_function():
    """Test that async callback function is awaited."""
    callback_results = []

    async def task(value):
        await asyncio.sleep(0.01)
        return value

    async def async_callback(result):
        await asyncio.sleep(0.01)
        callback_results.append(result)

    values = [1, 2, 3, 4, 5]
    results = await run_with_concurrency(2, [task(v) for v in values], async_callback)

    assert results == values
    assert sorted(callback_results) == values

@pytest.mark.asyncio
async def test_empty_coroutines():
    """Test with empty list of coroutines."""
    results = await run_with_concurrency(5, [])
    assert results == []

@pytest.mark.asyncio
async def test_error_propagation():
    """Test that errors in tasks are properly propagated."""
    async def succeeding_task():
        await asyncio.sleep(0.01)
        return "success"

    async def failing_task():
        await asyncio.sleep(0.01)
        raise ValueError("Task failed")

    with pytest.raises(ValueError, match="Task failed"):
        await run_with_concurrency(2, [succeeding_task(), failing_task()])

@pytest.mark.asyncio
async def test_different_return_types():
    """Test with tasks that return different types."""
    async def task_int():
        await asyncio.sleep(0.01)
        return 42

    async def task_str():
        await asyncio.sleep(0.01)
        return "hello"

    async def task_list():
        await asyncio.sleep(0.01)
        return [1, 2, 3]

    results = await run_with_concurrency(3, [task_int(), task_str(), task_list()])
    assert results == [42, "hello", [1, 2, 3]]

@pytest.mark.asyncio
async def test_concurrency_one():
    """Test with concurrency limit of 1 (should run sequentially)."""
    execution_order = []

    async def task(idx):
        execution_order.append(idx)
        await asyncio.sleep(0.01)
        return idx

    tasks = [task(i) for i in range(5)]
    results = await run_with_concurrency(1, tasks)

    assert results == list(range(5))
    assert execution_order == list(range(5))  # Should execute in order
