import inspect

import pytest

from sf_toolkit.data.bulk import (
    BulkApiIngestJob,
    BulkApiQueryJob,
    BulkQueryResult,
    ResultPage,
)
from sf_toolkit.data.fields import object_values

# Structural / existence tests – validate that the bulk module exposes the expected public API.
# These tests don't assert internal side‑effects (those would require live HTTP / deeper fixtures),
# but they guard against accidental API regressions (removed / renamed methods).


INGEST_JOB_METHODS_SYNC = [
    "init_job",
    "upload_dataset",
    "upload_batches",
    "refresh",
    "monitor_until_complete",
    "_batch_buffers",
    "validate_fieldnames",
]

INGEST_JOB_METHODS_ASYNC = [
    "init_job_async",
    "upload_dataset_async",
    "upload_batches_async",
    "refresh_async",
    "monitor_until_complete_async",
]

QUERY_JOB_METHODS_SYNC = [
    "init_job",
    "refresh",
    "monitor_until_complete",
]

QUERY_JOB_METHODS_ASYNC = [
    "init_job_async",
    "refresh_async",
    "monitor_until_complete_async",
]

QUERY_RESULT_METHODS_SYNC = [
    "__iter__",
    "__aiter__",
    "__next__",
    "as_list",
    "copy",
]

QUERY_RESULT_METHODS_ASYNC = [
    "__anext__",
    "as_list_async",
]

RESULT_PAGE_METHODS_SYNC = [
    "__iter__",
    "__next__",
    "fetch",
    "next_page",
]

RESULT_PAGE_METHODS_ASYNC = [
    "__aiter__",
    "__anext__",
    "fetch_async",
]


@pytest.mark.parametrize("method", INGEST_JOB_METHODS_SYNC)
def test_bulk_ingest_job_has_sync_method(method):
    assert hasattr(BulkApiIngestJob, method), (
        f"BulkApiIngestJob missing sync method {method}"
    )
    attr = getattr(BulkApiIngestJob, method)
    assert callable(attr), f"BulkApiIngestJob.{method} should be callable"


@pytest.mark.parametrize("method", INGEST_JOB_METHODS_ASYNC)
def test_bulk_ingest_job_has_async_method(method):
    assert hasattr(BulkApiIngestJob, method), (
        f"BulkApiIngestJob missing async method {method}"
    )
    attr = getattr(BulkApiIngestJob, method)
    assert callable(attr), f"BulkApiIngestJob.{method} should be callable"
    assert inspect.iscoroutinefunction(attr), (
        f"BulkApiIngestJob.{method} should be a coroutine function"
    )


@pytest.mark.parametrize("method", QUERY_JOB_METHODS_SYNC)
def test_bulk_query_job_has_sync_method(method):
    assert hasattr(BulkApiQueryJob, method), (
        f"BulkApiQueryJob missing sync method {method}"
    )
    attr = getattr(BulkApiQueryJob, method)
    assert callable(attr), f"BulkApiQueryJob.{method} should be callable"


@pytest.mark.parametrize("method", QUERY_JOB_METHODS_ASYNC)
def test_bulk_query_job_has_async_method(method):
    assert hasattr(BulkApiQueryJob, method), (
        f"BulkApiQueryJob missing async method {method}"
    )
    attr = getattr(BulkApiQueryJob, method)
    assert callable(attr), f"BulkApiQueryJob.{method} should be callable"
    assert inspect.iscoroutinefunction(attr), (
        f"BulkApiQueryJob.{method} should be a coroutine function"
    )


@pytest.mark.parametrize("method", QUERY_RESULT_METHODS_SYNC)
def test_bulk_query_result_has_sync_method(method):
    assert hasattr(BulkQueryResult, method), (
        f"BulkQueryResult missing sync method {method}"
    )
    attr = getattr(BulkQueryResult, method)
    assert callable(attr), f"BulkQueryResult.{method} should be callable"


