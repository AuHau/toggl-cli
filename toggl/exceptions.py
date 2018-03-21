import click


class TogglException(Exception):
    pass


class TogglValidationException(TogglException):
    pass


class TogglCliException(TogglException, click.ClickException):
    pass
