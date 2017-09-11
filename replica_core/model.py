import neomodel
from neomodel import StructuredNode, StructuredRel, db
from neomodel import StringProperty, DateTimeProperty, ArrayProperty, UniqueIdProperty, EmailProperty, \
    RelationshipFrom, RelationshipTo, Relationship, JSONProperty, IntegerProperty
from typing import List, Union, Tuple
from flask_restplus import fields, Model
import hashlib
import pytz
from datetime import datetime, timedelta


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


class BaseElement:
    __non_extended_relationships__ = []
    __do_not_marshall_properties__ = []
    __do_not_marshall_relationships__ = []
    added = DateTimeProperty(default_now=True, help_text="Time at which this element was added in the database")
    uid = UniqueIdProperty(help_text='Internal Unique Identifier')

    @classmethod
    def _get_schema(cls, api, extended=False):
        result = dict()
        conversion_dict = {
            StringProperty: fields.String,
            DateTimeProperty: fields.DateTime,
            JSONProperty: fields.Raw,
            EmailProperty: fields.String,
            UniqueIdProperty: fields.String,
            ArrayProperty: fields.List(fields.String, required=True),
            IntegerProperty: fields.Integer
        }
        for property_name, property in cls.__all_properties__:
            if property_name not in cls.__do_not_marshall_properties__:
                d = conversion_dict[property.__class__]
                if isinstance(d, fields.List):
                    result[property_name] = d
                else:
                    result[property_name] = d(description=property.help_text,
                                              required=property.required or (property.default is not None))
        for relationship_name, relationship in cls.__all_relationships__:
            if relationship_name in cls.__do_not_marshall_relationships__:
                continue
            if extended or relationship_name in cls.__non_extended_relationships__:
                cardinality = relationship.manager  # type: neomodel.RelationshipManager
                if cardinality == neomodel.One:
                    result[relationship_name] = fields.Nested(api.models[relationship._raw_class], required=True)
                elif cardinality == neomodel.ZeroOrOne:
                    result[relationship_name] = fields.Nested(api.models[relationship._raw_class])
                else:
                    result[relationship_name] = fields.List(fields.Nested(api.models[relationship._raw_class]),
                                                            required=True)
        return result

    @classmethod
    def add_schema(cls, api, extended=False):
        class_name = str(cls.__name__) + ('_ext' if extended else '')
        api.models[class_name] = Model(class_name, cls._get_schema(api, extended))

    def to_dict(self, extended=False):
        result = {**self.__properties__}  # copy to avoid modifications
        for relationship_name, relationship in self.__all_relationships__:
            if relationship_name in self.__do_not_marshall_relationships__:
                continue
            if extended or relationship_name in self.__non_extended_relationships__:
                elements = [n.to_dict() for n in getattr(self, relationship_name).order_by('added').all()]
                # print(elements)
                if relationship.manager == neomodel.One or \
                                relationship.manager == neomodel.ZeroOrOne:
                    elements = elements[0] if len(elements) > 0 else None
                if elements is not None:
                    result[relationship_name] = elements
        return result

    @classmethod
    def get_by_id(cls, _id):
        query = "MATCH (a) WHERE id(a)={id} RETURN a"
        results, meta = db.cypher_query(query, {'id': _id})
        return cls.inflate(results[0][0]) if len(results) > 0 else None

    @classmethod
    def get_by_ids(cls, _ids):
        query = "MATCH (a) WHERE id(a) IN {ids} RETURN a"
        results, meta = db.cypher_query(query, {'ids': _ids})
        unordered_results = [cls.inflate(r[0]) for r in results]
        key_order = {cho.id : cho for cho in unordered_results}
        return [key_order[_id] for _id in _ids]

    @classmethod
    def get_elements_created_since(cls, time=datetime.today() - timedelta(1)):
        # return cls.nodes.filter(added__gt=time.timestamp())
        query = "MATCH (a) WHERE a.added>{timestamp} RETURN a ORDER BY a.added DESC"
        results, meta = db.cypher_query(query, {'obj_type': cls.__name__, 'timestamp': time.timestamp()})
        return [cls.inflate(r[0]) for r in results]


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
    groups = RelationshipFrom('Group', 'GROUP_CONTAINS')

    links = RelationshipFrom('VisualLink', 'LINKS')


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