@pytest.mark.parametrize("method", QUERY_RESULT_METHODS_ASYNC)
def test_bulk_query_result_has_async_method(method):
    assert hasattr(BulkQueryResult, method), (
        f"BulkQueryResult missing async method {method}"
    )
    attr = getattr(BulkQueryResult, method)
    assert callable(attr), f"BulkQueryResult.{method} should be callable"
    assert inspect.iscoroutinefunction(attr), (
        f"BulkQueryResult.{method} should be a coroutine function"
    )


@pytest.mark.parametrize("method", RESULT_PAGE_METHODS_SYNC)
def test_result_page_has_sync_method(method):
    assert hasattr(ResultPage, method), f"ResultPage missing sync method {method}"
    attr = getattr(ResultPage, method)
    assert callable(attr), f"ResultPage.{method} should be callable"


@pytest.mark.parametrize("method", RESULT_PAGE_METHODS_ASYNC)
def test_result_page_has_async_method(method):
    assert hasattr(ResultPage, method), f"ResultPage missing async method {method}"
    attr = getattr(ResultPage, method)
    assert callable(attr), f"ResultPage.{method} should be callable"
    assert inspect.iscoroutinefunction(attr), (
        f"ResultPage.{method} should be a coroutine function"
    )


def test_bulk_ingest_job_init_job_uses_operation_and_object(mocker, mock_sf_client):
    """
    Light behavioral test for init_job: ensure the job creation POST is invoked and the returned
    job instance retains some reference to the provided parameters (object type / operation).
    """
    # Arrange: mock POST response
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        "id": "75000000000TESTJOB",
        "object": "Account",
        "operation": "insert",
        "state": "Open",
        "contentType": "CSV",
    }
    mock_sf_client.post.return_value = mock_response

    # Act
    job = BulkApiIngestJob.init_job("Account", "insert", connection=mock_sf_client)

    # Assert: POST called once to ingest jobs endpoint
    assert mock_sf_client.post.call_count == 1, (
        "Expected a single POST to create ingest job"
    )
    request_args, request_kwargs = mock_sf_client.post.call_args
    assert "/jobs/ingest" in request_args[0], (
        "Job creation endpoint should include /jobs/ingest"
    )

    # We don't rely on internal attribute names (they may change); instead assert that
    # the instance __dict__ contains values we passed (defensive against refactors).
    assert job.object == "Account", "Job instance should retain object type information"
    assert job.operation == "insert", "Job instance should retain operation information"


@pytest.mark.asyncio
async def test_bulk_ingest_job_init_job_async(mocker, mock_async_client):
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        "id": "750000000TESTASYNC",
        "object": "Contact",
        "operation": "upsert",
        "state": "Open",
        "contentType": "CSV",
    }
    mock_async_client.post.return_value = mock_response

    job = await BulkApiIngestJob.init_job_async(
        "Contact",
        "upsert",
        external_id_field="External_Id__c",
        connection=mock_async_client,
    )

    assert mock_async_client.post.call_count == 1
    req_args, _ = mock_async_client.post.call_args
    assert "/jobs/ingest" in req_args[0]
    assert job.object == "Contact"
    assert job.operation == "upsert"


def test_bulk_ingest_job_has_expected_api_surface():
    """
    Guard against accidental removal of key attributes / properties that may be set post-init.
    (Since internal names can evolve, we only check for the presence of at least one identifier.)
    """
    job = BulkApiIngestJob.__new__(BulkApiIngestJob)  # bypass __init__
    # Before init, ensure methods still accessible
    for method in INGEST_JOB_METHODS_SYNC + INGEST_JOB_METHODS_ASYNC:
        assert hasattr(job, method), f"Ingest job instance missing method {method}"


def test_bulk_module_public_classes():
    # Ensure classes are actually classes (not replaced / aliased incorrectly).
    for cls in [BulkApiIngestJob, BulkApiQueryJob, BulkQueryResult, ResultPage]:
        assert inspect.isclass(cls), f"{cls} should be a class"


