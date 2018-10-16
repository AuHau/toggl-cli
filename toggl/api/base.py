import json
import logging
import re
import typing
from abc import ABCMeta
from collections import OrderedDict
from inspect import Signature, Parameter

from .. import exceptions
from .. import utils
from . import fields as model_fields

logger = logging.getLogger('toggl.api.base')

Entity = typing.TypeVar('Entity', bound='TogglEntity')


def evaluate_conditions(conditions, entity, contain=False):  # type: (typing.Dict, Entity, bool) -> bool
    """
    Will compare conditions dict and entity.
    Condition's keys and values must match the entities attributes, but not the other way around.

    :param contain: If True, then string fields won't be tested on equality but on partial match.
    :param entity: TogglEntity
    :param conditions: dict
    :return:
    :rtype: bool
    """
    for key in conditions:
        if not getattr(entity, key, False):
            return False

        if isinstance(entity.__fields__[key], model_fields.StringField) and contain:
            if str(conditions[key]) not in str(getattr(entity, key)):
                return False

            continue

        if str(getattr(entity, key)) != str(conditions[key]):
            return False

    return True


# TODO: Caching
class TogglSet(object):
    """
    Class that is mainly responsible for fetching objects from the API.

    It is always binded to an entity class that represents entities which will be fetched from the API. The binding is
    done either passing the Entity's class to constructor or later on calling method bind_to_class. Without
    binded Entity the class can not perform any action.
    """

    def __init__(self, entity_cls=None, url=None, can_get_detail=None, can_get_list=None):  # type: (Entity, typing.Union[str, None], typing.Union[bool, None], typing.Union[bool, None]) -> None
        self.entity_cls = entity_cls
        self._url = url
        self._can_get_detail = can_get_detail
        self._can_get_list = can_get_list

    def bind_to_class(self, cls):  # type: (Entity) -> None
        """
        Binds an Entity to the instance.

        :raises exceptions.TogglException: When instance is already bound TogglException is raised.
        """
        if self.entity_cls is not None:
            raise exceptions.TogglException('The instance is already bound to a class {}!'.format(self.entity_cls))

        self.entity_cls = cls

    @property
    def base_url(self):  # type: (TogglSet) -> str
        """
        Returns base URL which will be used for building listing or detail URLs.
        """
        if self._url:
            return self._url

        if self.entity_cls is None:
            raise exceptions.TogglException('The TogglSet instance is not binded to any TogglEntity!')

        return self.entity_cls.get_url()

    def build_list_url(self, caller, config, **kwargs):  # type: (str, utils.Config, **typing.Any) -> str
        """
        Build the listing URL.

        :param caller: Defines which method called this method, it can be either 'filter' or 'all'.
        :param config: Config
        :param kwargs: If caller == 'filter' then kwargs contain conditions for filtering.
        """
        return '/{}'.format(self.base_url)

    def build_detail_url(self, id, config):  # type: (int, utils.Config) -> str
        """
        Build the detail URL.

        :param id: ID of the entity to fetch.
        :param config: Config
        """
        return '/{}/{}'.format(self.base_url, id)


    @property
    def can_get_detail(self):  # type: (TogglSet) -> bool
        """
        Property which defines if TogglSet can fetch detail of the binded Entity.
        """
        if self._can_get_detail is not None:
            return self._can_get_detail

        if self.entity_cls and self.entity_cls._can_get_detail is not None:
            return self.entity_cls._can_get_detail

        return True

    @property
    def can_get_list(self):  # type: (TogglSet) -> bool
        """
        Property which defines if TogglSet can fetch list of all objects of the binded Entity.
        """
        if self._can_get_list is not None:
            return self._can_get_list

        if self.entity_cls and self.entity_cls._can_get_list is not None:
            return self.entity_cls._can_get_list

        return True

    def get(self, id=None, config=None, **conditions):  # type: (typing.Any, utils.Config, dict) -> Entity
        """
        Method for fetching detail object of the entity. it fetches the object based on specified conditions.

        If ID is used then detail URL is used to fetch object.
        If other conditions are used to specify the object, then TogglSet will fetch all objects using listing URL and
        filter out objects based on passed conditions.

        In any case result must be only one object or no object at all. Returned is the fetched object or None.

        :raises exceptions.TogglMultipleResultsException: When multiple results is returned base on the specified conditions.
        """
        if self.entity_cls is None:
            raise exceptions.TogglException('The TogglSet instance is not binded to any TogglEntity!')

        config = config or utils.Config.factory()

        if id is not None:
            if self.can_get_detail:
                try:
                    fetched_entity = utils.toggl(self.build_detail_url(id, config), 'get', config=config)
                    if fetched_entity['data'] is None:
                        return None

                    return self.entity_cls.deserialize(config=config, **fetched_entity['data'])
                except exceptions.TogglNotFoundException:
                    return None
            else:
                # TODO: [Q/Design] Is this desired fallback?
                conditions['id'] = id

        entries = self.filter(config=config, **conditions)

        if len(entries) > 1:
            raise exceptions.TogglMultipleResultsException()

        if not entries:
            return None

        return entries[0]

    def _fetch_all(self, url, order, config):  # type: (str, str, utils.Config) -> typing.List[Entity]
        """
        Helper method that fetches all objects from given URL and deserialize them.
        """
        fetched_entities = utils.toggl(url, 'get', config=config)

        if fetched_entities is None:
            return []

        output = []
        i = 0 if order == 'asc' else len(fetched_entities) - 1
        while 0 <= i < len(fetched_entities):
            output.append(self.entity_cls.deserialize(config=config, **fetched_entities[i]))

            if order == 'asc':
                i += 1
            else:
                i -= 1

        return output

    def filter(self, order='asc', config=None, contain=False, **conditions):  # type: (str, utils.Config, bool, dict) -> typing.List[Entity]
        """
        Method that fetches all entries and filter them out based on specified conditions.

        :param order: Strings 'asc' or 'desc' which specifies how the results will be sorted (
        :param config: Config instance
        :param contain: Specify how evaluation of conditions is performed. If True condition is evaluated using 'in' operator, otherwise hard equality (==) is enforced.
        :param conditions: Dict of conditions to filter the results. It has structure 'name of property' => 'value'
        """
        if self.entity_cls is None:
            raise exceptions.TogglException('The TogglSet instance is not binded to any TogglEntity!')

        url = self.build_list_url('filter', config, **conditions)
        fetched_entities = self._fetch_all(url, order, config)

        if fetched_entities is None:
            return []

        # There are no specified conditions ==> return all
        if not conditions:
            return fetched_entities

        return [entity for entity in fetched_entities if evaluate_conditions(conditions, entity, contain)]

    def all(self, order='asc', config=None, **kwargs):  # type: (str, utils.Config, **typing.Any) -> typing.List[Entity]
        """
        Method that fetches all entries and deserialize them into instances of the binded entity.

        :param order: Strings 'asc' or 'desc' which specifies how the results will be sorted (
        :param config: Config instance
        :raises exceptions.TogglNotAllowedException: When retrieving a list of objects is not allowed.
        """
        if self.entity_cls is None:
            raise exceptions.TogglException('The TogglSet instance is not binded to any TogglEntity!')

        if not self.can_get_list:
            raise exceptions.TogglNotAllowedException('Entity {} is not allowed to fetch list from the API!'
                                            .format(self.entity_cls))

        config = config or utils.Config.factory()
        url = self.build_list_url('all', config, **kwargs)

        return self._fetch_all(url, order, config)

    def __str__(self):
        return 'ToggleSet<{}>'.format(self.entity_cls.__name__)


