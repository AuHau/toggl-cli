from pbr.version import VersionInfo

_v = VersionInfo('toggl').semantic_version()
__version__ = _v.release_string()
VERSION = _v.version_tuple()
