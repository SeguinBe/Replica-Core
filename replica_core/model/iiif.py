import neomodel
from neomodel import StructuredNode, StructuredRel, db
from neomodel import StringProperty, DateTimeProperty, ArrayProperty, UniqueIdProperty, EmailProperty, \
    RelationshipFrom, RelationshipTo, Relationship, JSONProperty, IntegerProperty
from typing import List, Union, Tuple, Optional
import re
from flask_restplus import fields, Model
from .base import BaseElement, SerializationLevel
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

    def get_date_range_from_fields(self, labels: List[str]) -> (Optional[int], Optional[int]):
        metadata_dict = {d['label'].lower(): d['value'] for d in self.raw_metadata}
        for l in labels:
            maybe_date_range = self._get_date_range_from_value(metadata_dict.get(l.lower()))
            if maybe_date_range is not None:
                return maybe_date_range
        return None, None

    @staticmethod
    def _get_date_range_from_value(f: str) -> Optional[Tuple[int, int]]:
        if isinstance(f, int):
            return f, f
        if isinstance(f, str):
            # Just a number
            if f.isdigit():
                return int(f), int(f)
            default = '\?+'
            date = '[0-9]+'
            # 1240-1320 , ????-1200, ???-1234
            pattern = '({default}|{date})-({default}|{date})'.format(default=default, date=date)
            if re.fullmatch(pattern, f):
                s1, s2 = f.split('-')
                b, e = None, None
                if s1.isdigit():
                    b = int(s1)
                if s2.isdigit():
                    e = int(s2)
                # Cases of 1722-24 or 1722-3
                if e is not None and b is not None:
                    if e < 10:
                        e += (b // 10)*10
                    if e < 100:
                        e += (b // 100)*100
                    if e < b:
                        print('Weird value', f)
                        b, e = min(b, e), max(b, e)
                return b, e
            # c. 1565
            pattern = '(c|c.|circa)\W?{date}'.format(date=date)
            if re.fullmatch(pattern, f):
                s1 = re.findall(date, f)[0]
                return int(s1)-5, int(s1)+5
            # 1920s
            pattern = '{date}s'.format(date=date)
            if re.fullmatch(pattern, f):
                s1 = re.findall(date, f)[0]
                return int(s1), int(s1)+10

            #all_dates = re.findall('[0-9]{4}', f)
            #if len(all_dates) == 1:
            #    d = int(all_dates[0])
            #    return d, d
            #if len(all_dates) == 2:
            #    d_b, d_e = [int(d) for d in all_dates]
            #    return d_b, d_e
        return None


class Collection(StructuredNode, IsPartOfCollection, BaseElement, IIIFMetadata):
    __do_not_marshall_relationships__ = ['elements']

    children_collections = RelationshipTo('Collection', 'COLL_CONTAINS')

    elements = RelationshipTo('CHO', 'COLL_CONTAINS')

    @classmethod
    def _get_schema(cls, api, level=SerializationLevel.DEFAULT):
        schema = super()._get_schema(api, level)
        schema['nb_elements'] = fields.Integer(required=True, description='Number of elements in the collection')
        if level >= SerializationLevel.EXTENDED:
            schema['parent_collection_hierarchy'] = fields.List(fields.Nested(api.models[str(Collection.__name__)]))
        return schema

    def get_total_number_of_elements(self):
        # Might be a bit slow... :(
        results, _ = self.cypher("""
        MATCH (c:Collection)-[:COLL_CONTAINS*]->(n1:CHO) WHERE id(c)={self}
        RETURN COUNT(n1)""")
        return results[0][0]

    def to_dict(self, level=SerializationLevel.DEFAULT):
        result = super().to_dict(level)
        result['nb_elements'] = len(self.elements)
        if level >= SerializationLevel.EXTENDED:
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
    # __do_not_marshall_relationships__ = ['images']
    __non_extended_relationships__ = ['images']
    __relationship_serialization__ = {'images': SerializationLevel.BASE}

    # IIIF data
    related = StringProperty()

    # Parsed Metadata
    author = StringProperty()
    title = StringProperty()
    date_begin = IntegerProperty()
    date_end = IntegerProperty()

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
    def get_from_image_uids(cls, image_uids: List[str]) -> List['CHO']:
        results, _ = db.cypher_query(
            "match (n1:CHO)-[IS_SHOWN_BY]-(n2:Image) where n2.uid IN {image_uids} return n1, n2.uid",
            params={'image_uids': image_uids}
        )
        key_order = {r[1]: cls.inflate(r[0]) for r in results}
        return [key_order[_id] for _id in image_uids]

    @classmethod
    def get_image_uids_from_ids(cls, ids: List[int]) -> List['str']:
        results, _ = db.cypher_query(
            "match (n1:CHO)-[IS_SHOWN_BY]-(n2:Image) where id(n1) IN {ids} return n1.uid, n2.uid",
            params={'ids': ids}
        )
        return [n[1] for n in results]

    @classmethod
    def _get_schema(cls, api, level=SerializationLevel.DEFAULT):
        schema = super()._get_schema(api, level)
        #schema['images'] = fields.List(fields.Nested(api.models[str(Image.__name__)]),
        #                                                        required=True)
        if level >= SerializationLevel.EXTENDED:
            schema['parent_collection_hierarchy'] = fields.List(fields.Nested(api.models[str(Collection.__name__)]),
                                                                required=True)
        return schema

    def to_dict(self, level=SerializationLevel.DEFAULT):
        result = super().to_dict(level)
        if level >= SerializationLevel.EXTENDED:
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
    __do_not_marshall_relationships__ = ['links', 'groups']
    __non_extended_relationships__ = ['cho']
    __relationship_serialization__ = {'cho': SerializationLevel.BASE}

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
    def _get_schema(cls, api, level=False):
        schema = super()._get_schema(api, level)
        if level >= SerializationLevel.EXTENDED:
            schema['links'] = fields.List(fields.Nested(api.models['Link_from_source']), required=True)
        return schema

    def to_dict(self, level=SerializationLevel.DEFAULT):
        result = super().to_dict(level)
        if level >= SerializationLevel.EXTENDED:
            result['links'] = [l.dict_from_source(self) for l in self.links]
        return result
