from pathlib import Path
from typing import ClassVar
from urllib.parse import quote_plus

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock

from sf_toolkit.data.fields import TextField
from sf_toolkit.io.api import (
    fetch,
    save_insert,
    save_update,
    save_upsert,
    save_list,
)
from sf_toolkit.io.file import (
    to_json_file,
    from_json_file,
    to_csv_file,
    from_csv_file,
    to_file,
    from_file,
)
from sf_toolkit._models import SObjectSaveResult
from sf_toolkit.data.sobject import SObject, SObjectList


@pytest.fixture
def simple_sobject(monkeypatch):
    class Simple(SObject, api_name="Simple__c"):
        Id: ClassVar[TextField] = TextField()
        Name: ClassVar[TextField] = TextField()
        External_Id__c: ClassVar[TextField] = TextField()

    yield Simple


@pytest.fixture
def record(simple_sobject):
    return simple_sobject()


# ---------------------------------------------------------------------------
# Tests for fetch
# ---------------------------------------------------------------------------


def test_fetch_builds_correct_url_and_returns_instance(simple_sobject, mock_sf_client):
    # Arrange
    record_id = "001ABC"
    expected_url = (
        f"{mock_sf_client.sobjects_url}/{simple_sobject.attributes.type}/{record_id}"
    )

    mock_sf_client.get.return_value.json.return_value = {
        "Id": record_id,
        "Name": "Fetched",
        "External_Id__c": "EXT1",
    }

    # Act
    result = fetch(simple_sobject, record_id, sf_client=mock_sf_client)

    # Assert
    assert isinstance(result, simple_sobject)
    assert result.Id == record_id
    assert mock_sf_client.get.call_count == 1
    called_url = (
        mock_sf_client.get.call_args.kwargs.get("url")
        or mock_sf_client.get.call_args.args[0]
    )
    params = mock_sf_client.get.call_args.kwargs.get("params")
    assert called_url == expected_url
    # fields param present (may be empty string if object_fields empty, but here we patched)
    assert set(params["fields"].split(",")) == {"Id", "Name", "External_Id__c"}


# ---------------------------------------------------------------------------
# Tests for save_insert
# ---------------------------------------------------------------------------


def test_save_insert_sets_id_and_clears_dirty(record, mock_sf_client):
    mock_sf_client.post.return_value.json.return_value = {"id": "001NEW"}
    # Pre-mutate a field so dirty set not empty
    record.Name = "Initial"
    from sf_toolkit.io.api import dirty_fields, serialize_object

    assert dirty_fields(record)  # dirty before

    save_insert(record, sf_client=mock_sf_client)

    assert record.Id == "001NEW"
    assert not dirty_fields(record)  # cleared
    # post called with correct URL
    expected_url = f"{mock_sf_client.sobjects_url}/{record.attributes.type}"
    called_url = (
        mock_sf_client.post.call_args.kwargs.get("url")
        or mock_sf_client.post.call_args.args[0]
    )
    assert called_url == expected_url
    payload = mock_sf_client.post.call_args.kwargs.get("json")
    # Insert should not include Id since it is not set prior
    assert "Id" not in payload


def test_save_insert_raises_if_id_present(record, mock_sf_client):
    record.Id = "EXISTING"
    with pytest.raises(ValueError):
        save_insert(record, sf_client=mock_sf_client)


# ---------------------------------------------------------------------------
# Tests for save_update
# ---------------------------------------------------------------------------


def test_save_update_only_changes(record, mock_sf_client, monkeypatch):
    # Setup record with existing Id
    record.Id = "001UPDATE"
    record.Name = "Original"
    # clear dirty after initial set
    from sf_toolkit.io.api import dirty_fields

    dirty_fields(record).clear()
    # mutate Name
    record.Name = "Changed"

    # Capture json payload passed to patch
    mock_sf_client.patch.return_value = MagicMock(is_success=True)

    save_update(record, sf_client=mock_sf_client, only_changes=True)

    assert mock_sf_client.patch.call_count == 1
    kwargs = mock_sf_client.patch.call_args.kwargs
    payload = kwargs.get("json")
    # Id should be stripped out
    assert "Id" not in payload
    # Only changed field present
    assert payload == {"Name": "Changed"}


def test_save_update_no_dirty_fields_only_changes_skips_call(record, mock_sf_client):
    record.Id = "001NOCHANGE"
    from sf_toolkit.io.api import dirty_fields

    dirty_fields(record).clear()  # Ensure empty dirty set
    save_update(record, sf_client=mock_sf_client, only_changes=True)
    mock_sf_client.patch.assert_not_called()


def test_save_update_raises_without_id(record, mock_sf_client):
    with pytest.raises(ValueError):
        save_update(record, sf_client=mock_sf_client)


