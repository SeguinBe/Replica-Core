import neomodel
from neomodel import StructuredNode, StructuredRel, db
from neomodel import StringProperty, DateTimeProperty, ArrayProperty, UniqueIdProperty, EmailProperty, \
    RelationshipFrom, RelationshipTo, Relationship, JSONProperty, IntegerProperty
from typing import List, Union, Tuple, Optional
import re
from flask_restplus import fields, Model
from .base import BaseElement
from .user import GroupContains


class IsPartOfCollection:
    parent_collection = RelationshipFrom('Collection', 'COLL_CONTAINS', cardinality=neomodel.ZeroOrOne)

    def get_parent_collections_hierarchy(self) -> List['Collection']:
        results, _ = self.cypher("""
        MATCH p=(c:Collection)-[:COLL_CONTAINS*]->(n1) WHERE id(n1)={self}
        WITH COLLECT(p) as paths, MAX(LENGTH(p)) as max_length
        RETURN FILTER(path IN paths
          WHERE length(path)= max_length) AS longest_path""")
        results = results[0][0]
        if len(results) == 0:
            colls = []
        else:
            colls = results[0].nodes[:-1]
        return [Collection.inflate(n) for n in colls]


class IIIFMetadata:
    # IIIF data
    uri = StringProperty(unique_index=True, required=True, help_text='URI of the Resource')
    label = StringProperty(default='', help_text='IIIF label')
    description = StringProperty(help_text='IIIF description')
    thumbnail = StringProperty(help_text='IIIF thumbnail')
    attribution = StringProperty(help_text='IIIF attribution')
    license = StringProperty(help_text='IIIF license')
    logo = StringProperty(help_text='IIIF logo')
    raw_metadata = JSONProperty(default={}, help_text='IIIF Raw metadata field')

    def get_metadata(self, label: str, default=None):
        metadata_dict = {d['label']: d['value'] for d in self.raw_metadata}
        return metadata_dict.get(label, default)

    def get_date_from_fields(self, labels: List[str]):
        metadata_dict = {d['label']: d['value'] for d in self.raw_metadata}
        for l in labels:
            maybe_date = self._get_date_from_value(metadata_dict.get(l))
            if maybe_date is not None:
                return maybe_date
        return None

    @staticmethod
    def _get_date_from_value(f: str) -> Optional[int]:
        if isinstance(f, int):
            return f
        if isinstance(f, str):
            all_dates = re.findall('[0-9]{4}', f)
            if len(all_dates) > 0:
                return round(sum([int(d) for d in all_dates])/len(all_dates))
        return None


class Collection(StructuredNode, IsPartOfCollection, BaseElement, IIIFMetadata):
    __do_not_marshall_relationships__ = ['elements']

    children_collections = RelationshipTo('Collection', 'COLL_CONTAINS')

    elements = RelationshipTo('CHO', 'COLL_CONTAINS')

    @classmethod
    def _get_schema(cls, api, extended=False):
        schema = super()._get_schema(api, extended)
        schema['nb_elements'] = fields.Integer(required=True, description='Number of elements in the collection')
        if extended:
            schema['parent_collection_hierarchy'] = fields.List(fields.Nested(api.models[str(Collection.__name__)]))
        return schema

    def get_total_number_of_elements(self):
        # Might be a bit slow... :(
        results, _ = self.cypher("""
        MATCH (c:Collection)-[:COLL_CONTAINS*]->(n1:CHO) WHERE id(c)={self}
        RETURN COUNT(n1)""")
        return results[0][0]

    def to_dict(self, extended=False):
        result = super().to_dict(extended)
        result['nb_elements'] = len(self.elements)
        if extended:
            result['parent_collection_hierarchy'] = [d.to_dict() for d in self.get_parent_collections_hierarchy()]
        return result

    @classmethod
    def get_top_collections(cls) -> List['Collection']:
        results, _ = db.cypher_query(
            "match (n1:Collection) where not (n1)<-[:COLL_CONTAINS]-() return n1"
        )
        return [Collection.inflate(n[0]) for n in results]

    def delete_collection_and_children(self):
        # WARNING : if links are part of some of the elements, it's not going to work well
        self.cypher("""
        match (c:Collection)-[:COLL_CONTAINS|IS_SHOWN_BY*..3]->(n) where id(c)={self} optional match (n)-[r]-()
        delete c, r, n""")


