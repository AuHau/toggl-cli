import json
import logging
import re
from abc import ABCMeta
from collections import OrderedDict
from inspect import Signature, Parameter

from .. import exceptions
from .. import utils
from . import fields as model_fields

logger = logging.getLogger('toggl.models.base')


def evaluate_conditions(conditions, entity, contain=False):
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
    def __init__(self, entity_cls=None, url=None, can_get_detail=None, can_get_list=None):
        self.entity_cls = entity_cls
        self._url = url
        self._can_get_detail = can_get_detail
        self._can_get_list = can_get_list

    def bind_to_class(self, cls):
        if self.entity_cls is not None:
            raise exceptions.TogglException('The instance is already bound to a class {}!'.format(self.entity_cls))

        self.entity_cls = cls

    @property
    def url(self):
        return self._url or self.entity_cls.get_url()

    @property
    def can_get_detail(self):
        if self._can_get_detail is not None:
            return self._can_get_detail

        if self.entity_cls._can_get_detail is not None:
            return self.entity_cls._can_get_detail

        return True

    @property
    def can_get_list(self):
        if self._can_get_list is not None:
            return self._can_get_list

        if self.entity_cls._can_get_list is not None:
            return self.entity_cls._can_get_list

        return True

    def build_list_url(self):
        return '/{}'.format(self.url)

    def build_detail_url(self, id):
        return '/{}/{}'.format(self.url, id)

    def get(self, id=None, config=None, **conditions):
        if id is not None:
            if self.can_get_detail:
                try:
                    fetched_entity = utils.toggl(self.build_detail_url(id), 'get', config=config)
                    return self.entity_cls.deserialize(config=config, **fetched_entity['data'])
                except exceptions.TogglNotFoundException:
                    return None
            else:
                conditions['id'] = id

        entries = self.filter(config=config, **conditions)

        if len(entries) > 1:
            raise exceptions.TogglMultipleResultsException()

        if not entries:
            return None

        return entries[0]

    def filter(self, order='asc', config=None, contain=False, **conditions):
        fetched_entities = self.all(order, config)

        if fetched_entities is None:
            return []

        return [entity for entity in fetched_entities if evaluate_conditions(conditions, entity, contain)]

    def all(self, order='asc', config=None):
        if not self.can_get_list:
            raise exceptions.TogglException('Entity {} is not allowed to fetch list from the API!'
                                            .format(self.entity_cls))

        config = config or utils.Config.factory()
        fetched_entities = utils.toggl(self.build_list_url(), 'get', config=config)

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


class WorkspaceToggleSet(TogglSet):

    def build_list_url(self, wid=None):
        return '/workspaces/{}/{}'.format(wid, self.url)

    def filter(self, order='asc', wid=None, config=None, contain=False, **conditions):
        fetched_entities = self.all(order, wid, config)

        if fetched_entities is None:
            return []

        return [entity for entity in fetched_entities if evaluate_conditions(conditions, entity, contain)]

    def all(self, order='asc', wid=None, config=None):
        if not self.can_get_list:
            raise exceptions.TogglException('Entity {} is not allowed to fetch list from the API!'
                                            .format(self.entity_cls))

        config = config or utils.Config.factory()
        wid = wid or config.default_workspace.id
        fetched_entities = utils.toggl(self.build_list_url(wid), 'get', config=config)

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


class TogglEntityMeta(ABCMeta):

    def _make_signature(fields):
        non_default_parameters = [Parameter(field.name, Parameter.POSITIONAL_OR_KEYWORD) for field in fields.values()
                                  if field.name != 'id' and field.required]
        default_parameters = [Parameter(field.name, Parameter.POSITIONAL_OR_KEYWORD, default=field.default) for field in
                              fields.values()
                              if field.name != 'id' and not field.required]

        return Signature(non_default_parameters + default_parameters)

    def _make_fields(attrs, parents):
        fields = OrderedDict()
        for parent in parents:
            fields.update(parent.__fields__)

        for key, field in attrs.items():
            if isinstance(field, model_fields.TogglField):
                field.name = key
                fields[key] = field

        return fields

    def _make_mapped_fields(fields):
        return {field.mapped_field: field for field in fields.values() if isinstance(field, model_fields.MappingField)}

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
    __signature__ = Signature()
    __fields__ = OrderedDict()
    __change_dict__ = {}

    _validate_workspace = True
    _can_create = True
    _can_update = True
    _can_delete = True
    _can_get_detail = True
    _can_get_list = True

    id = model_fields.IntegerField(required=False)

    def __init__(self, config=None, **kwargs):
        self._config = config or utils.Config.factory()

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

                if field.default is None and field.required:
                    raise TypeError('We need "{}" attribute!'.format(field.mapped_field))
                continue

            if field.name not in kwargs:
                if field.default is None and field.required:
                    raise TypeError('We need "{}" attribute!'.format(field.name))
            else:  # Set the attribute only when there is some value to set, so default values could work properly
                field.init(self, kwargs[field.name])

    def save(self, config=None):
        if not self._can_update and self.id is not None:
            raise exceptions.TogglException("Updating this entity is not allowed!")

        if not self._can_create and self.id is None:
            raise exceptions.TogglException("Creating this entity is not allowed!")

        config = config or self._config

        self.validate()

        if self.id is not None:  # Update
            utils.toggl("/{}/{}".format(self.get_url(), self.id), "put", self.json(update=True), config=config)
            self.__change_dict__ = {}  # Reset tracking changes
        else:  # Create
            data = utils.toggl("/{}".format(self.get_url()), "post", self.json(), config=config)
            self.id = data['data']['id']  # Store the returned ID

    def delete(self, config=None):
        if not self._can_delete:
            raise exceptions.TogglException("Deleting this entity is not allowed!")

        utils.toggl("/{}/{}".format(self.get_url(), self.id), "delete", config=config or self._config)
        self.id = None  # Invalidate the object, so when save() is called after delete a new object is created

    def json(self, update=False):
        return json.dumps({self.get_name(): self.to_dict(serialized=True, changes_only=update)})

    def validate(self):
        for field in self.__fields__.values():
            field.validate(getattr(self, field.name, None))

    def to_dict(self, serialized=False, changes_only=False):
        source_dict = self.__change_dict__ if changes_only else self.__fields__
        entity_dict = {}
        for field_name in source_dict:
            field = self.__fields__[field_name]
            try:
                entity_dict[field.mapped_field] = getattr(self, field.name).id
            except AttributeError:
                value = getattr(self, field.name, None)
                entity_dict[field.name] = field.serialize(value) if serialized else value

        return entity_dict

    def __cmp__(self, other):
        if not isinstance(other, self.__class__):
            raise RuntimeError("You are trying to compare instances of different classes!")

        return self.id == other.id

    def __copy__(self):
        cls = self.__class__
        new_instance = cls.__new__(cls)
        new_instance.__dict__.update(self.__dict__)
        new_instance.id = None  # New instance was never saved ==> no ID for it yet
        return new_instance

    def __str__(self):
        return "{} (#{})".format(getattr(self, 'name'), self.id)

    @classmethod
    def get_name(cls, verbose=False):
        name = cls.__name__
        name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()

        if verbose:
            return name.replace('_', ' ').capitalize()

        return name

    @classmethod
    def get_url(cls):
        return cls.get_name() + 's'

    @classmethod
    def deserialize(cls, config=None, **kwargs):
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
