from collections.abc import Callable
import json
import csv
from pathlib import Path
from typing import Any, TypeVar


from ..data.fields import query_fields, serialize_object

from ..data.transformers import flatten, unflatten
from ..data.sobject import SObject, SObjectList

_SO = TypeVar("_SO", bound=SObject)


def from_csv_file(
    cls: type[_SO],
    filepath: Path | str,
    file_encoding: str = "utf-8",
    fieldnames: list[str] | None = None,
):
    """
    Loads SObject records from a CSV file.
    The CSV file must have a header row with field names matching the SObject fields.
    """
    import csv

    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    with filepath.open(encoding=file_encoding) as csv_file:
        reader = csv.DictReader(csv_file, fieldnames=fieldnames)
        assert reader.fieldnames, "no fieldnames found for reader."
        object_fields = set(query_fields(cls))
        for field in reader.fieldnames:
            if field not in object_fields:
                raise KeyError(
                    f"Field {field} in {filepath} not found for SObject {cls.__qualname__} ({cls.attributes.type})"
                )
        return SObjectList(
            (cls(**unflatten(row)) for row in reader),
            connection=cls.attributes.connection,
        )  # type: ignore


def from_json_file(cls: type[_SO], filepath: Path | str, file_encoding: str = "utf-8"):
    """
    Loads SObject records from a JSON file. The file can contain either a single
    JSON object or a list of JSON objects.
    """

    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    with filepath.open(encoding=file_encoding) as csv_file:
        data = json.load(csv_file)
        if isinstance(data, list):
            return SObjectList(
                (cls(**record) for record in data),
                connection=cls.attributes.connection,
            )
        elif isinstance(data, dict):
            return SObjectList([cls(**data)], connection=cls.attributes.connection)
        raise TypeError(
            (
                f"Unexpected {type(data).__name__} value "
                f"{str(data)[:50] + '...' if len(str(data)) > 50 else ''} "
                f"while attempting to load {cls.__qualname__} from {filepath}"
            )
        )


def from_file(
    cls: type[_SO], filepath: Path | str, file_encoding: str = "utf-8"
) -> SObjectList[_SO]:
    """
    Loads SObject records from a file. The file format is determined by the file extension.
    Supported file formats are CSV (.csv) and JSON (.json).
    """
    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    file_extension = filepath.suffix.lower()
    if file_extension == ".csv":
        return from_csv_file(cls, filepath, file_encoding=file_encoding)
    elif file_extension == ".json":
        return from_json_file(cls, filepath, file_encoding=file_encoding)
    else:
        raise ValueError(f"Unknown file extension {file_extension}")


def to_json_file(
    records: SObjectList[_SO],
    filepath: Path | str,
    encoding="utf-8",
    as_lines: bool = False,
    **json_options,
) -> None:
    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    with filepath.open("w+", encoding=encoding) as outfile:
        if as_lines:
            assert "indent" not in json_options, (
                "indent option not supported with as_lines=True"
            )
            for record in records:
                json.dump(serialize_object(record), outfile, **json_options)
                outfile.write("\n")
        else:
            json.dump(
                [serialize_object(record) for record in records],
                outfile,
                **json_options,
            )


def to_csv_file(self: SObjectList[_SO], filepath: Path | str, encoding="utf-8") -> None:
    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    assert self, "Cannot save an empty list"
    fieldnames = query_fields(type(self[0]))
    with filepath.open("w+", encoding=encoding) as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flatten(serialize_object(row)) for row in self)


def to_file(
    records: SObjectList[_SO],
    filepath: Path | str,
    file_encoding: str = "utf-8",
    **options,
) -> None:
    """
    Saves SObject records to a file. The file format is determined by the file extension.
    Supported file formats are CSV (.csv) and JSON (.json).
    """
    if isinstance(filepath, str):
        filepath = Path(filepath).resolve()
    file_extension = filepath.suffix.lower()
    if file_extension == ".csv":
        to_csv_file(records, filepath, encoding=file_encoding)
    elif file_extension == ".json":
        to_json_file(records, filepath, encoding=file_encoding, **options)
    else:
        raise ValueError(f"Unknown file extension {file_extension}")