# ---------------------------------------------------------------------------
# Tests for save_upsert
# ---------------------------------------------------------------------------


def test_save_upsert_inserts_when_no_id(record, mock_sf_client):
    record.External_Id__c = "EXT-123"
    mock_sf_client.patch.return_value.is_success = True
    mock_sf_client.patch.return_value.json.return_value = {"id": "001UPSERT"}

    save_upsert(record, "External_Id__c", sf_client=mock_sf_client)

    assert record.Id == "001UPSERT"
    called_url = mock_sf_client.patch.call_args.args[0]
    assert called_url.endswith(
        f"/{record.attributes.type}/External_Id__c/{quote_plus('EXT-123')}"
    )


def test_save_upsert_requires_external_id(record, mock_sf_client):
    with pytest.raises(ValueError):
        save_upsert(record, "External_Id__c", sf_client=mock_sf_client)


# ---------------------------------------------------------------------------
# Tests for save_list orchestration
# ---------------------------------------------------------------------------


def test_save_list_mixed_insert_and_update(simple_sobject, monkeypatch):
    # Prepare three records: two updates, one insert
    r1 = simple_sobject(Id="001A")
    r2 = simple_sobject()
    r3 = simple_sobject(Id="001C")
    records = SObjectList([r1, r2, r3], connection="test")

    # Monkeypatch internal helpers to observe calls
    called = {}

    def fake_save_update_list(objs, **kw):
        called.setdefault("update", []).append((objs, kw))
        return [
            SObjectSaveResult(id=o.Id, success=True, errors=[], created=False)
            for o in objs
        ]

    def fake_save_insert_list(objs, **kw):
        called.setdefault("insert", []).append((objs, kw))
        # simulate new ids
        for idx, o in enumerate(objs, start=1):
            o.Id = f"NEW{idx}"
        return [
            SObjectSaveResult(id=o.Id, success=True, errors=[], created=True)
            for o in objs
        ]

    monkeypatch.setattr("sf_toolkit.io.api.save_update_list", fake_save_update_list)
    monkeypatch.setattr("sf_toolkit.io.api.save_insert_list", fake_save_insert_list)

    results = save_list(records)

    # Expect both helpers called
    assert "update" in called and "insert" in called
    assert len(results) == 3
    # Inserted record got an Id
    assert r2.Id.startswith("NEW")


def test_save_list_all_updates(simple_sobject, monkeypatch):
    r1 = simple_sobject(Id="001")
    r2 = simple_sobject(Id="002")
    lst = SObjectList([r1, r2], connection="test")

    called = {}

    def fake_save_update_list(objs, **kw):
        called["update"] = True
        return [
            SObjectSaveResult(id=o.Id, success=True, errors=[], created=False)
            for o in objs
        ]

    monkeypatch.setattr("sf_toolkit.io.api.save_update_list", fake_save_update_list)

    results = save_list(lst)
    assert called.get("update")
    assert all(not r.created for r in results)


def test_save_list_all_inserts(simple_sobject, monkeypatch):
    r1 = simple_sobject()
    r2 = simple_sobject()
    lst = SObjectList([r1, r2], connection="test")

    called = {}

    def fake_save_insert_list(objs, **kw):
        called["insert"] = True
        for i, o in enumerate(objs, 1):
            o.Id = f"00NEW{i}"
        return [
            SObjectSaveResult(id=o.Id, success=True, errors=[], created=True)
            for o in objs
        ]

    monkeypatch.setattr("sf_toolkit.io.api.save_insert_list", fake_save_insert_list)

    results = save_list(lst)
    assert called.get("insert")
    assert all(r.created for r in results)


# ---------------------------------------------------------------------------
# Tests for file IO helpers
# ---------------------------------------------------------------------------


def _build_records(simple_sobject):
    r1 = simple_sobject(Id="001", Name="Alpha", External_Id__c="E1")
    r2 = simple_sobject(Id="002", Name="Beta", External_Id__c="E2")
    return SObjectList([r1, r2], connection="test")


def test_json_round_trip(tmp_path: Path, simple_sobject):
    records = _build_records(simple_sobject)
    filepath = tmp_path / "records.json"
    to_json_file(records, filepath, indent=2)
    loaded = from_json_file(simple_sobject, filepath)
    assert len(loaded) == len(records)
    assert {r.Id for r in loaded} == {"001", "002"}


def test_csv_round_trip(tmp_path: Path, simple_sobject):
    records = _build_records(simple_sobject)
    filepath = tmp_path / "records.csv"
    to_csv_file(records, filepath)
    loaded = from_csv_file(simple_sobject, filepath)
    assert len(loaded) == 2
    assert {r.Id for r in loaded} == {"001", "002"}


