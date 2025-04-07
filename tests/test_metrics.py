from sf_toolkit.metrics import parse_api_usage, Usage, PerAppUsage, ApiUsage


def test_parse_api_usage_with_api_usage_only():
    # Test with only api-usage information
    sforce_limit_info = "api-usage=18/5000"
    result = parse_api_usage(sforce_limit_info)

    assert isinstance(result, ApiUsage)
    assert result.api_usage == Usage(used=18, total=5000)
    assert result.per_app_api_usage is None


def test_parse_api_usage_with_per_app_usage_only():
    # Test with only per-app-api-usage information
    sforce_limit_info = "per-app-api-usage=17/250(appName=sample-connected-app)"
    result = parse_api_usage(sforce_limit_info)

    assert isinstance(result, ApiUsage)
    assert result.api_usage is None
    assert result.per_app_api_usage == PerAppUsage(
        used=17, total=250, name="sample-connected-app"
    )


def test_parse_api_usage_with_both_usages():
    # Test with both api-usage and per-app-api-usage information
    sforce_limit_info = (
        "api-usage=25/5000; per-app-api-usage=17/250(appName=sample-connected-app)"
    )
    result = parse_api_usage(sforce_limit_info)

    assert isinstance(result, ApiUsage)
    assert result.api_usage == Usage(used=25, total=5000)
    assert result.per_app_api_usage == PerAppUsage(
        used=17, total=250, name="sample-connected-app"
    )


def test_parse_api_usage_with_empty_string():
    # Test with empty string
    sforce_limit_info = ""
    result = parse_api_usage(sforce_limit_info)

    assert isinstance(result, ApiUsage)
    assert result.api_usage is None
    assert result.per_app_api_usage is None


def test_parse_api_usage_with_invalid_format():
    # Test with invalid format
    sforce_limit_info = "invalid-format"
    result = parse_api_usage(sforce_limit_info)

    assert isinstance(result, ApiUsage)
    assert result.api_usage is None
    assert result.per_app_api_usage is None


def test_parse_api_usage_with_complex_app_name():
    # Test with complex app name containing special characters
    sforce_limit_info = (
        "per-app-api-usage=17/250(appName=sample-app-with.special_chars)"
    )
    result = parse_api_usage(sforce_limit_info)

    assert isinstance(result, ApiUsage)
    assert result.api_usage is None
    assert result.per_app_api_usage == PerAppUsage(
        used=17, total=250, name="sample-app-with.special_chars"
    )
