import click


class TogglException(Exception):
    pass


class TogglValidationException(TogglException):
    pass


class TogglAuthorizationException(TogglException):
    pass


class TogglAuthenticationException(TogglException):
    pass


class TogglMultipleResults(TogglException):
    pass


class TogglCliException(TogglException, click.ClickException):
    pass