def test_to_file_and_from_file_json(tmp_path: Path, simple_sobject):
    records = _build_records(simple_sobject)
    filepath = tmp_path / "generic.json"
    to_file(records, filepath)
    loaded = from_file(simple_sobject, filepath)
    assert len(loaded) == 2


def test_to_file_and_from_file_csv(tmp_path: Path, simple_sobject):
    records = _build_records(simple_sobject)
    filepath = tmp_path / "generic.csv"
    to_file(records, filepath)
    loaded = from_file(simple_sobject, filepath)
    assert len(loaded) == 2


def test_from_file_unsupported_extension(tmp_path: Path, simple_sobject):
    bad = tmp_path / "file.txt"
    bad.write_text("content")
    with pytest.raises(ValueError):
        from_file(simple_sobject, bad)


def test_to_file_unsupported_extension(tmp_path: Path, simple_sobject):
    bad = tmp_path / "file.xyz"
    with pytest.raises(ValueError):
        to_file(_build_records(simple_sobject), bad)


# ---------------------------------------------------------------------------
# Additional tests for io.api to improve coverage
# ---------------------------------------------------------------------------


def test_save_orchestration_paths(simple_sobject, monkeypatch, mock_sf_client):
    from sf_toolkit.io.api import save

    # Track which helper used
    called = {"insert": 0, "update": 0, "upsert": 0}

    def fake_save_insert(rec, sf_client=None, reload_after_success=False):
        called["insert"] += 1
        rec.Id = "NEWID"

    def fake_save_update(
        rec,
        sf_client=None,
        only_changes=False,
        reload_after_success=False,
        only_blob=False,
    ):
        called["update"] += 1

    def fake_save_upsert(
        rec,
        external_id_field,
        sf_client=None,
        reload_after_success=False,
        update_only=False,
        only_changes=False,
    ):
        called["upsert"] += 1
        rec.Id = "UPSERTID"

    monkeypatch.setattr("sf_toolkit.io.api.save_insert", fake_save_insert)
    monkeypatch.setattr("sf_toolkit.io.api.save_update", fake_save_update)
    monkeypatch.setattr("sf_toolkit.io.api.save_upsert", fake_save_upsert)

    # Insert path (no Id, no external id)
    r_insert = simple_sobject()
    save(r_insert, sf_client=mock_sf_client)
    assert r_insert.Id == "NEWID"

    # Update path (Id present)
    r_update = simple_sobject(Id="001X")
    save(r_update, sf_client=mock_sf_client)
    assert called["update"] == 1

    # Upsert path (no Id but external id provided)
    r_upsert = simple_sobject(External_Id__c="EXT-X")
    save(r_upsert, sf_client=mock_sf_client, external_id_field="External_Id__c")
    assert r_upsert.Id == "UPSERTID"

    # update_only flag with no Id & no external id should raise
    r_bad = simple_sobject()
    with pytest.raises(ValueError):
        save(r_bad, sf_client=mock_sf_client, update_only=True)

    assert called == {"insert": 1, "update": 1, "upsert": 1}


def test_save_upsert_list_success_and_dirty_clear(
    simple_sobject, monkeypatch, mock_sf_client
):
    from sf_toolkit.io.api import save_upsert_list, dirty_fields

    # Prepare records with external ids
    records = [simple_sobject(External_Id__c=f"EXT{i}", Name=f"N{i}") for i in range(3)]
    # Mark all fields dirty
    for r in records:
        dirty_fields(r).update(["External_Id__c", "Name"])

    # Mock resolve_client to use our provided client
    monkeypatch.setattr(
        "sf_toolkit.io.api.resolve_client", lambda cls, client=None: mock_sf_client
    )

    # Prepare patch responses (one batch only)
    mock_sf_client.patch.return_value.json.return_value = [
        {"id": f"001{i}", "success": True, "errors": [], "created": True}
        for i in range(3)
    ]

    results = save_upsert_list(
        SObjectList(records, connection="test"), external_id_field="External_Id__c"
    )
    assert len(results) == 3
    assert mock_sf_client.patch.call_count == 1
    # All dirty fields cleared
    for r in records:
        assert not dirty_fields(r)


def test_save_upsert_list_missing_external_id_raises(
    simple_sobject, monkeypatch, mock_sf_client
):
    from sf_toolkit.io.api import save_upsert_list

    r1 = simple_sobject(External_Id__c="EXT1")
    r2 = simple_sobject()  # missing external id
    lst = SObjectList([r1, r2], connection="test")

    monkeypatch.setattr(
        "sf_toolkit.io.api.resolve_client", lambda cls, client=None: mock_sf_client
    )

    with pytest.raises(AssertionError):
        save_upsert_list(lst, external_id_field="External_Id__c")


