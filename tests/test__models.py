import pytest
from sf_toolkit._models import (
    SObjectSaveError,
    SObjectSaveResult
)


@pytest.mark.parametrize(
    "error_code, message, fields",
    [
        ("TEST_CODE", "test error", ["field1", "field2"]),
        ("ANOTHER_CODE", "another error", ["field3", "field4"]),
    ]
)
def test_sobject_save_error(error_code, message, fields):
    error = SObjectSaveError(error_code, message, fields)
    str_error = str(error)
    assert message in str_error
    assert error_code in str_error
    for field in fields:
        assert field in str_error


def test_sobject_save_result():
    result = SObjectSaveResult(
        "TEST_ID",
        False,
        [{
            "statusCode": "TEST_CODE",
            "message": "test error",
            "fields": ["field1", "field2"]
        }]
    )
    str_result = str(result)
    assert "TEST_ID" in str_result
    assert "field1" in str_result
    assert "field2" in str_result

    assert type(result).__name__ in repr(result)
