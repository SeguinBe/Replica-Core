import neomodel
from neomodel import StructuredNode, StructuredRel, db
from neomodel import StringProperty, DateTimeProperty, ArrayProperty, UniqueIdProperty, EmailProperty, \
    RelationshipFrom, RelationshipTo, Relationship, JSONProperty, IntegerProperty
from .base import BaseElement
import hashlib


class User(StructuredNode, BaseElement):
    __do_not_marshall_properties__ = ['password_sha256', 'email']

    username = StringProperty(required=True, unique_index=True)
    password_sha256 = StringProperty(required=True)
    email = EmailProperty(required=False)

    authorization_level = IntegerProperty(default=0)

    groups = RelationshipTo('Group', 'OWNS')
    created_links = RelationshipFrom('.link.VisualLink', 'CREATED_BY')

    @classmethod
    def make_new_user(cls, username, clear_password):
        password_sha256 = hashlib.sha256(clear_password.encode()).hexdigest()
        user = User(username=username, password_sha256=password_sha256)
        user.save()
        return user

    def can_annotate_links(self):
        return self.authorization_level >= 2


class GroupContains(StructuredRel):
    added = DateTimeProperty(default_now=True, help_text="Time at which this element was added in the database")


class Group(StructuredNode, BaseElement):
    """
    User created groups for works or other
    """
    owner = RelationshipFrom('User', 'OWNS', cardinality=neomodel.One)

    label = StringProperty(required=True)
    notes = StringProperty()
    images = RelationshipTo('.iiif.Image', 'GROUP_CONTAINS', model=GroupContains)