def test_save_update_list_requires_ids(simple_sobject, monkeypatch):
    from sf_toolkit.io.api import save_update_list

    r1 = simple_sobject(Id="001")
    r2 = simple_sobject()  # missing Id
    lst = SObjectList([r1, r2], connection="test")

    with pytest.raises(ValueError):
        save_update_list(lst)


def test_save_update_list_clears_dirty_fields(
    simple_sobject, monkeypatch, mock_sf_client
):
    from sf_toolkit.io.api import save_update_list, dirty_fields

    r1 = simple_sobject(Id="001", Name="A")
    r2 = simple_sobject(Id="002", Name="B")
    lst = SObjectList([r1, r2], connection="test")

    # Mark names dirty
    dirty_fields(r1).add("Name")
    dirty_fields(r2).add("Name")

    monkeypatch.setattr(
        "sf_toolkit.io.api.resolve_client", lambda cls, client=None: mock_sf_client
    )
    mock_sf_client.patch.return_value.json.return_value = [
        {"id": "001", "success": True, "errors": [], "created": False},
        {"id": "002", "success": True, "errors": [], "created": False},
    ]

    results = save_update_list(lst, only_changes=True)
    assert len(results) == 2
    assert mock_sf_client.patch.call_count == 1
    assert not dirty_fields(r1)
    assert not dirty_fields(r2)


def test_fetch_list_batches(simple_sobject, mock_sf_client):
    from sf_toolkit.io.api import fetch_list

    # Build >2000 ids to force batching (2000 + 1)
    ids = [f"ID{i}" for i in range(2001)]

    # Prepare two responses
    first_batch = [
        {"Id": f"ID{i}", "Name": f"Name{i}", "External_Id__c": f"EXT{i}"}
        for i in range(2000)
    ]
    second_batch = [{"Id": "ID2000", "Name": "Name2000", "External_Id__c": "EXT2000"}]

    # side_effect returns MagicMock with .json()
    resp1 = MagicMock()
    resp1.json.return_value = first_batch
    resp2 = MagicMock()
    resp2.json.return_value = second_batch
    mock_sf_client.post.side_effect = [resp1, resp2]

    result_list = fetch_list(simple_sobject, *ids, sf_client=mock_sf_client)
    assert len(result_list) == 2001
    assert mock_sf_client.post.call_count == 2
    assert {r.Id for r in result_list[:3]} == {"ID0", "ID1", "ID2"}


def test_delete_list_batches(monkeypatch, simple_sobject, mock_sf_client):
    from sf_toolkit.io.api import delete_list

    # Create 5 records with ids
    records = SObjectList(
        [simple_sobject(Id=f"001{i}") for i in range(5)],
        connection="test",
    )

    monkeypatch.setattr(
        "sf_toolkit.io.api.resolve_client", lambda cls, client=None: mock_sf_client
    )

    # Prepare delete responses for batches of size 2 (2,2,1)
    batch_results = [
        [
            {"id": "0010", "success": True, "errors": [], "created": False},
            {"id": "0011", "success": True, "errors": [], "created": False},
        ],
        [
            {"id": "0012", "success": True, "errors": [], "created": False},
            {"id": "0013", "success": True, "errors": [], "created": False},
        ],
        [{"id": "0014", "success": True, "errors": [], "created": False}],
    ]
    mock_sf_client.delete.side_effect = [
        MagicMock(json=MagicMock(return_value=br)) for br in batch_results
    ]

    results = delete_list(records, batch_size=2)
    assert len(results) == 5
    assert mock_sf_client.delete.call_count == 3

    # Verify ids param passed for each batch
    called_ids = []
    for call in mock_sf_client.delete.call_args_list:
        params = call.kwargs.get("params")
        called_ids.extend(params["ids"].split(","))
    assert set(called_ids) == {f"001{i}" for i in range(5)}


def test_update_record_helper(simple_sobject):
    from sf_toolkit.io.api import update_record

    rec = simple_sobject(Id="001", Name="Orig", External_Id__c="EXT1")
    # Update existing fields and attempt to set a non-existent field (ignored)
    update_record(rec, Name="NewName", External_Id__c="EXTNEW", MissingField="X")
    assert rec.Name == "NewName"
    assert rec.External_Id__c == "EXTNEW"
    # MissingField should not exist
    assert not hasattr(rec, "MissingField")


