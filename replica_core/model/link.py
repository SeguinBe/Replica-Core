import neomodel
from neomodel import StructuredNode, StructuredRel, db
from neomodel import StringProperty, DateTimeProperty, ArrayProperty, UniqueIdProperty, EmailProperty, \
    RelationshipFrom, RelationshipTo, Relationship, JSONProperty, IntegerProperty, FloatProperty
from typing import List, Union, Tuple, Optional
import pytz
from datetime import datetime, timedelta
from .base import BaseElement
from .iiif import CHO, Collection, Image
from .user import User, Group, GroupContains


class LinkImageRel(StructuredRel):
    box_x = FloatProperty()
    box_y = FloatProperty()
    box_h = FloatProperty()
    box_w = FloatProperty()

    def set_dict(self, **kwargs):
        self.box_x = kwargs['box_x']
        self.box_y = kwargs['box_y']
        self.box_h = kwargs['box_h']
        self.box_w = kwargs['box_w']


class VisualLink(StructuredNode, BaseElement):
    class Type:
        PROPOSAL = 'PROPOSAL'
        DUPLICATE = 'DUPLICATE'
        NONDUPLICATE = 'NON-DUPLICATE'
        POSITIVE = 'POSITIVE'
        NEGATIVE = 'NEGATIVE'
        UNDEFINED = 'UNDEFINED'
        VALID_TYPES = [DUPLICATE, NONDUPLICATE, POSITIVE, NEGATIVE, UNDEFINED]
        ALL_TYPES = VALID_TYPES + [PROPOSAL]

    # User that proposed or created the link
    creator = RelationshipTo('.user.User', 'CREATED_BY', cardinality=neomodel.One)

    type = StringProperty(default=Type.PROPOSAL)
    # If link was validated/specified
    annotated = DateTimeProperty()
    annotator = RelationshipTo('.user.User', 'ANNOTATED_BY', cardinality=neomodel.ZeroOrOne)

    # Integer value for relative strength encoding
    strength = IntegerProperty()

    # If it comes from a bot-prediction
    prediction_score = FloatProperty()
    # Spatial overlap if it was computed, useful to distinguish complete duplicate to partial ones
    spatial_spread = FloatProperty()

    images = RelationshipTo('.iiif.Image', 'LINKS', model=LinkImageRel)

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

    def plot(self):
        from IPython.core.display import display, HTML
        html_code = """
        <span>
        UID : {} <br>
        Type : {} <br>
        Creator : {} <br>
        Annotator : {}
        </span>
        <div style="float:left;">
        <img style="display:inline-block;" src="{}/full/300,/0/default.jpg",width=300/>
        <img style="display:inline-block;" src="{}/full/300,/0/default.jpg",width=300/>
        </div>
        """.format(self.uid, self.type, self.creator.get().username, self.annotator.get_or_none(), *(img.iiif_url for img in self.images))
        display(HTML(html_code))

    @classmethod
    def get_from_images(cls, img1_uid: str, img2_uid: str, user=None) -> Union[None, 'VisualLink']:
        results, _ = db.cypher_query('''MATCH (i2:Image)<-[:LINKS]-(l:'''+str(cls.__name__)+''')-[:LINKS]->(i1:Image)
                                        WHERE i1.uid={img1} and i2.uid={img2}
                                        RETURN l''',
                                     dict(img1=img1_uid, img2=img2_uid))
        if len(results) > 0:
            return cls.inflate(results[0][0])
        else:
            return None

    @classmethod
    def create_proposal(cls, img1: Image, img2: Image, user: 'User', exist_ok=True):
        if not (img1 and img2):
            raise ValueError('Some img do not exist')
        if img1 == img2:
            raise ValueError('The two images are the same')
        if img1.cho.single() == img2.cho.single():
            raise ValueError('Can not connect two images of the same element')

        link = cls.get_from_images(img1.uid, img2.uid, user)
        if link is not None:
            if exist_ok:
                return link
            else:
                raise ValueError('Images are already linked')
        with db.transaction:
            link = cls()
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


class PersonalLink(StructuredNode, BaseElement):
    # User that proposed or created the link
    creator = RelationshipTo('.user.User', 'CREATED_BY', cardinality=neomodel.One)

    type = StringProperty(default='PERSONAL')

    images = RelationshipTo('.iiif.Image', 'LINKS')

    @classmethod
    def get_from_images(cls, img1_uid: str, img2_uid: str, user) -> Union[None, 'VisualLink']:
        results, _ = db.cypher_query('''MATCH (i2:Image)<-[:LINKS]-(l:'''+str(cls.__name__)+''')-[:LINKS]->(i1:Image), (user:User)<-[CREATED_BY]-(l)
                                        WHERE i1.uid={img1} and i2.uid={img2} and user.uid={user_uid}
                                        RETURN l''',
                                     dict(img1=img1_uid, img2=img2_uid, user_uid=user.uid))
        if len(results) > 0:
            return cls.inflate(results[0][0])
        else:
            return None

    @classmethod
    def create_link(cls, img1: Image, img2: Image, user: 'User') -> 'PersonalLink':
        if not (img1 and img2):
            raise ValueError('Some img do not exist')
        if img1 == img2:
            raise ValueError('The two images are the same')
        if img1.cho.single() == img2.cho.single():
            raise ValueError('Can not connect two images of the same element')

        link = cls.get_from_images(img1.uid, img2.uid, user)
        if link is not None:
            return link
            #raise ValueError('Images are already linked')
        with db.transaction:
            link = cls()
            link.save()
            link.images.connect(img1)
            link.images.connect(img2)
            link.creator.connect(user)
        return link


class TripletComparison(StructuredNode, BaseElement):
    anchor = RelationshipTo('.iiif.Image', 'ANCHOR', cardinality=neomodel.One)
    positive = RelationshipTo('.iiif.Image', 'POSITIVE', cardinality=neomodel.ZeroOrOne)
    negative = RelationshipTo('.iiif.Image', 'NEGATIVE', cardinality=neomodel.ZeroOrOne)
    candidates = RelationshipTo('.iiif.Image', 'CANDIDATE', cardinality=neomodel.OneOrMore)

    # If annotated
    annotated = DateTimeProperty()
    annotator = RelationshipTo('.user.User', 'ANNOTATED_BY', cardinality=neomodel.ZeroOrOne)

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