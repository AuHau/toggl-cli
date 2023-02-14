from pbr.version import VersionInfo

VERSION = VersionInfo('togglCli').semantic_version()
__version__ = VERSION.release_string()

__all__ = (
    '__version__',
    'VERSION',
    'api',
    'utils',
    'exceptions',
    'toggl'
)