def test_save_upsert_list_with_concurrency(simple_sobject, monkeypatch):
    """
    Validate that save_upsert_list chooses async path when concurrency >1 and multiple batches.
    """
    from sf_toolkit.io.api import save_upsert_list

    # Create > batch_size records so we have multiple batches
    batch_size = 2
    records = SObjectList(
        [simple_sobject(External_Id__c=f"E{i}", Name=f"N{i}") for i in range(5)],
        connection="test",
    )

    # Monkeypatch resolve_async_client for async branch plus async helper
    mock_async_client = MagicMock()
    mock_async_client.patch.return_value.json.return_value = [
        {"id": f"001{i}", "success": True, "errors": [], "created": True}
        for i in range(batch_size)
    ]

    monkeypatch.setattr(
        "sf_toolkit.io.api.resolve_client", lambda cls, client=None: mock_async_client
    )
    monkeypatch.setattr(
        "sf_toolkit.io.api.resolve_async_client",
        lambda cls, client=None: mock_async_client,
    )

    # Fake async executor to run tasks immediately
    async def fake_run_concurrently(concurrency, tasks, *a, **k):
        return [t for t in tasks]  # tasks are already awaited objects (MagicMocks)

    monkeypatch.setattr("sf_toolkit.io.api.run_concurrently", fake_run_concurrently)

    # Patch async chunk function used by upsert list
    async def fake_save_upsert_chunks(
        client, url, chunks, headers, concurrency, all_or_none, **opts
    ):
        # Return success objects flattening all chunks
        results = []
        counter = 0
        for chunk in chunks:
            for _ in chunk:
                results.append(
                    type(
                        "R",
                        (),
                        {
                            "json": lambda self=None: [
                                {
                                    "id": f"ID{counter}",
                                    "success": True,
                                    "errors": [],
                                    "created": True,
                                }
                            ]
                        },
                    )()
                )
                counter += 1
        # Flatten into SObjectSaveResult items
        from sf_toolkit._models import SObjectSaveResult

        flat = []
        for resp in results:
            flat.extend(SObjectSaveResult(**r) for r in resp.json())
        return flat

    monkeypatch.setattr(
        "sf_toolkit.io.api._save_upsert_list_chunks_async", fake_save_upsert_chunks
    )

    res = save_upsert_list(
        records,
        external_id_field="External_Id__c",
        concurrency=2,
        batch_size=batch_size,
    )
    assert len(res) == 5
    assert (
        mock_async_client.patch.call_count == 0
    )  # async helper bypassed direct patch path


def test_save_function_with_external_id_only_changes(
    simple_sobject, monkeypatch, mock_sf_client
):
    from sf_toolkit.io.api import save, dirty_fields

    rec = simple_sobject(External_Id__c="EXT100")
    rec.Name = "Initial"
    # Mark only Name dirty
    monkeypatch.setattr(
        "sf_toolkit.io.api.save_upsert", lambda *a, **k: setattr(rec, "Id", "001XYZ")
    )
    save(
        rec,
        sf_client=mock_sf_client,
        external_id_field="External_Id__c",
        only_changes=True,
    )
    assert rec.Id == "001XYZ"


def test_save_insert_list_with_all_or_none(simple_sobject, monkeypatch, mock_sf_client):
    from sf_toolkit.io.api import save_insert_list

    recs = SObjectList(
        [simple_sobject(Name="A"), simple_sobject(Name="B")], connection="test"
    )
    monkeypatch.setattr(
        "sf_toolkit.io.api.resolve_client", lambda cls, client=None: mock_sf_client
    )

    mock_sf_client.post.return_value.json.return_value = [
        {"id": "001A", "success": True, "errors": [], "created": True},
        {"id": "001B", "success": True, "errors": [], "created": True},
    ]

    results = save_insert_list(recs, all_or_none=True)
    assert len(results) == 2
    assert recs[0].Id == "001A"
    assert recs[1].Id == "001B"
    # Confirm allOrNone flag passed
    payload = mock_sf_client.post.call_args.kwargs.get("json")
    assert payload["allOrNone"] is True


def test_delete_list_clear_id_field(simple_sobject, monkeypatch, mock_sf_client):
    from sf_toolkit.io.api import delete_list

    recs = SObjectList(
        [simple_sobject(Id="001"), simple_sobject(Id="002")], connection="test"
    )
    monkeypatch.setattr(
        "sf_toolkit.io.api.resolve_client", lambda cls, client=None: mock_sf_client
    )
    mock_sf_client.delete.return_value.json.return_value = [
        {"id": "001", "success": True, "errors": [], "created": False},
        {"id": "002", "success": True, "errors": [], "created": False},
    ]
    delete_list(recs, clear_id_field=True)
    assert recs[0].Id is None
    assert recs[1].Id is None


def test_save_update_list_empty_returns_empty(simple_sobject):
    from sf_toolkit.io.api import save_update_list

    empty = SObjectList([], connection="test")
    assert save_update_list(empty) == []


def test_save_upsert_list_empty_returns_empty(simple_sobject):
    from sf_toolkit.io.api import save_upsert_list

    empty = SObjectList([], connection="test")
    assert save_upsert_list(empty, external_id_field="External_Id__c") == []


