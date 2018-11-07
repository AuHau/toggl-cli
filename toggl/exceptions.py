import click


class TogglException(Exception):
    """
    General top-level Exception for TogglCLI related issues
    """
    exit_code = 1


class TogglValidationException(TogglException):
    """
    Exception raised during validations of TogglEntity before saving the entity or by calling validate() method.
    """
    exit_code = 40


class TogglMultipleResultsException(TogglException):
    """
    Exception returned by TogglSet when calling get() method with conditions that does not narrow the set of all items
    to only one item.
    """
    pass


class TogglConfigException(TogglException):
    """
    Exception related to Config object and its functionality.
    """
    pass


class TogglConfigMigrationException(TogglException):
    """
    Exception related to migrations of Config files (.togglrc)
    """
    pass


class TogglCliException(TogglException, click.ClickException):
    """
    Exception related to the CLI functionality.
    """
    pass


class TogglPremiumException(TogglException):
    """
    Exception raised when user tries to use a Toggl's functionality which is limited only to Premium (Paid) workspaces
    and his current workspace does not support that.
    """
    exit_code = 42


class TogglNotAllowedException(TogglException):
    """
    Exception raised when user tries operation which is not allowed.

    Examples:
     - modifing a resources for which he requires admin privilege and he does not have it
     - using methods which are disabled for the Entity (eq. TogglSet.all() when the binded TogglEntity._can_get_list = False)
    """
    pass


# API Exceptions
class TogglApiException(TogglException):
    def __init__(self, status_code, message, *args, **kwargs):
        self.status_code = status_code
        self.message = message

        super().__init__(*args, **kwargs)


class TogglServerException(TogglApiException):
    """
    Exception raised when the Toggl's API is unavailable for unknown reasons (eq. HTTP status code 500)
    """
    pass


class TogglAuthorizationException(TogglApiException):
    """
    Exception raised when API refuses to perform an action because of insufficient user's rights.
    """
    pass


class TogglAuthenticationException(TogglApiException):
    """
    Exception raised when Toggl does not recognize the authentication credentials provided by the user.
    """
    exit_code = 43


class TogglThrottlingException(TogglApiException):
    """
    Exception raised when Toggl refuse API call because the call was too soon from last call.
    """
    exit_code = 10


class TogglNotFoundException(TogglApiException):
    """
    Exception raised when requested resource was not found.
    """
    exit_code = 44
