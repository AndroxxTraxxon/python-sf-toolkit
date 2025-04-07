__all__ = ("lazy_login",)


def lazy_login(**kwargs):
    if "sf_cli_alias" in kwargs:
        from .login_cli import cli_login

        return cli_login(kwargs.pop("sf_cli_alias"), kwargs.pop("sf_cli_exec_path"))