def test_save_list_empty_returns_empty():
    empty = SObjectList([], connection="test")
    assert save_list(empty) == []


def test_delete_removes_id_and_calls_delete(simple_sobject, mock_sf_client):
    from sf_toolkit.io.api import delete

    rec = simple_sobject(Id="001DEL")
    # Chain .raise_for_status()
    mock_sf_client.delete.return_value.raise_for_status.return_value = None

    delete(rec, sf_client=mock_sf_client)

    assert mock_sf_client.delete.call_count == 1
    # Id attribute value should be cleared
    assert rec.Id is None


def test_delete_raises_without_id(simple_sobject, mock_sf_client):
    from sf_toolkit.io.api import delete

    rec = simple_sobject()
    with pytest.raises(ValueError):
        delete(rec, sf_client=mock_sf_client)


@pytest.mark.asyncio
async def test_fetch_async_builds_correct_url_and_returns_instance(
    simple_sobject, mock_async_client
):
    from sf_toolkit.io.api import fetch_async
    from unittest.mock import AsyncMock

    record_id = "001ASYNC"
    expected_url = (
        f"{mock_async_client.sobjects_url}/{simple_sobject.attributes.type}/{record_id}"
    )

    mock_async_client.get = AsyncMock()
    mock_async_client.get.return_value = MagicMock()
    mock_async_client.get.return_value.json.return_value = {
        "Id": record_id,
        "Name": "FetchedAsync",
        "External_Id__c": "EXTA",
    }

    result = await fetch_async(simple_sobject, record_id, sf_client=mock_async_client)
    assert isinstance(result, simple_sobject)
    called_url = (
        mock_async_client.get.call_args.kwargs.get("url")
        or mock_async_client.get.call_args.args[0]
    )
    params = mock_async_client.get.call_args.kwargs.get("params")
    assert called_url == expected_url
    assert set(params["fields"].split(",")) == {"Id", "Name", "External_Id__c"}


def test_delete_async_removes_id_and_calls_delete(simple_sobject, mock_async_client):
    from sf_toolkit.io.api import delete_async
    from unittest.mock import AsyncMock
    import asyncio

    rec = simple_sobject(Id="001DELASYNC")
    mock_async_client.delete = AsyncMock()
    mock_async_client.delete.return_value.raise_for_status.return_value = None

    asyncio.run(delete_async(rec, sf_client=mock_async_client))
    assert mock_async_client.delete.call_count == 1
    assert rec.Id is None


def test_reload_updates_fields(simple_sobject, monkeypatch, mock_sf_client):
    from sf_toolkit.io.api import reload

    rec = simple_sobject(Id="001RELOAD", Name="Old")
    # When reload calls fetch, return new object
    monkeypatch.setattr(
        "sf_toolkit.io.api.fetch",
        lambda cls, rid, sf_client=None: simple_sobject(Id=rid, Name="NewName"),
    )
    reload(rec)
    assert rec.Name == "NewName"


def test_reload_async_updates_fields(simple_sobject, monkeypatch, mock_async_client):
    from sf_toolkit.io.api import reload_async
    import asyncio

    rec = simple_sobject(Id="001RELOADA", Name="OldA")

    async def fake_fetch_async(cls, rid, sf_client=None):
        return simple_sobject(Id=rid, Name="NewAsync")

    monkeypatch.setattr("sf_toolkit.io.api.fetch_async", fake_fetch_async)
    asyncio.run(reload_async(rec, mock_async_client))
    assert rec.Name == "NewAsync"


def test_sobject_describe_builds_correct_url(
    simple_sobject, monkeypatch, mock_sf_client
):
    from sf_toolkit.io.api import sobject_describe

    # Patch resolve_client to return our mock client
    monkeypatch.setattr(
        "sf_toolkit.io.api.resolve_client", lambda cls, client=None: mock_sf_client
    )
    mock_sf_client.get.return_value.json.return_value = {
        "fields": [],
        "label": "Simple",
    }

    desc = sobject_describe(simple_sobject)
    assert isinstance(desc, dict)
    called_url = (
        mock_sf_client.get.call_args.kwargs.get("url")
        or mock_sf_client.get.call_args.args[0]
    )
    assert called_url.endswith("/Simple__c/describe")


def test_save_upsert_update_only_not_found_raises(simple_sobject, mock_sf_client):
    from sf_toolkit.io.api import save_upsert

    rec = simple_sobject(External_Id__c="EXT404", Name="Name404")
    # Simulate 404 response when update_only=True
    mock_sf_client.patch.return_value.is_success = False
    mock_sf_client.patch.return_value.status_code = 404
    with pytest.raises(ValueError):
        save_upsert(rec, "External_Id__c", sf_client=mock_sf_client, update_only=True)


