import json
import re
from abc import ABCMeta
from builtins import int

from requests import HTTPError

from .. import utils
from ..exceptions import TogglValidationException, TogglException, TogglMultipleResults


def evaluate_conditions(conditions, entity):
    """
    Will compare conditions dict and entity.
    Condition's keys and values must match the entities attributes, but not the other way around.

    :param entity: TogglEntity
    :param conditions: dict
    :return:
    :rtype: bool
    """
    for key in conditions:
        if not getattr(entity, key, False):
            return False

        if str(getattr(entity, key)) != str(conditions[key]):
            return False

    return True


class TogglSet(object):
    def __init__(self, url, entity_cls, can_get_detail=True, can_get_list=True):
        self.url = url
        self.entity_cls = entity_cls
        self.can_get_detail = can_get_detail
        self.can_get_list = can_get_list

    def build_list_url(self, wid):
        return '/workspaces/{}/{}'.format(wid, self.url)

    def build_detail_url(self, id):
        return '/{}/{}'.format(self.url, id)

    def _convert_entity(self, raw_entity):
        entity_id = raw_entity.pop('id')
        entity_object = self.entity_cls(**raw_entity)
        entity_object.id = entity_id

        return entity_object

    def get(self, id=None, config=None, **conditions):
        if id is not None:
            if self.can_get_detail:
                try:
                    fetched_entity = utils.toggl(self.build_detail_url(id), 'get', config=config)
                    return self._convert_entity(fetched_entity['data'])
                except HTTPError:
                    return None
            else:
                conditions['id'] = id

        entries = self.filter(config=config, **conditions)

        if len(entries) > 1:
            raise TogglMultipleResults()

        if not entries:
            return None

        return entries[0]

    def filter(self, wid=None, config=None, **conditions):
        fetched_entities = self.all(wid, config)

        if fetched_entities is None:
            return []

        return [entity for entity in fetched_entities if evaluate_conditions(conditions, entity)]

    def all(self, wid=None, config=None):
        wid = wid or OldUser().get('default_wid')
        fetched_entities = utils.toggl(self.build_list_url(wid), 'get', config=config)

        if fetched_entities is None:
            return []

        entity_list = []
        for entity in fetched_entities:
            entity_list.append(
                self._convert_entity(entity)
            )

        return entity_list


class TogglEntityBase(ABCMeta):

    def __new__(cls, name, bases, attrs, **kwargs):
        new_class = super().__new__(cls, name, bases, attrs, **kwargs)

        parents = [b for b in bases if isinstance(b, TogglEntityBase)]
        if not parents:
            return new_class

        setattr(new_class, 'objects', TogglSet(new_class.get_url(), new_class, new_class._can_get_detail))

        return new_class