class VisualLink(StructuredNode, BaseElement):
    class Type:
        PROPOSAL = 'PROPOSAL'
        DUPLICATE = 'DUPLICATE'
        POSITIVE = 'POSITIVE'
        NEGATIVE = 'NEGATIVE'
        UNDEFINED = 'UNDEFINED'
        VALID_TYPES = [DUPLICATE, POSITIVE, NEGATIVE, UNDEFINED]
        ALL_TYPES = VALID_TYPES + [PROPOSAL]

    # User that proposed or created the link
    creator = RelationshipTo('User', 'CREATED_BY', cardinality=neomodel.One)

    type = StringProperty(default=Type.PROPOSAL)
    # If link was validated/specified
    annotated = DateTimeProperty()
    annotator = RelationshipTo('User', 'ANNOTATED_BY', cardinality=neomodel.ZeroOrOne)

    # Integer value for relative strength encoding
    strength = IntegerProperty()

    images = RelationshipTo('Image', 'LINKS')

    @classmethod
    def get_from_images(cls, img1_uid: str, img2_uid: str) -> Union[None, 'VisualLink']:
        results, _ = db.cypher_query('''MATCH (i2:Image)<-[:LINKS]-(l:VisualLink)-[:LINKS]->(i1:Image)
                                        WHERE i1.uid={img1} and i2.uid={img2}
                                        RETURN l''',
                                     dict(img1=img1_uid, img2=img2_uid))
        if len(results) > 0:
            return VisualLink.inflate(results[0][0])
        else:
            return None

    def annotate(self, user: 'User', link_type: 'Type'):
        if link_type not in VisualLink.Type.VALID_TYPES:
            raise ValueError('Type is invalid : {}'.format(link_type))
        with db.transaction:
            self.annotated = datetime.utcnow().replace(tzinfo=pytz.utc)
            self.type = link_type
            self.save()
            old_annotator = self.annotator.single()
            if old_annotator:
                self.annotator.disconnect(old_annotator)
            self.annotator.connect(user)

    def remove_annotation(self, user=None):
        with db.transaction:
            old_annotator = self.annotator.single()
            if old_annotator and ((user is not None) or user == old_annotator):
                self.annotated = None
                self.type = VisualLink.Type.PROPOSAL
                self.save()
                self.annotator.disconnect(old_annotator)

    @classmethod
    def create_proposal(cls, img1: Image, img2: Image, user: 'User', exist_ok=True):
        if not (img1 and img2):
            raise ValueError('Some img do not exist')
        if img1 == img2:
            raise ValueError('The two images are the same')
        if img1.cho.single() == img2.cho.single():
            raise ValueError('Can not connect two images of the same element')

        link = cls.get_from_images(img1.uid, img2.uid)
        if link is not None:
            if exist_ok:
                return link
            else:
                raise ValueError('Images are already linked')
        with db.transaction:
            link = VisualLink()
            link.save()
            link.images.connect(img1)
            link.images.connect(img2)
            link.creator.connect(user)
        return link

    @classmethod
    def get_random_proposals(cls, limit=10) -> List['VisualLink']:
        results, _ = db.cypher_query('''MATCH (a:VisualLink) where a.type={link_type}
                                        RETURN a, rand() as r
                                        ORDER BY r LIMIT {limit}''',
                                     dict(link_type=VisualLink.Type.PROPOSAL, limit=limit))
        return [VisualLink.inflate(r[0]) for r in results]

    def dict_from_source(self, image_source: Image):
        d = self.to_dict()
        images = self.images.all()
        if images[0] == image_source:
            target_image = images[1]
        else:
            target_image = images[0]
        d['image'] = target_image.to_dict()
        return d


