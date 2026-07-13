from pbr.version import VersionInfo

VERSION = VersionInfo('tgl').semantic_version()
__version__ = VERSION.release_string()

__all__ = (
    '__version__',
    'VERSION',
    'api',
    'utils',
    'exceptions',
    'app'
)
