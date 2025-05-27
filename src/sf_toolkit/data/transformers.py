from typing import Any
from collections import defaultdict

def unflatten(flattened_data: dict[str, Any]) -> dict[str, Any]:
    inflated_data = {}
    nested_objects = defaultdict(dict)
    for fieldname in flattened_data.keys():
        if "." in fieldname:
            parent, child = fieldname.split(".", maxsplit=1)
            nested_objects[parent][child] = flattened_data[fieldname]
        else:
            inflated_data[fieldname] = flattened_data[fieldname]
    for name, nested_object in nested_objects.items():
        inflated_data[name] = unflatten(nested_object)

    return inflated_data


def flatten(data: dict[str, Any]) -> dict[str, Any]:
    flattened_data = {}
    for fieldname in data.keys():
        field_data = data[fieldname]
        assert not isinstance(field_data, list), "Cannot flatten list fields."
        if isinstance(field_data, dict):
            flat_nested_data = flatten(field_data)
            flattened_data.update(
                {
                    f"{fieldname}.{nested_field}": nested_value
                    for nested_field, nested_value in flat_nested_data.items()
                }
            )
        else:
            flattened_data[fieldname] = data[fieldname]

    return flattened_data