def test_bulk_query_result_iter_protocol_presence():
    assert hasattr(BulkQueryResult, "__iter__"), (
        "BulkQueryResult should implement __iter__"
    )
    assert hasattr(BulkQueryResult, "__next__"), (
        "BulkQueryResult should implement __next__"
    )
    assert hasattr(BulkQueryResult, "__aiter__"), (
        "BulkQueryResult should implement __aiter__"
    )
    assert hasattr(BulkQueryResult, "__anext__"), (
        "BulkQueryResult should implement __anext__"
    )


def test_result_page_iter_protocol_presence():
    assert hasattr(ResultPage, "__iter__"), "ResultPage should implement __iter__"
    assert hasattr(ResultPage, "__next__"), "ResultPage should implement __next__"
    assert hasattr(ResultPage, "__aiter__"), "ResultPage should implement __aiter__"
    assert hasattr(ResultPage, "__anext__"), "ResultPage should implement __anext__"


@pytest.mark.usefixtures("mock_sf_client")
def test_bulk_ingest_job_monitor_until_complete_success(mocker):
    """
    Ensure monitor_until_complete repeatedly refreshes until a terminal success state is reached.
    We simulate state transitions without performing real HTTP calls.
    """
    job = BulkApiIngestJob.__new__(BulkApiIngestJob)
    job._values = {}
    job.state = "UploadComplete"  # initial non-terminal state

    # Simulated sequence of states leading to completion
    next_states = iter(["InProgress", "JobComplete"])

    def advance_state(*_, **_kw):
        try:
            job.state = next(next_states)
        except StopIteration:
            pass
        return job

    refresh_mock = mocker.Mock(side_effect=advance_state)
    job.refresh = refresh_mock  # replace actual refresh logic

    # Avoid real sleeping
    mocker.patch("time.sleep", return_value=None)

    result = job.monitor_until_complete(poll_interval=0)

    assert result is job, "monitor_until_complete should return the job instance"
    assert job.state == "JobComplete", (
        "Final state should be JobComplete (success terminal state)"
    )
    assert refresh_mock.call_count == 2, (
        "Expected exactly two refresh cycles to reach completion"
    )


@pytest.mark.asyncio
async def test_bulk_ingest_job_monitor_until_complete_async_success(mocker):
    """
    Async variant: ensure monitor_until_complete_async awaits refresh_async until terminal state.
    """
    job = BulkApiIngestJob.__new__(BulkApiIngestJob)
    job._values = {}
    job.state = "UploadComplete"

    next_states = iter(["InProgress", "JobComplete"])

    def advance_state_async(*_, **_kw):
        try:
            job.state = next(next_states)
        except StopIteration:
            pass
        return job

    refresh_async_mock = mocker.AsyncMock(side_effect=advance_state_async)
    job.refresh_async = refresh_async_mock

    # Patch asyncio.sleep to avoid delays
    mocker.patch("sf_toolkit.data.bulk.sleep_async", side_effect=lambda _: None)
    result = await job.monitor_until_complete_async()

    assert result is job, "monitor_until_complete_async should return the job instance"
    assert job.state == "JobComplete", "Final state should be JobComplete"
    assert refresh_async_mock.call_count == 2, (
        "Expected two async refresh cycles to reach completion"
    )


def _build_mock_csv(records):
    # Helper for building a deterministic CSV payload from list[dict]
    if not records:
        return ""
    headers = list(records[0].keys())
    lines = [",".join(headers)]
    for r in records:
        row = []
        for h in headers:
            val = r.get(h, "")
            if val is None:
                val = ""
            row.append(str(val))
        lines.append(",".join(row))
    return "\n".join(lines) + "\n"


def _assert_results_structure(result, expected_len):
    # Be tolerant about the library's return type (list[dict] vs raw text)
    assert isinstance(result, list), "Results should be returned as a list"
    assert len(result) == expected_len, (
        f"Expected {expected_len} parsed rows, got {len(result)}"
    )


