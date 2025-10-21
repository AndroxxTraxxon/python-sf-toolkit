from collections.abc import Callable
import json
from pathlib import Path
from typing import Any, TypeVar

from .fields import query_fields

from .transformers import unflatten
from .sobject import SObject, SObjectList

_SO = TypeVar("_SO", bound=SObject)

LoaderFunc = Callable[[type[_SO], Path, str], SObjectList[_SO]]
loaders: dict[str, LoaderFunc[Any]] = {}


def register(extension: str):
    def decorator(func: Callable[[type[SObject], Path, str], SObjectList[SObject]]):
        loaders[extension.lower()] = func
        return func

    return decorator


@register(".csv")
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


@register(".json")
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
    loader: LoaderFunc[_SO] | None = loaders.get(file_extension, None)
    if loader is not None:
        return loader(cls, filepath, file_encoding)
    raise ValueError(f"Unknown file extension {file_extension}")
