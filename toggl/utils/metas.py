import logging
from pprint import pformat
from traceback import format_stack

logger = logging.getLogger('toggl.utils.metas')

sentinel = object()


class CachedFactoryMeta(type):
    """
    Meta class that implements pattern similar to Singleton, except there are more instances cached based on
    a input parameter. It utilizes Factory pattern and forbids direct instantion of the class.

    To retrieve/create unique instance use `factory(key)` class method.

    It is possible to leave out 'key' parameter and then default value is returned. Related to this, it is possible
    to set a default object using `set_default(obj)` class method.
    """

    SENTINEL_KEY = '20800fa4-c75d-4c2c-9c99-fb35122e1a18'

    def __new__(mcs, name, bases, namespace):
        mcs.cache = {}

        def new__init__(_):
            raise ValueError('Cannot directly instantiate new object, you have to use \'factory\' method for that!')

        old_init = namespace.get('__init__')
        namespace['__init__'] = new__init__

        def factory(cls_obj, key=sentinel, *args, **kwargs):
            # Key with None are not cached
            if key is None:
                obj = cls_obj.__new__(cls_obj, key, *args, **kwargs)
                old_init(obj, key, *args, **kwargs)
                return obj

            cached_key = mcs.SENTINEL_KEY if key == sentinel else key

            # Is already cached ==> return it
            if cached_key in mcs.cache:
                return mcs.cache[cached_key]

            # Default value
            if key == sentinel:
                obj = cls_obj.__new__(cls_obj, *args, **kwargs)
                old_init(obj, *args, **kwargs)
            else:
                obj = cls_obj.__new__(cls_obj, key, *args, **kwargs)
                old_init(obj, key, *args, **kwargs)

            mcs.cache[cached_key] = obj

            return obj

        def set_default(_, obj):
            mcs.cache[mcs.SENTINEL_KEY] = obj

        namespace['set_default'] = classmethod(set_default)
        namespace['factory'] = classmethod(factory)
        return super().__new__(mcs, name, bases, namespace)


class ClassAttributeModificationWarning(type):
    """
    Meta class that logs warnings when class's attributes are overridden.
    """
    def __setattr__(cls, attr, value):
        logger.warning('You are modifying class attribute of \'{}\' class. You better know what you are doing!'
                       .format(cls.__name__))

        logger.debug(pformat(format_stack()))

        super().__setattr__(attr, value)
