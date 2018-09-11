import click


class TogglException(Exception):
    pass


class TogglValidationException(TogglException):
    pass


class TogglMultipleResultsException(TogglException):
    pass


class TogglCliException(TogglException, click.ClickException):
    pass


# API Exceptions
class TogglServerException(TogglException):
    pass


class TogglApiException(TogglException):
    def __init__(self, status_code, message, *args, **kwargs):
        self.status_code = status_code
        self.message = message

        super().__init__(*args, **kwargs)


class TogglPremiumException(TogglApiException):
    pass


class TogglAuthorizationException(TogglApiException):
    pass


class TogglAuthenticationException(TogglApiException):
    pass


class TogglThrottlingException(TogglApiException):
    pass


class TogglNotFoundException(TogglApiException):
    pass