class WorkspaceToggleSet(TogglSet):
    """
    Specialized TogglSet for Workspaced entities.
    """

    def build_list_url(self, caller, config, **kwargs):  # type: (str, utils.Config, **typing.Any) -> str
        wid = kwargs.get('wid') or config.default_workspace.id
        return '/workspaces/{}/{}'.format(wid, self.base_url)


class TogglEntityMeta(ABCMeta):
    """
    Toggl Entity's Meta, which collects all Fields of a Entity and build related properties ('__fields__', '__mapped_fields__', '__signature__')
    Also if not defined it creates TogglSet instance binded to the Entity under 'objects' property.
    """

    @staticmethod
    def _make_signature(fields):  # type: (typing.Dict[str, model_fields.TogglField]) -> Signature
        """
        Creates Signature object for validation of passed args and kwargs. Currently not used for validation.
        """
        non_default_parameters = [Parameter(field.name, Parameter.POSITIONAL_OR_KEYWORD) for field in fields.values()
                                  if field.name != 'id' and field.required]
        default_parameters = [Parameter(field.name, Parameter.POSITIONAL_OR_KEYWORD, default=field.default) for field in
                              fields.values()
                              if field.name != 'id' and not field.required]

        return Signature(non_default_parameters + default_parameters)

    @staticmethod
    def _make_fields(attrs, parents):  # type: (typing.Dict, typing.List[typing.Type[Entity]]) -> typing.Dict[str, model_fields.Field]
        """
        Builds dict where keys are name of the fields and values are the TogglField's instances.
        """
        fields = OrderedDict()
        for parent in parents:
            fields.update(parent.__fields__)

        for key, field in attrs.items():
            if isinstance(field, model_fields.TogglField):
                if key in fields:
                    logger.warning('Field \'{}\' is being overridden'.format(key))

                field.name = key
                fields[key] = field

        return fields

    @staticmethod
    def _make_mapped_fields(fields):  # type: (typing.Dict[str, model_fields.TogglField]) -> typing.Dict[str, model_fields.MappingField]
        """
        Similar to _make_fields(), except it takes in consideration MappedFields.
        The keys of the result dict are 'mapped_field's (see MappedField implementation)
        """
        out = {}
        for field in fields.values():
            if isinstance(field, model_fields.MappingField):
                if field.mapped_field in out:
                    raise TypeError('MappingField conflict! There is already other field who is mapped to \'{}\''.format(field.mapped_field))

                out[field.mapped_field] = field

        return out

    def __new__(mcs, name, bases, attrs, **kwargs):
        new_class = super().__new__(mcs, name, bases, attrs, **kwargs)

        fields = mcs._make_fields(attrs, bases)
        setattr(new_class, '__fields__', fields)
        setattr(new_class, '__mapped_fields__', mcs._make_mapped_fields(fields))
        setattr(new_class, '__signature__', mcs._make_signature(fields))

        # Add objects only if they are not defined to allow custom ToggleSet implementations
        if 'objects' not in new_class.__dict__:
            setattr(new_class, 'objects', WorkspaceToggleSet(new_class))
        else:
            try:
                new_class.objects.bind_to_class(new_class)
            except (exceptions.TogglException, AttributeError):
                pass

        return new_class