def _prepare_job_with_connection(mocker, mock_sf_client, job_id="750XXXXXTESTJOB"):
    job = BulkApiIngestJob.__new__(BulkApiIngestJob)
    job._values = {}
    job.id = job_id
    # Simulate what init_job would normally attach
    job._connection = mock_sf_client
    return job


def test_bulk_ingest_job_successful_results_fetch(mocker, mock_sf_client):
    """
    Ensure calling successful_results() hits the expected ingest job endpoint and returns
    a structure representing each successful record (parsed list or raw CSV text).
    """
    job = _prepare_job_with_connection(mocker, mock_sf_client)
    rows = [
        {"sf__Id": "001000000000001", "sf__Created": "true"},
        {"sf__Id": "001000000000002", "sf__Created": "false"},
    ]
    csv_payload = _build_mock_csv(rows)
    mock_response = mocker.Mock()
    mock_response.text = csv_payload
    mock_sf_client.get.return_value = mock_response

    assert hasattr(job, "successful_results"), (
        "BulkApiIngestJob should expose successful_results()"
    )
    result = job.successful_results()

    assert mock_sf_client.get.call_count == 1, (
        "Expected a single GET for successful results"
    )
    url = mock_sf_client.get.call_args[0][0]
    assert job.id in url, "Request URL should include the job id"
    assert "successfulResults" in url, "Endpoint should target successfulResults"
    _assert_results_structure(result, expected_len=2)


def test_bulk_ingest_job_failed_results_fetch(mocker, mock_sf_client):
    """
    Ensure calling failed_results() hits the expected endpoint and returns failed rows.
    """
    job = _prepare_job_with_connection(mocker, mock_sf_client)
    rows = [
        {
            "sf__Id": "001000000000101",
            "sf__Error": "REQUIRED_FIELD_MISSING: Name",
        }
    ]
    csv_payload = _build_mock_csv(rows)
    mock_response = mocker.Mock()
    mock_response.text = csv_payload
    mock_sf_client.get.return_value = mock_response

    # Method name tolerance: some APIs might use failed_results vs failed_records
    method_name = None
    for candidate in ("failed_results", "failed_records"):
        if hasattr(job, candidate):
            method_name = candidate
            break
    assert method_name, (
        "BulkApiIngestJob should expose a failed results retrieval method"
    )
    method = getattr(job, method_name)
    result = method()

    assert mock_sf_client.get.call_count == 1, (
        "Expected a single GET for failed results"
    )
    url = mock_sf_client.get.call_args[0][0]
    assert job.id in url, "Request URL should include the job id"
    assert "failedResults" in url, "Endpoint should target failedResults"
    _assert_results_structure(result, expected_len=1)


def test_bulk_ingest_job_unprocessed_results_fetch(mocker, mock_sf_client):
    """
    Ensure calling unprocessed/unprocessed_records (uncompleted) results retrieval method
    hits the expected endpoint and returns remaining rows not processed.
    """
    job = _prepare_job_with_connection(mocker, mock_sf_client)
    rows = [
        {"Id": "001000000000201", "Success": "", "Created": "", "Error": ""},
        {"Id": "001000000000202", "Success": "", "Created": "", "Error": ""},
    ]
    csv_payload = _build_mock_csv(rows)
    mock_response = mocker.Mock()
    mock_response.text = csv_payload
    mock_sf_client.get.return_value = mock_response

    # Accept several possible method names referencing "unprocessed" or "uncompleted"
    method_name = None
    for candidate in (
        "unprocessed_records",
        "unprocessed_results",
        "uncompleted_records",
        "uncompleted_results",
    ):
        if hasattr(job, candidate):
            method_name = candidate
            break
    assert method_name, (
        "BulkApiIngestJob should expose a method to fetch unprocessed/uncompleted records"
    )
    method = getattr(job, method_name)
    result = method()

    assert mock_sf_client.get.call_count == 1, (
        "Expected a single GET for unprocessed/uncompleted results"
    )
    url = mock_sf_client.get.call_args[0][0]
    assert job.id in url, "Request URL should include the job id"
    # Salesforce endpoint segment is 'unprocessedrecords'
    assert "unprocessedrecords" in url.lower(), (
        "Endpoint should target unprocessedrecords"
    )
    _assert_results_structure(result, expected_len=2)


