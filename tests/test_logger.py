from sf_toolkit.logger import getLogger, pkg_root


def test_logger_creation():
    # Test getting the root logger
    logger = getLogger(None)
    assert logger == pkg_root

    # Test getting a child logger
    child_name = "test_child"
    child_logger = getLogger(child_name)
    assert child_logger.name == f"{pkg_root.name}.{child_name}"

    # Test logger hierarchy
    assert child_logger.parent == pkg_root