class CHO(StructuredNode, IsPartOfCollection, BaseElement, IIIFMetadata):
    """Rough Equivalent of the Manifest element in IIIF Presentation API"""
    __non_extended_relationships__ = ['images']

    # IIIF data
    related = StringProperty()

    # Parsed Metadata
    author = StringProperty()
    title = StringProperty()
    date = IntegerProperty()

    # Relationships
    images = RelationshipTo('Image', 'IS_SHOWN_BY', cardinality=neomodel.OneOrMore)

    # same_as = Relationship('CHO', 'SAME_AS')

    def get_first_image(self):
        images = self.images.order_by('added').all()
        if len(images) > 0:
            return images[0]
        else:
            return None

    @classmethod
    def search(cls, query, nb_results=20) -> List['CHO']:
        results, _ = db.cypher_query(
            # "START n=CHO:node_auto_index('name:{query}') RETURN n",
            "match (n1:CHO) where n1.description contains {query} return n1 LIMIT {nb_results}",
            params={'query': query, 'nb_results': nb_results}
        )
        return [CHO.inflate(n[0]) for n in results]

    @classmethod
    def get_from_image_uid(cls, image_uid: str) -> 'CHO':
        results, _ = db.cypher_query(
            "match (n1:CHO)-[IS_SHOWN_BY]-(n2:Image) where n2.uid = {image_uid} return n1",
            params={'image_uid': image_uid}
        )
        return CHO.inflate(results[0][0])

    @classmethod
    def _get_schema(cls, api, extended=False):
        schema = super()._get_schema(api, extended)
        if extended:
            schema['parent_collection_hierarchy'] = fields.List(fields.Nested(api.models[str(Collection.__name__)]),
                                                                required=True)
        return schema

    def to_dict(self, extended=False):
        result = super().to_dict(extended)
        if extended:
            result['parent_collection_hierarchy'] = [d.to_dict() for d in self.get_parent_collections_hierarchy()]
        return result

    @classmethod
    def get_random(cls, limit=10) -> List['CHO']:
        results, _ = db.cypher_query('''MATCH (a:CHO)
                                        RETURN a, rand() as r
                                        ORDER BY r LIMIT {limit}''',
                                     dict(limit=limit))
        return [CHO.inflate(r[0]) for r in results]


class Image(StructuredNode, BaseElement):
    __do_not_marshall_relationships__ = ['links']
    # __non_extended_relationships__ = ['cho']

    # Location of image (one of the two at least)
    iiif_url = StringProperty(required=True, unique_index=True, help_text='IIIF Url of the Resource')
    width = IntegerProperty(required=True)
    height = IntegerProperty(required=True)

    # Additional info
    # provider = StringProperty()
    # data_provider = StringProperty()

    # Object
    cho = RelationshipFrom('CHO', 'IS_SHOWN_BY', cardinality=neomodel.One)
    # User Groups
    groups = RelationshipFrom('.user.Group', 'GROUP_CONTAINS', model=GroupContains)

    links = RelationshipFrom('.link.VisualLink', 'LINKS')


    @classmethod
    def _get_schema(cls, api, extended=False):
        schema = super()._get_schema(api, extended)
        if extended:
            schema['links'] = fields.List(fields.Nested(api.models['Link_from_source']), required=True)
        return schema

    def to_dict(self, extended=False):
        result = super().to_dict(extended)
        if extended:
            result['links'] = [l.dict_from_source(self) for l in self.links]
        return result