def test_save_upsert_only_changes_no_payload_skips_call(
    simple_sobject, mock_sf_client, monkeypatch
):
    from sf_toolkit.io.api import save_upsert, dirty_fields

    rec = simple_sobject(External_Id__c="EXTNOCHANGE")
    # Mark external id dirty then clear so only_changes yields empty payload
    dirty_fields(rec).clear()
    save_upsert(rec, "External_Id__c", sf_client=mock_sf_client, only_changes=True)
    # No patch call because nothing to update
    assert mock_sf_client.patch.call_count == 0


def test_fetch_list_async_batches(simple_sobject, mock_async_client, monkeypatch):
    from sf_toolkit.io.api import fetch_list_async
    from unittest.mock import AsyncMock
    import asyncio

    ids = [f"IDA{i}" for i in range(2500)]  # 2 batches (2000 + 500)

    batch1 = [
        {"Id": f"IDA{i}", "Name": f"Name{i}", "External_Id__c": f"EXT{i}"}
        for i in range(2000)
    ]
    batch2 = [
        {"Id": f"IDA{i}", "Name": f"Name{i}", "External_Id__c": f"EXT{i}"}
        for i in range(2000, 2500)
    ]

    # Post returns two responses
    resp1 = MagicMock()
    resp1.json.return_value = batch1
    resp2 = MagicMock()
    resp2.json.return_value = batch2

    mock_async_client.post = AsyncMock(side_effect=[resp1, resp2])

    result = asyncio.run(
        fetch_list_async(simple_sobject, *ids, sf_client=mock_async_client)
    )
    assert len(result) == 2500
    assert mock_async_client.post.call_count == 2


def test_delete_list_async_batches(simple_sobject, mock_async_client, monkeypatch):
    from sf_toolkit.io.api import delete_list_async
    from unittest.mock import AsyncMock
    import asyncio

    recs = [simple_sobject(Id=f"DEL{i}") for i in range(5)]
    lst = SObjectList(recs, connection="test")

    # 3 batches if batch_size=2
    batches = [
        [
            {"id": "DEL0", "success": True, "errors": [], "created": False},
            {"id": "DEL1", "success": True, "errors": [], "created": False},
        ],
        [
            {"id": "DEL2", "success": True, "errors": [], "created": False},
            {"id": "DEL3", "success": True, "errors": [], "created": False},
        ],
        [{"id": "DEL4", "success": True, "errors": [], "created": False}],
    ]
    mock_async_client.delete = AsyncMock(
        side_effect=[MagicMock(json=MagicMock(return_value=b)) for b in batches]
    )
    monkeypatch.setattr(
        "sf_toolkit.io.api.resolve_async_client",
        lambda cls, client=None: mock_async_client,
    )
    results = asyncio.run(delete_list_async(lst, batch_size=2, concurrency=2))
    assert len(results) == 5
    assert mock_async_client.delete.call_count == 3


def test_save_upsert_list_async_success(simple_sobject, mock_async_client, monkeypatch):
    from sf_toolkit.io.api import save_upsert_list_async, dirty_fields
    from unittest.mock import AsyncMock
    import asyncio

    recs = SObjectList(
        [simple_sobject(External_Id__c=f"EX{i}", Name=f"N{i}") for i in range(3)],
        connection="test",
    )
    for r in recs:
        dirty_fields(r).update(["External_Id__c", "Name"])

    monkeypatch.setattr(
        "sf_toolkit.io.api.resolve_async_client",
        lambda cls, client=None: mock_async_client,
    )

    response = MagicMock()
    response.json.return_value = [
        {"id": f"001{i}", "success": True, "errors": [], "created": True}
        for i in range(3)
    ]
    mock_async_client.patch = AsyncMock(return_value=response)

    results = asyncio.run(
        save_upsert_list_async(recs, external_id_field="External_Id__c")
    )
    assert len(results) == 3
    assert mock_async_client.patch.call_count == 1
    for r in recs:
        assert not dirty_fields(r)


def test_save_insert_list_empty_returns_empty(simple_sobject):
    from sf_toolkit.io.api import save_insert_list

    empty = SObjectList([], connection="test")
    assert save_insert_list(empty) == []


