import logging

pkg_root = logging.getLogger("sftk")


def getLogger(name: str | None):
    if not name:
        return pkg_root
    return pkg_root.getChild(name)
