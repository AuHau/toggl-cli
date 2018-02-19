import click


class TogglException(Exception):
    pass


class TogglCliException(TogglException, click.ClickException):
    pass
