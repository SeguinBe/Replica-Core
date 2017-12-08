import neomodel
from neomodel import StructuredNode, StructuredRel, db
from neomodel import StringProperty, DateTimeProperty, ArrayProperty, UniqueIdProperty, EmailProperty, \
    RelationshipFrom, RelationshipTo, Relationship, JSONProperty, IntegerProperty
from flask_restplus import fields
import hashlib
from typing import List
from .base import BaseElement, SerializationLevel


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

    @classmethod
    def _get_schema(cls, api, level=SerializationLevel.DEFAULT):
        schema = super()._get_schema(api, level)
        schema['nb_images'] = fields.Integer(required=True, description='Number of images in the group')
        return schema

    def to_dict(self, level=SerializationLevel.DEFAULT):
        result = super().to_dict(level)
        result['nb_images'] = len(self.images)
        return result

    def add_images(self, images: List['Image']):
        already_added_uids = {img.uid for img in self.images.all()}
        for image in images:
            if image.uid in already_added_uids:
                continue
            self.images.connect(image)

    def update_group(self, label, notes, new_images):
        self.label = label
        self.notes = notes
        self.save()
        previous_images = {img.uid: img for img in self.images.all()}
        for image in new_images:
            if image.uid in previous_images.keys():
                del previous_images[image.uid]
            else:
                self.images.connect(image)
        for image in previous_images.values():
            self.images.disconnect(image)

    @classmethod
    def create_group(cls, user: User, label: str, images: List['Image']):
        with db.transaction:
            group = Group(label=label)
            group.save()
            group.owner.connect(user)
            group.add_images(images)
        return group