# TODO: Premium fields and check for current Workspace to be Premium
class TogglEntity(metaclass=TogglEntityBase):
    _validate_workspace = True
    _can_create = True
    _can_update = True
    _can_delete = True
    _can_get_detail = True

    required_fields = tuple()
    int_fields = tuple()
    float_fields = tuple()
    bool_fields = tuple()
    mapping_fields = dict()

    def __init__(self, entity_id=None, wid=None, config=None):
        self.id = entity_id
        self._config = config

        if wid is None:
            if not self.get_name() == 'workspace':
                self.wid = OldUser().get('default_wid')
            self._validate_workspace = False
        else:
            self.wid = wid

    def save(self):
        if not self._can_update and self.id is not None:
            raise TogglException("Updating this entity is not allowed!")

        if not self._can_create and self.id is None:
            raise TogglException("Creating this entity is not allowed!")

        self.validate()

        if self.id is not None:  # Update
            utils.toggl("/{}/{}".format(self.get_url(), self.id), "put", self.json(), config=self._config)
        else:  # Create
            data = utils.toggl("/{}".format(self.get_url()), "post", self.json(), config=self._config)
            self.id = data['data']['id']  # Store the returned ID

    def delete(self):
        if not self._can_delete:
            raise TogglException("Deleting this entity is not allowed!")

        utils.toggl("/{}/{}".format(self.get_url(), self.id), "delete")
        self.id = None  # Invalidate the object, so when save() is called after delete a new object is created

    def __cmp__(self, other):
        if not isinstance(other, self.__class__):
            raise TogglException("You are trying to compare instances of different classes!")

        return self.id == other.id

    def json(self):
        return json.dumps({self.get_name(): self.to_dict()})

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

    def validate(self, validate_workspace_existence=True):
        from .models import Workspace
        
        if not self.get_name() == 'Workspace':
            if self._validate_workspace and validate_workspace_existence and Workspace.objects.get(self.wid) is None:
                raise TogglValidationException("Workspace ID does not exists!")

            if self.wid is None:
                raise TogglValidationException("Workspace ID is required!")

            if not isinstance(self.wid, int):
                raise TogglValidationException("Workspace ID must be an integer!")

        for field in self.required_fields:
            if getattr(self, field) is None:
                raise TogglValidationException("Attribute '{}' is required!".format(field))

        for field in self.int_fields:
            if getattr(self, field) is not None and not isinstance(getattr(self, field), int):
                raise TogglValidationException("Attribute '{}' has to be integer!".format(field))

        for field in self.bool_fields:
            if getattr(self, field) is not None and not isinstance(getattr(self, field), bool):
                raise TogglValidationException("Attribute '{}' has to be boolean!".format(field))

        for field in self.float_fields:
            if getattr(self, field) is not None and not isinstance(getattr(self, field), float):
                raise TogglValidationException("Attribute '{}' has to be float!".format(field))

    def to_dict(self):
        # Have to make copy, otherwise will modify directly instance's dict
        entity_dict = json.loads(json.dumps(vars(self)))

        try:  # New objects does not have ID ==> try/except
            del entity_dict['id']
        except KeyError:
            pass

        # Protected attributes are not serialized
        keys = list(entity_dict.keys())
        for key in keys:
            if key.startswith('_'):
                del entity_dict[key]

        if hasattr(self, '_FILTERED_KEYS'):
            for key in self._FILTERED_KEYS:
                try:
                    del entity_dict[key]
                except KeyError:
                    pass

        return entity_dict

    def __setattr__(self, key, value):
        if hasattr(self, '_READ_ONLY') and key in self._READ_ONLY:
            raise TogglException("You are trying to assign value to read-only attribute '{}'!".format(key))

        # if key == 'id' and value is not None:
        #     raise TogglException("You are trying to change ID which is not allowed, you can only set it to None to "
        #                          "create new object!")

        super(TogglEntity, self).__setattr__(key, value)

    def __getattr__(self, item):
        if item not in self.mapping_fields:
            raise AttributeError()

        mapping = self.mapping_fields[item]
        id = getattr(self, mapping.key)

        if id is None:
            return None

        if mapping.cardinality == 'one':
            return mapping.cls.objects.get(id)
        elif mapping.cardinality == 'many':
            return mapping.cls.objects.filter(id=id)
        else:
            raise TogglException('Unknown cardinality \'{}\''.format(mapping.cardinality))

    def __str__(self):
        return "{} #{}: {}".format(self.get_name().capitalize(), self.id, self.name)


class OldUser(object):
    """
    utils.Singleton toggl user data.
    """

    __metaclass__ = utils.Singleton

    def __init__(self):
        """
        Fetches user data from toggl.
        """
        result_dict = utils.toggl("/me", 'get')

        # Results come back in two parts. 'since' is how long the user has
        # had their toggl account. 'data' is a dictionary of all the other
        # user data.
        self.data = result_dict['data']
        self.data['since'] = result_dict['since']

    def get(self, prop):
        """
        Return the given toggl user property. User properties are
        documented at https://github.com/toggl/toggl_api_docs/blob/master/chapters/users.md
        """
        return self.data[prop]