@pytest.mark.asyncio
async def test_save_insert_list_async_assigns_ids(
    simple_sobject, mock_async_client, monkeypatch
):
    from sf_toolkit.io.api import save_insert_list_async
    from unittest.mock import AsyncMock

    recs = SObjectList([simple_sobject(Name="A"), simple_sobject(Name="B")])

    # monkeypatch.setattr(
    #     "sf_toolkit.io.api.resolve_async_client",
    #     lambda cls, client=None: mock_async_client,
    # )

    response = MagicMock()
    response.json.return_value = [
        {"id": "001A", "success": True, "errors": [], "created": True},
        {"id": "001B", "success": True, "errors": [], "created": True},
    ]
    mock_async_client.post = AsyncMock(return_value=response)

    results = await save_insert_list_async(recs)
    assert len(results) == 2
    assert recs[0].Id == "001A"
    assert recs[1].Id == "001B"


def test_save_update_list_async_clears_dirty(
    simple_sobject, mock_async_client, monkeypatch
):
    from sf_toolkit.io.api import save_update_list_async, dirty_fields
    from unittest.mock import AsyncMock
    import asyncio

    recs = SObjectList(
        [simple_sobject(Id="001", Name="A"), simple_sobject(Id="002", Name="B")],
    )
    dirty_fields(recs[0]).add("Name")
    dirty_fields(recs[1]).add("Name")

    monkeypatch.setattr(
        "sf_toolkit.io.api.resolve_async_client",
        lambda cls, client=None: mock_async_client,
    )
    response = MagicMock()
    response.json.return_value = [
        {"id": "001", "success": True, "errors": [], "created": False},
        {"id": "002", "success": True, "errors": [], "created": False},
    ]
    mock_async_client.post = AsyncMock(return_value=response)

    results = asyncio.run(save_update_list_async(recs, only_changes=True))
    assert len(results) == 2
    assert not dirty_fields(recs[0])
    assert not dirty_fields(recs[1])


def test_save_update_bulk_invokes_job_methods(simple_sobject, monkeypatch):
    from sf_toolkit.io.api import save_update_bulk

    recs = SObjectList(
        [simple_sobject(Id="001"), simple_sobject(Id="002")], connection="test"
    )

    job_mock = MagicMock()
    monkeypatch.setattr(
        "sf_toolkit.io.api.BulkApiIngestJob.init_job",
        lambda sobject_type, operation, connection=None, **opts: job_mock,
    )
    job_mock.upload_batches.return_value = None

    result_job = save_update_bulk(recs)
    assert result_job is job_mock
    assert job_mock.upload_batches.call_count == 1


@pytest.mark.asyncio
async def test_save_insert_bulk_async_invokes_job_methods(simple_sobject, monkeypatch):
    from sf_toolkit.io.api import save_insert_bulk_async
    import asyncio

    recs = SObjectList(
        [simple_sobject(Name="A"), simple_sobject(Name="B")], connection="test"
    )

    mock_job = MagicMock()

    mock_job.upload_batches_async = AsyncMock()
    mock_job.upload_batches_async.return_value = None
    mock_init_async = AsyncMock()
    mock_init_async.return_value = mock_job

    monkeypatch.setattr(
        "sf_toolkit.io.api.BulkApiIngestJob.init_job_async",
        mock_init_async,
    )

    result_job = await save_insert_bulk_async(recs)
    assert result_job is mock_job


def test_save_upsert_bulk_invokes_job_methods(simple_sobject, monkeypatch):
    from sf_toolkit.io.api import save_upsert_bulk

    recs = SObjectList(
        [simple_sobject(External_Id__c="E1"), simple_sobject(External_Id__c="E2")],
        connection="test",
    )
    job_mock = MagicMock()
    monkeypatch.setattr(
        "sf_toolkit.io.api.BulkApiIngestJob.init_job",
        lambda sobject_type,
        operation,
        external_id_field=None,
        connection=None,
        **opts: job_mock,
    )
    job_mock.upload_batches.return_value = None
    result_job = save_upsert_bulk(recs, external_id_field="External_Id__c")
    assert result_job is job_mock
    assert job_mock.upload_batches.call_count == 1


def test_save_update_bulk_empty_returns_none(simple_sobject):
    from sf_toolkit.io.api import save_update_bulk

    empty = SObjectList([], connection="test")
    assert save_update_bulk(empty) is None


def test_save_insert_bulk_empty_returns_none(simple_sobject):
    from sf_toolkit.io.api import save_insert_bulk

    with pytest.raises(AssertionError):
        empty = SObjectList([], connection="test")
        _ = save_insert_bulk(empty)


def test_save_update_bulk_async_empty_returns_none(simple_sobject):
    from sf_toolkit.io.api import save_update_bulk_async
    import asyncio

    empty = SObjectList([], connection="test")
    assert asyncio.run(save_update_bulk_async(empty)) is None


def test_save_insert_bulk_async_empty_returns_none(simple_sobject):
    from sf_toolkit.io.api import save_insert_bulk_async
    import asyncio

    empty = SObjectList([], connection="test")
    assert asyncio.run(save_insert_bulk_async(empty)) is None