class TogglEntity(metaclass=TogglEntityMeta):
    """
    Base class for all Toggl Entities.

    Simplest Entities consists only of fields declaration (eq. TogglField and its subclasses), but it is also possible
    to implement custom class or instance methods for specific tasks.

    This class handles serialization, saving new instances, updating the existing one, deletion etc.
    Support for these operation can be customized using _can_* attributes, by default everything is enabled.
    """

    __signature__ = Signature()
    __fields__ = OrderedDict()

    _validate_workspace = True
    _can_create = True
    _can_update = True
    _can_delete = True
    _can_get_detail = True
    _can_get_list = True

    id = model_fields.IntegerField(required=False, default=None)

    def __init__(self, config=None, **kwargs):
        self._config = config or utils.Config.factory()
        self.__change_dict__ = {}

        for field in self.__fields__.values():
            if field.name in {'id'}:
                continue

            if isinstance(field, model_fields.MappingField):
                # User supplied most probably the whole mapped object
                if field.name in kwargs:
                    field.init(self, kwargs.get(field.name))
                    continue

                # Most probably converting API call with direct ID of the object
                if field.mapped_field in kwargs:
                    field.init(self, kwargs.get(field.mapped_field))
                    continue

                if field.default is model_fields.NOTSET and field.required:
                    raise TypeError('We need \'{}\' attribute!'.format(field.mapped_field))
                continue

            if field.name not in kwargs:
                if field.default is model_fields.NOTSET and field.required:
                    raise TypeError('We need \'{}\' attribute!'.format(field.name))
            else:  # Set the attribute only when there is some value to set, so default values could work properly
                field.init(self, kwargs[field.name])

    def save(self, config=None):  # type: (utils.Config) -> None
        """
        Main method for saving the entity.

        If it is a new entity (eq. entity.id is not set), then calling this method will result in creation of new object using POST call.
        If this is already existing entity, then calling this method will result in updating of the object using PUT call.

        For updating the entity, only changed fields are sent (this is tracked using self.__change_dict__).

        Before the API call validations are performed on the instance and only after successful validation, the call is made.

        :raises exceptions.TogglNotAllowedException: When action (create/update) is not allowed.
        """
        if not self._can_update and self.id is not None:
            raise exceptions.TogglNotAllowedException('Updating this entity is not allowed!')

        if not self._can_create and self.id is None:
            raise exceptions.TogglNotAllowedException('Creating this entity is not allowed!')

        config = config or self._config

        self.validate()

        if self.id is not None:  # Update
            utils.toggl('/{}/{}'.format(self.get_url(), self.id), 'put', self.json(update=True), config=config)
            self.__change_dict__ = {}  # Reset tracking changes
        else:  # Create
            data = utils.toggl('/{}'.format(self.get_url()), 'post', self.json(), config=config)
            self.id = data['data']['id']  # Store the returned ID

    def delete(self, config=None):  # type: (utils.Config) -> None
        """
        Method for deletion of the entity through API using DELETE call.

        This will not delete the instance's object in Python, therefore calling save() method after deletion will
        result in new object created using POST call.

        :raises exceptions.TogglNotAllowedException: When action is not allowed.
        """
        if not self._can_delete:
            raise exceptions.TogglNotAllowedException('Deleting this entity is not allowed!')

        if not self.id:
            raise exceptions.TogglException('This instance has not been saved yet!')

        utils.toggl('/{}/{}'.format(self.get_url(), self.id), 'delete', config=config or self._config)
        self.id = None  # Invalidate the object, so when save() is called after delete a new object is created

    def json(self, update=False):  # type: (bool) -> str
        """
        Serialize the entity into JSON string.

        :param update: Specifies if the resulted JSON should contain only changed fields (for PUT call) or whole entity.
        """
        return json.dumps({self.get_name(): self.to_dict(serialized=True, changes_only=update)})

    def validate(self):  # type: () -> None
        """
        Performs validation across all Entity's fields.

        If overloading then don't forget to call super().validate()!
        """
        for field in self.__fields__.values():
            if isinstance(field, model_fields.MappingField):
                field.validate(getattr(self, field.mapped_field, None))
            else:
                field.validate(getattr(self, field.name, None))

    def to_dict(self, serialized=False, changes_only=False):  # type: (bool, bool) -> typing.Dict
        """
        Method that returns dict representing the instance.

        :param serialized: If True, the returned dict contains only Python primitive types and no objects (eq. so JSON serialization could happen)
        :param changes_only: If True, the returned dict contains only changes to the instance since last call of save() method.
        """
        source_dict = self.__change_dict__ if changes_only else self.__fields__
        entity_dict = {}
        for field_name in source_dict.keys():
            try:
                field = self.__fields__[field_name]
            except KeyError:
                field = self.__mapped_fields__[field_name]

            value = getattr(self, field.name, None)

            if serialized:
                try:
                    entity_dict[field.mapped_field] = field.serialize(value)
                except AttributeError:
                    entity_dict[field.name] = field.serialize(value)
            else:
                entity_dict[field.name] = value

        return entity_dict

    def __cmp__(self, other):  # type: (typing.Generic[Entity]) -> bool
        if not isinstance(other, self.__class__):
            raise RuntimeError('You are trying to compare instances of different classes!')

        # TODO: [Q/Design] What to do if ID is not set? Should there be value's comparision fallback?
        return self.id == other.id

    # TODO: [Q/Design] Problem with unique field's. Copy ==> making invalid option ==> Some validation?
    def __copy__(self):  # type: () -> typing.Generic[Entity]
        cls = self.__class__
        new_instance = cls.__new__(cls)
        new_instance.__dict__.update(self.__dict__)
        new_instance.id = None  # New instance was never saved ==> no ID for it yet
        return new_instance

    def __str__(self):  # type: () -> str
        return '{} (#{})'.format(getattr(self, 'name', None) or self.__class__.__name__, self.id)

    @classmethod
    def get_name(cls, verbose=False):  # type: (bool) -> str
        name = cls.__name__
        name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()

        if verbose:
            return name.replace('_', ' ').capitalize()

        return name

    @classmethod
    def get_url(cls):  # type: () -> str
        return cls.get_name() + 's'

    @classmethod
    def deserialize(cls, config=None, **kwargs):  # type: (utils.Config, **typing.Any) -> typing.Generic[Entity]
        """
        Method which takes kwargs as dict representing the Entity's data and return actuall instance of the Entity.
        """
        try:
            kwargs.pop('at')
        except KeyError:
            pass

        instance = cls.__new__(cls)
        instance._config = config

        for key, value in kwargs.items():
            try:
                field = instance.__fields__[key]
            except KeyError:
                try:
                    field = instance.__mapped_fields__[key]
                except KeyError:
                    continue

            field.init(instance, value)

        return instance
