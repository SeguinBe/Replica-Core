import neomodel
from neomodel import StructuredNode, StructuredRel, db
from neomodel import StringProperty, DateTimeProperty, ArrayProperty, UniqueIdProperty, EmailProperty, \
    RelationshipFrom, RelationshipTo, Relationship, JSONProperty, IntegerProperty
from flask_restplus import fields, Model
from datetime import datetime, timedelta


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
                m = api.models[cls.get_model_name(relationship._raw_class)]
                if cardinality == neomodel.One:
                    result[relationship_name] = fields.Nested(m, required=True)
                elif cardinality == neomodel.ZeroOrOne:
                    result[relationship_name] = fields.Nested(m)
                else:
                    result[relationship_name] = fields.List(fields.Nested(m),
                                                            required=True)
        return result

    @classmethod
    def add_schema(cls, api, extended=False):
        class_name = cls.get_model_name(str(cls.__name__)) + ('_ext' if extended else '')
        api.models[class_name] = Model(class_name, cls._get_schema(api, extended))

    @staticmethod
    def get_model_name(raw_name):
        return raw_name.split('.')[-1]

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
        key_order = {cho.id: cho for cho in unordered_results}
        return [key_order[_id] for _id in _ids]

    @classmethod
    def get_elements_created_since(cls, time=datetime.today() - timedelta(1)):
        # return cls.nodes.filter(added__gt=time.timestamp())
        query = "MATCH (a) WHERE a.added>{timestamp} RETURN a ORDER BY a.added DESC"
        results, meta = db.cypher_query(query, {'obj_type': cls.__name__, 'timestamp': time.timestamp()})
        return [cls.inflate(r[0]) for r in results]