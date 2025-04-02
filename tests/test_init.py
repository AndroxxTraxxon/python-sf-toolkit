def test_import():
    """Test that the module can be imported without circular import issues."""
    import sf_toolkit

    # Verify top-level imports are accessible
    assert hasattr(sf_toolkit, "SalesforceClient")
    assert hasattr(sf_toolkit, "AsyncSalesforceClient")
    assert hasattr(sf_toolkit, "SalesforceAuth")
    assert hasattr(sf_toolkit, "SalesforceToken")
    assert hasattr(sf_toolkit, "SObject")
    assert hasattr(sf_toolkit, "SoqlSelect")
    assert hasattr(sf_toolkit, "lazy_login")
    assert hasattr(sf_toolkit, "cli_login")