class TripletComparison(StructuredNode, BaseElement):
    anchor = RelationshipTo('Image', 'ANCHOR', cardinality=neomodel.One)
    positive = RelationshipTo('Image', 'POSITIVE', cardinality=neomodel.ZeroOrOne)
    negative = RelationshipTo('Image', 'NEGATIVE', cardinality=neomodel.ZeroOrOne)
    candidates = RelationshipTo('Image', 'CANDIDATE', cardinality=neomodel.OneOrMore)

    # If annotated
    annotated = DateTimeProperty()
    annotator = RelationshipTo('User', 'ANNOTATED_BY', cardinality=neomodel.ZeroOrOne)

    @classmethod
    def get_from_images(self, anchor_uid, cand1_uid, cand2_uid):
        results, _ = db.cypher_query('''MATCH (a:Image)<-[:ANCHOR]-(l:TripletComparison)-[:CANDIDATE]->(i1:Image)
                                        WHERE a.uid={a_uid} and i1.uid={i1_uid} and i2.uid={i2_uid}
                                        and (l)-[:CANDIDATE]->(i2:Image)
                                        RETURN l''',
                                     dict(a_uid=anchor_uid, i1_uid=cand1_uid, i2_uid=cand2_uid))
        if len(results) > 0:
            return TripletComparison.inflate(results[0][0])
        else:
            return None

    @classmethod
    def create_proposal(cls, anchor: Image, candidate1: Image, candidate2: Image, user: 'User', exist_ok=True):
        if not (anchor and candidate1 and candidate2):
            raise ValueError('Some img do not exist')
        if anchor == candidate1 or anchor == candidate2 or candidate1 == candidate2:
            raise ValueError('Two images are the same')
        if len(set([c.cho.single() for c in [anchor, candidate1, candidate2]])) < 3:
            raise ValueError('Can not connect two images of the same element')

        comparison = cls.get_from_images(anchor.uid, candidate1.uid, candidate2.uid)
        if comparison is not None:
            if exist_ok:
                return comparison
            else:
                raise ValueError('Images are already part of a comparison')
        with db.transaction:
            comparison = TripletComparison()
            comparison.save()
            comparison.anchor.connect(anchor)
            comparison.candidates.connect(candidate1)
            comparison.candidates.connect(candidate2)
            comparison.creator.connect(user)
        return comparison

    def annotate(self, user: 'User', positive_img: Image, negative_img: Image):
        if positive_img not in self.candidates or negative_img not in self.candidates:
            raise ValueError('The images are not corresponding to this triplet')
        with db.transaction:
            self.annotated = datetime.utcnow().replace(tzinfo=pytz.utc)
            self.save()
            old_annotator = self.annotator.single()
            if old_annotator:
                self.annotator.disconnect(old_annotator)
                self.positive.disconnect(self.positive.single())
                self.negative.disconnect(self.negative.single())
            self.annotator.connect(user)
            self.positive.connect(positive_img)
            self.negative.connect(negative_img)

    @classmethod
    def get_random_proposals(cls, limit=10) -> List['TripletComparison']:
        results, _ = db.cypher_query('''MATCH (a:TripletComparison) where a.annotated=null
                                        RETURN a, rand() as r
                                        ORDER BY r LIMIT {limit}''',
                                     dict(limit=limit))
        return [TripletComparison.inflate(r[0]) for r in results]


class User(StructuredNode, BaseElement):
    __do_not_marshall_properties__ = ['password_sha256', 'email']

    username = StringProperty(required=True, unique_index=True)
    password_sha256 = StringProperty(required=True)
    email = EmailProperty(required=False)

    groups = RelationshipTo('Group', 'OWNS')
    created_links = RelationshipFrom('VisualLink', 'CREATED_BY')

    @classmethod
    def make_new_user(cls, username, clear_password):
        password_sha256 = hashlib.sha256(clear_password.encode()).hexdigest()
        user = User(username=username, password_sha256=password_sha256)
        user.save()
        return user


class Group(StructuredNode, BaseElement):
    """
    User created groups for works or other
    """
    owner = RelationshipFrom('User', 'OWNS', cardinality=neomodel.One)

    notes = StringProperty()

    images = RelationshipTo('Image', 'GROUP_CONTAINS')


def get_subgraph(image_uids: List[str], graph_depth=3) -> (List[Image], List[Tuple[str, str, VisualLink]]):
    results, _ = db.cypher_query("""
                                    MATCH (n:Image) where n.uid IN {image_uids}
                                    WITH DISTINCT(n) as n_previous
                                    """ +
                                 """MATCH (n_previous:Image)<-[]-(:VisualLink)-[]->(n:Image)
                                    WITH DISTINCT(n) as n_previous
                                    """ * graph_depth +
                                 """WITH COLLECT(n_previous) as nodes
                                    MATCH (n1:Image)<-[]-(v:VisualLink)-[]->(n2:Image) where n1 in nodes and n2 in nodes and id(n1)<id(n2)
                                    return nodes, collect([n1.uid, n2.uid, v]) as links
                                    """,
                                 dict(image_uids=image_uids))

    if len(results)> 0:
        nodes_data, links_data = results[0]
    else:
        nodes_data, links_data = [], []
    nodes, links = [Image.inflate(d) for d in nodes_data], [(uid1, uid2, VisualLink.inflate(d)) for uid1, uid2, d in links_data]

    missing_image_uids = set(image_uids).difference([img.uid for img in nodes])
    nodes += [Image.nodes.get(uid=uid) for uid in missing_image_uids]

    return nodes, links

