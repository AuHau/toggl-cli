VERSION = (2, 0, 0)


def get_version(raw=False):
    if raw:
        return VERSION

    return '.'.join(map(str, VERSION))


__version__ = get_version()