@pytest.mark.asyncio
async def test_bulk_ingest_job_successful_results_async_fetch(
    mocker, mock_async_client
):
    """
    Async: ensure successful_results_async() hits the expected endpoint and returns parsed / raw data.
    """
    job = _prepare_job_with_connection(mocker, mock_async_client)
    rows = [
        {"sf__Id": "001000000000301", "sf__Created": "true"},
        {"sf__Id": "001000000000302", "sf__Created": "false"},
    ]
    csv_payload = _build_mock_csv(rows)
    mock_response = mocker.Mock()
    mock_response.text = csv_payload
    mock_async_client.get.return_value = mock_response

    assert hasattr(job, "successful_results_async"), (
        "BulkApiIngestJob should expose successful_results_async()"
    )
    result = await job.successful_results_async()

    assert mock_async_client.get.call_count == 1, (
        "Expected one async GET for successful results"
    )
    url = mock_async_client.get.call_args[0][0]
    assert job.id in url
    assert "successfulResults" in url
    _assert_results_structure(result, expected_len=2)


@pytest.mark.asyncio
async def test_bulk_ingest_job_failed_results_async_fetch(mocker, mock_async_client):
    """
    Async: ensure failed_results_async() (or tolerated alias) hits expected endpoint.
    """
    job = _prepare_job_with_connection(mocker, mock_async_client)
    rows = [
        {
            "sf__Id": "001000000000401",
            "sf__Created": "false",
            "sf__Error": "DUPLICATE_VALUE: External Id",
            "Other_Field__c": "Something",
        }
    ]
    csv_payload = _build_mock_csv(rows)
    mock_response = mocker.Mock()
    mock_response.text = csv_payload
    mock_async_client.get.return_value = mock_response

    method_name = None
    for candidate in ("failed_results_async", "failed_records_async"):
        if hasattr(job, candidate):
            method_name = candidate
            break
    assert method_name, (
        "BulkApiIngestJob should expose an async failed results retrieval method"
    )

    method = getattr(job, method_name)
    result = await method()

    assert mock_async_client.get.call_count == 1, (
        "Expected one async GET for failed results"
    )
    url = mock_async_client.get.call_args[0][0]
    assert job.id in url
    assert "failedResults" in url
    _assert_results_structure(result, expected_len=1)


@pytest.mark.asyncio
async def test_bulk_ingest_job_unprocessed_results_async_fetch(
    mocker, mock_async_client
):
    """
    Async: ensure unprocessed/uncompleted async retrieval method hits expected endpoint.
    """
    job = _prepare_job_with_connection(mocker, mock_async_client)
    rows = [
        {"Id": "001000000000501", "Success": "", "Created": "", "Error": ""},
        {"Id": "001000000000502", "Success": "", "Created": "", "Error": ""},
        {"Id": "001000000000503", "Success": "", "Created": "", "Error": ""},
    ]
    csv_payload = _build_mock_csv(rows)
    mock_response = mocker.Mock()
    mock_response.text = csv_payload
    mock_async_client.get.return_value = mock_response

    method_name = None
    for candidate in (
        "unprocessed_results_async",
        "unprocessed_records_async",
        "uncompleted_results_async",
        "uncompleted_records_async",
    ):
        if hasattr(job, candidate):
            method_name = candidate
            break
    assert method_name, (
        "BulkApiIngestJob should expose an async method to fetch unprocessed/uncompleted records"
    )

    method = getattr(job, method_name)
    result = await method()

    assert mock_async_client.get.call_count == 1, (
        "Expected one async GET for unprocessed results"
    )
    url = mock_async_client.get.call_args[0][0]
    assert job.id in url
    assert "unprocessedrecords" in url.lower()
    _assert_results_structure(result, expected_len=3)
