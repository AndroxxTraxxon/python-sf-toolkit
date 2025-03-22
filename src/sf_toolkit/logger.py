import logging

pkg_root = logging.getLogger("sf_toolkit")

def getLogger(name: str | None):
    if not name:
        return pkg_root
    return pkg_root.getChild(name)
