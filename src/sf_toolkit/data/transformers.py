from typing import Any, TypeVar
from collections import defaultdict
from collections.abc import Iterable

from itertools import islice

_T = TypeVar("_T")


def chunked(
    iterable: Iterable[_T], n: int, *, strict: bool = False
) -> Iterable[list[_T]]:
    # batched('ABCDEFG', 2) → AB CD EF G
    if n < 1:
        raise ValueError("n must be at least one")
    iterator = iter(iterable)
    while batch := list(islice(iterator, n)):
        if strict and len(batch) != n:
            raise ValueError("batched(): incomplete batch")
        yield batch


def unflatten(flattened_data: dict[str, _T]) -> dict[str, _T | dict[str, _T]]:
    inflated_data: dict[str, _T | dict[str, _T]] = {}
    nested_objects: dict[str, dict[str, _T]] = defaultdict(dict)
    for fieldname in flattened_data.keys():
        if "." in fieldname:
            parent, child = fieldname.split(".", maxsplit=1)
            nested_objects[parent][child] = flattened_data[fieldname]
        else:
            inflated_data[fieldname] = flattened_data[fieldname]
    for name, nested_object in nested_objects.items():
        inflated_data[name] = unflatten(nested_object)  # pyright: ignore[reportArgumentType]

    return inflated_data


def flatten(data: dict[str, _T | dict[str, _T]]) -> dict[str, _T]:
    flattened_data: dict[str, _T] = {}
    for fieldname in data.keys():
        field_data = data[fieldname]
        assert not isinstance(field_data, list), "Cannot flatten list fields."
        if isinstance(field_data, dict):
            flat_nested_data = flatten(field_data)  # pyright: ignore[reportArgumentType]
            flattened_data.update(
                {
                    f"{fieldname}.{nested_field}": nested_value
                    for nested_field, nested_value in flat_nested_data.items()
                }
            )
        else:
            flattened_data[fieldname] = data[fieldname]  # pyright: ignore[reportArgumentType]

    return flattened_data
