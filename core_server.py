import neomodel
from flask import Flask, request, g, Response, stream_with_context
from flask_restplus import Api, Resource, fields
from flask_prometheus import monitor
from werkzeug.exceptions import BadRequest
import requests
from collections import namedtuple
from functools import partial
import json
from threading import Lock
try:
    import better_exceptions
except:
    pass

from replica_core import model, auth
from replica_core.model import SerializationLevel

app = Flask(__name__, static_folder='static', static_url_path='')
app.config.SWAGGER_UI_JSONEDITOR = True


@app.route('/')
def base_file():
    print(str(request.headers['Host']))
    return app.send_static_file("base.html")


@app.route('/screensaver')
def screensaver():
    return app.send_static_file("screensaver.html")


api = Api(app, doc='/api/', title='Replica API')

app.config.from_object('config')
# app.config.from_envvar('YOURAPPLICATION_SETTINGS')

neomodel.config.DATABASE_URL = app.config['DATABASE_URL']

classes = [model.Image, model.Collection, model.CHO, model.Group,
           model.VisualLink, model.PersonalLink, model.TripletComparison, model.User]
for c in classes:
    c.add_schema(api, level=model.SerializationLevel.BASE)
for c in classes:
    c.add_schema(api, level=model.SerializationLevel.NORMAL)
api.clone('Link_from_source', api.models['VisualLink'], {'image': fields.Nested(api.models['Image'])})
for c in classes:
    c.add_schema(api, level=model.SerializationLevel.EXTENDED)


model_box = api.model('Box', {'y': fields.Float(required=True),
                              'x': fields.Float(required=True),
                              'h': fields.Float(required=True),
                              'w': fields.Float(required=True)
                              })

model_img_box = api.clone('ImageBox', api.models['Image'], {'box': fields.Nested(model_box)})
model_cho_box = api.clone('CHOBox', api.models['CHO'])
model_cho_box['images'].container.model = model_img_box

model_collections = api.model('Collections',
                              {'collections': fields.List(fields.Nested(api.models['Collection']), required=True)})
model_groups = api.model('Groups',
                              {'groups': fields.List(fields.Nested(api.models['Group']), required=True)})
model_links = api.model('Links',
                        {'links': fields.List(fields.Nested(api.models['VisualLink_ext']), required=True)})
model_text_search = api.model('TextSearch',
                              {'query': fields.String,
                               'results': fields.List(fields.Nested(api.models['CHO'])),
                               'total': fields.Integer})
model_image_search = api.model('ImageSearch',
                               {'results': fields.List(fields.Nested(api.models['CHO'])),
                                'total': fields.Integer})
model_image_search_region = api.model('ImageSearchRegion',
                                      {'results': fields.List(fields.Nested(model_cho_box)),
                                       'total': fields.Integer})
model_simple_uid = api.model('SimpleUid',
                                      {'uid': fields.String(required=True, description='Unique Identifier')})

model_auth = api.model('Auth', {'token': fields.String(required=True,
                                                       description="JSON Web Token after successful authentication")})


@api.route('/api/stats')
class StatisticsResource(Resource):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        def _fn(link_type):
            return len(model.VisualLink.nodes.filter(type=link_type))

        Stat = namedtuple('Stat', ['key', 'label', 'fn'])
        self.stats = [
            Stat('nb_top_collections', 'Number of registered top collections',
                 lambda: len(model.Collection.get_top_collections())),
            Stat('nb_collections', 'Number of indexed collections (all)', lambda: len(model.Collection.nodes)),
            Stat('nb_elements', 'Number of indexed IIIF manifests', lambda: len(model.CHO.nodes)),
            Stat('nb_images', 'Number of indexed IIIF images', lambda: len(model.Image.nodes)),
            Stat('nb_users', 'Number of registered users', lambda: len(model.User.nodes)),
            Stat('nb_links', 'Number of total links', lambda: len(model.VisualLink.nodes))
        ]

        self.stats.extend([Stat('nb_{}_links'.format(t), 'Number of {} links'.format(t), partial(_fn, t))
                           for t in model.VisualLink.Type.ALL_TYPES])

        self.stats.append(Stat('nb_annotated_triplets', 'Number of annotated triplets',
                               lambda: len(model.TripletComparison.nodes.filter(annotated__isnull=False))))
        self.stats.append(Stat('nb_proposal_triplets', 'Number of proposal triplets',
                               lambda: len(model.TripletComparison.nodes.filter(annotated__isnull=True))))

    model_stat = api.model('Stat', {'key': fields.String(required=True),
                                    'label': fields.String(required=True),
                                    'value': fields.Integer(required=True)})
    model_stats = api.model('Stats', {'stats': fields.List(fields.Nested(model_stat))})

    @api.marshal_with(model_stats)
    def get(self):
        return {
            'stats': [
                {
                    'key': s.key,
                    'label': s.label,
                    'value': s.fn()
                } for s in self.stats
                ]
        }


@api.route('/api/collections')
class CollectionsResource(Resource):
    @api.marshal_with(model_collections)
    def get(self):
        return {'collections': [coll.to_dict() for coll in model.Collection.nodes.all()]}


@api.route('/api/collection/<string:uid>')
class CollectionResource(Resource):
    @api.marshal_with(api.models['Collection_ext'])
    def get(self, uid):
        coll = model.Collection.nodes.get_or_none(uid=uid)  # type: model.Collection
        if coll is None:
            raise BadRequest("{} is not a collection".format(uid))
        return coll.to_dict(level=SerializationLevel.EXTENDED)


@api.route('/api/group/<string:uid>')
class GroupResrouce(Resource):
    @api.marshal_with(api.models['Group_ext'])
    def get(self, uid):
        group = model.Group.nodes.get_or_none(uid=uid)  # type: model.Group
        if group is None:
            raise BadRequest("{} is not a group".format(uid))
        return group.to_dict(level=SerializationLevel.EXTENDED)

    parser = api.parser()
    parser.add_argument('image_uids', type=list, required=True, location='json')
    parser.add_argument('label', type=str, required=True, location='json')
    parser.add_argument('notes', type=str, default='', location='json')

    @api.expect(parser)
    @auth.login_required
    def put(self, uid):
        current_user = model.User.nodes.get(uid=g.user_uid)
        group = model.Group.nodes.get_or_none(uid=uid)  # type: model.Group
        if group.owner.get() != current_user:
            raise BadRequest('Unauthorized')
        if group is None:
            raise BadRequest("{} is not a group".format(uid))
        args = self.parser.parse_args()
        try:
            images = [model.Image.nodes.get(uid=uid) for uid in args['image_uids']]
        except Exception as e:
            raise BadRequest('Invalid image uid')
        group.update_group(args['label'], args['notes'], images)

    @auth.login_required
    def delete(self, uid):
        current_user = model.User.nodes.get(uid=g.user_uid)
        group = model.Group.nodes.get_or_none(uid=uid)  # type: model.Group
        if group.owner.get() != current_user:
            raise BadRequest('Unauthorized')
        group.delete()


@api.route('/api/group/<string:uid>/add')
class AddImagesGroupResrouce(Resource):
    parser = api.parser()
    parser.add_argument('image_uids', type=list, required=True, location='json')

    @api.expect(parser)
    @auth.login_required
    def post(self, uid):
        current_user = model.User.nodes.get(uid=g.user_uid)
        group = model.Group.nodes.get_or_none(uid=uid)  # type: model.Group
        if group.owner.get() != current_user:
            raise BadRequest('Unauthorized')
        if group is None:
            raise BadRequest("{} is not a group".format(uid))
        args = self.parser.parse_args()
        try:
            images = [model.Image.nodes.get(uid=uid) for uid in args['image_uids']]
        except Exception as e:
            raise BadRequest('Invalid image uid')
        group.add_images(images)


@api.route('/api/group')
class CreateGroupResource(Resource):
    parser = api.parser()
    parser.add_argument('image_uids', type=list, required=True, location='json')
    parser.add_argument('label', type=str, required=True, location='json')

    @api.marshal_with(api.models['Group'])
    @api.expect(parser)
    @auth.login_required
    def post(self):
        current_user = model.User.nodes.get(uid=g.user_uid)
        args = self.parser.parse_args()
        try:
            images = [model.Image.nodes.get(uid=uid) for uid in args['image_uids']]
        except Exception as e:
            raise BadRequest('Invalid image uid')
        group = model.Group.create_group(current_user, args['label'], images)
        return group.to_dict()


@api.route('/api/element/<string:uid>')
class ElementResource(Resource):
    @api.marshal_with(api.models['CHO_ext'])
    def get(self, uid):
        cho = model.CHO.nodes.get_or_none(uid=uid)  # type: model.CHO
        if cho is None:
            raise BadRequest("{} is not an element".format(uid))
        return cho.to_dict(level=SerializationLevel.EXTENDED)


@api.route('/api/element/random')
class LinkResource(Resource):
    parser = api.parser()
    parser.add_argument('nb_elements', type=int, default=1)

    @api.expect(parser)
    @api.marshal_with(api.models['CHO_ext'])
    def get(self):
        args = self.parser.parse_args()
        chos = model.CHO.get_random(limit=args['nb_elements'])
        return [cho.to_dict(level=SerializationLevel.DEFAULT) for cho in chos]


@api.route('/api/image/<string:uid>')
class ImageResource(Resource):
    @api.marshal_with(api.models['Image_ext'])
    def get(self, uid):
        img = model.Image.nodes.get_or_none(uid=uid)  # type: model.Image
        if img is None:
            raise BadRequest("{} is not an image".format(uid))
        return img.to_dict(level=SerializationLevel.EXTENDED)


@api.route('/api/link/<string:uid>')
class LinkResource(Resource):
    @api.marshal_with(api.models['VisualLink_ext'])
    def get(self, uid):
        link = model.VisualLink.nodes.get_or_none(uid=uid)  # type: model.VisualLink
        if link is None:
            raise BadRequest("{} is not a link".format(uid))
        return link.to_dict(level=SerializationLevel.EXTENDED)

        # @auth.login_required
        # def delete(self, uid):
        #    link = model.VisualLink.nodes.get_or_none(uid=uid)  # type: model.VisualLink
        #    if link:
        #        link.delete()
        #        return {}
        #    else:
        #        raise BadRequest("{} is not a link".format(uid))


@api.route('/api/link/create')
class LinkResource(Resource):
    parser = api.parser()
    parser.add_argument('img1_uid', type=str, required=True, location='json')
    parser.add_argument('img2_uid', type=str, required=True, location='json')
    parser.add_argument('type', type=str, required=True, location='json')
    parser.add_argument('personal', type=bool, default=False, location='json')

    @api.expect(parser)
    @auth.login_required
    def post(self):
        """
        Create (if necessary) the proposal and annotate it with the given type
        If element was already annotated, raise an error.
        :return:
        """
        args = self.parser.parse_args()
        user_uid = g.user_uid
        img1_uid, img2_uid, type = args['img1_uid'], args['img2_uid'], args['type']

        user = model.User.nodes.get_or_none(uid=user_uid)
        if not user:
            raise BadRequest('User does not exist')

        img1 = model.Image.nodes.get_or_none(uid=img1_uid)
        img2 = model.Image.nodes.get_or_none(uid=img2_uid)

        if args['personal']:
            link = model.PersonalLink.create_link(img1, img2, user)
            return {'uid': link.uid}
        else:
            # Create the proposal first
            link = model.VisualLink.create_proposal(img1, img2, user, exist_ok=True)

            if link.type == model.VisualLink.Type.PROPOSAL:
                if not user.can_annotate_links():
                    raise BadRequest("Forbidden action, user account does not have the right privileges.")
                link.annotate(user, type)
                return {"uid": link.uid}
            else:
                raise BadRequest("Link already exists uid:{}, type:{}".format(link.uid, link.type))


@api.route('/api/proposal/create')
class LinkResource(Resource):
    parser = api.parser()
    parser.add_argument('img1_uid', type=str, required=True, location='json')
    parser.add_argument('img2_uid', type=str, required=True, location='json')

    @api.expect(parser)
    @auth.login_required
    def post(self):
        args = self.parser.parse_args()
        user_uid = g.user_uid
        img1_uid, img2_uid = args['img1_uid'], args['img2_uid']

        user = model.User.nodes.get_or_none(uid=user_uid)
        if not user:
            raise BadRequest('User does not exist')

        # Create the proposal first
        img1 = model.Image.nodes.get_or_none(uid=img1_uid)
        img2 = model.Image.nodes.get_or_none(uid=img2_uid)
        link = model.VisualLink.create_proposal(img1, img2, user, exist_ok=True)
        return {"uid": link.uid}


@api.route('/api/link/proposal/random')
class LinkResource(Resource):
    parser = api.parser()
    parser.add_argument('nb_proposals', type=int, default=10)

    @api.expect(parser)
    @api.marshal_with(api.models['VisualLink_ext'])
    def get(self):
        args = self.parser.parse_args()
        links = model.VisualLink.get_random_proposals(limit=args['nb_proposals'])
        return [link.to_dict(level=SerializationLevel.EXTENDED) for link in links]


@api.route('/api/link/related')
class LinkResource(Resource):
    parser = api.parser()
    parser.add_argument('image_uids', type=list, required=True, location='json')
    parser.add_argument('personal', type=bool, default=False, location='json')

    graph_link_model = api.model('GraphLinkData', {'source': fields.String,
                                                   'target': fields.String,
                                                   'data': fields.Nested(api.models['VisualLink'])})
    related_data = api.model('RelatedData',
                             {'links': fields.List(fields.Nested(graph_link_model))})

    @api.marshal_with(related_data)
    @api.expect(parser)
    @auth.login_required
    def post(self):
        args = self.parser.parse_args()
        user_uid = g.user_uid
        user = model.User.nodes.get_or_none(uid=user_uid)
        if not user:
            raise BadRequest('User does not exist')
        if not args['personal']:
            _, links = model.get_subgraph(args['image_uids'], graph_depth=0)
        else:
            _, links = model.get_subgraph_personal(args['image_uids'], user, graph_depth=0)
        return {'links': [{'source': uid1,
                           'target': uid2,
                           'data': l.to_dict()} for uid1, uid2, l in links]}


@api.route('/api/triplet/proposal/random')
class LinkResource(Resource):
    parser = api.parser()
    parser.add_argument('nb_proposals', type=int, default=10)

    @api.expect(parser)
    @api.marshal_with(api.models['TripletComparison_ext'])
    def get(self):
        args = self.parser.parse_args()
        links = model.TripletComparison.get_random_proposals(limit=args['nb_proposals'])
        return [link.to_dict(level=SerializationLevel.EXTENDED) for link in links]


@api.route('/api/triplet/<string:uid>')
class LinkResource(Resource):
    @api.marshal_with(api.models['TripletComparison_ext'])
    def get(self, uid):
        link = model.TripletComparison.nodes.get_or_none(uid=uid)  # type: model.TripletComparison
        if link is None:
            raise BadRequest("{} is not a triplet".format(uid))
        return link.to_dict(level=SerializationLevel.EXTENDED)

    # @auth.login_required
    # def delete(self, uid):
    #    link = model.TripletComparison.nodes.get_or_none(uid=uid)  # type: model.TripletComparison
    #    if link:
    #        link.delete()
    #        return {}
    #    else:
    #        raise BadRequest("{} is not a link".format(uid))

    parser = api.parser()
    parser.add_argument('positive_uid', type=str, required=True)
    parser.add_argument('negative_uid', type=str, required=True)

    @api.expect(parser)
    @auth.login_required
    def put(self, uid):
        """
        Validates a triplet
        :param uid:
        :return:
        """
        args = self.parser.parse_args()
        user_uid = g.user_uid
        if user_uid is None:
            user = model.User.nodes.get(username='Anonymous')
        else:
            user = model.User.nodes.get_or_none(uid=user_uid)

        if not user:
            raise BadRequest('User does not exist')
        link = model.TripletComparison.nodes.get_or_none(uid=uid)  # type: model.TripletComparison
        if link is None:
            raise BadRequest("{} is not a triplet".format(uid))
        positive_img = model.Image.nodes.get_or_none(uid=args['positive_uid'])
        negative_img = model.Image.nodes.get_or_none(uid=args['negative_uid'])
        if not positive_img or not negative_img:
            raise BadRequest('One of the image does not exist')
        link.annotate(user, positive_img, negative_img)


# @api.route('/api/links')
# class LinkResource(Resource):
#    @api.marshal_with(model_links)
#    def get(self):
#        return {'links': [l.to_dict(extended=True) for l in model.VisualLink.nodes.all()]}


def elastic_search_ids(query=None, all_terms=False, min_date=None, max_date=None, nb_results=200):
    base_query = {
        "bool": {
             "must": [

                #{'match': {"attribution": {"query": 'Web Gallery of Art'}}}
                ],
             #"must_not": {'match': {"title": {"query": 'detail'}}}
             #"filter": ,
             #"must_not": [{'match': {"title": {"query": 'detail'}}},
                          #{'match': {"attribution": {"query": 'Fondazione Giorgio Cini'}}}
             #             ]
         }
    }
    if query is not None and query != "":
        base_query['bool']['must'].append({
                     "match": {
                        "_all": {
                            "query": query,
                            "operator": "and" if all_terms else "or",
                            "fuzziness": "AUTO",
                        },
                     },
                 })
    if max_date is not None:
        base_query['bool']['must'].append({"range": {"date_begin": {"lte": max_date}}})
    if min_date is not None:
        base_query['bool']['must'].append({"range": {"date_end": {"gte": min_date}}})
    elastic_search_query = {
        "stored_fields": [],  # Do not return the fields, _id is enough
        "query": base_query,
        "size": nb_results
    }
    # If all of them needs to be returned, use scrolling
    if nb_results > 10000:
        elastic_search_query['size'] = 10000  # Pages of 10000 elements
        es_results = requests.get('{}/_search?scroll=1m'.format(app.config['ELASTICSEARCH_URL']),
                                  json=elastic_search_query)
        all_ids = []
        # Take pages until done
        while True:
            json_result = es_results.json()
            total_results = json_result['hits']['total']
            new_ids = [int(s['_id']) for s in json_result['hits']['hits']]
            if len(new_ids) == 0:
                return all_ids, total_results
            all_ids.extend(new_ids)
            if len(all_ids) > nb_results:
                return all_ids[:nb_results], total_results
            es_results = requests.get('{}/_search/scroll'.format(app.config['ELASTICSEARCH_URL']),
                                      json={'scroll': '1m', 'scroll_id': json_result['_scroll_id']})
    else:
        es_results = requests.get('{}/_search'.format(app.config['ELASTICSEARCH_URL']),
                                  json=elastic_search_query)
        if es_results.status_code != 200:
            raise BadRequest('ElasticSearch query failed')
        search_data = es_results.json()
        total_results = search_data['hits']['total']
        return [int(r['_id']) for r in search_data['hits']['hits']], total_results


@api.route('/api/search/text')
class SearchTextResource(Resource):
    parser = api.parser()
    parser.add_argument('query', type=str, default="")
    parser.add_argument('nb_results', type=int, default=40)
    parser.add_argument('all_terms', type=int, default=1)
    parser.add_argument('min_date', type=int)
    parser.add_argument('max_date', type=int)
    parser.add_argument('filter_duplicates', type=int, default=1)

    @api.marshal_with(model_text_search)
    @api.expect(parser)
    def get(self):
        args = self.parser.parse_args()
        nb_results = args['nb_results']
        if args['filter_duplicates']:
            args['nb_results'] = int(2.5*args['nb_results'])
        q = args['query']
        min_date = args['min_date']  # type: Optional[int]
        max_date = args['max_date']  # type: Optional[int]
        if True:
            ids, total_results = elastic_search_ids(q, args['all_terms'], min_date, max_date, args['nb_results'])
            results = model.CHO.get_by_ids(ids)
        else:
            results = model.CHO.search(q, nb_results)
        if args['filter_duplicates']:
            results = model.utils.filter_duplicates_cho(results)
        results = results[:nb_results]
        return {'query': q, 'results': [r.to_dict() for r in results], 'total': total_results}


@api.route('/api/image/search')
class SearchImageResource(Resource):
    parser = api.parser()
    parser.add_argument('positive_image_uids', type=list, default=[], location='json')
    parser.add_argument('negative_image_uids', type=list, default=[], location='json')
    parser.add_argument('positive_images_b64', type=list, default=[], location='json')
    parser.add_argument('negative_images_b64', type=list, default=[], location='json')
    parser.add_argument('nb_results', type=int, default=100)
    parser.add_argument('index', type=str, location='json')
    parser.add_argument('metadata', type=dict)
    parser.add_argument('rerank', type=bool, default=False, location='json')
    parser.add_argument('filter_duplicates', type=bool, default=True, location='json')

    @api.marshal_with(model_image_search_region)
    @api.expect(parser)
    def post(self):
        args = self.parser.parse_args()
        nb_results = args['nb_results']
        if args['filter_duplicates']:
            args['nb_results'] = int(2.5*args['nb_results'])
        if args.get('metadata'):
            metadata = args['metadata']
            if metadata.get('query', '') != '' or metadata.get('min_date') is not None or metadata.get('max_date') is not None:
                ids, _ = elastic_search_ids(metadata.get('query', ''),
                                         metadata.get('all_terms', True),
                                         metadata.get('min_date'),
                                         metadata.get('max_date'),
                                         100000)
                filtered_uids = model.CHO.get_image_uids_from_ids(ids)
                args['filtered_uids'] = filtered_uids
            del args['metadata']
        try:
            r = requests.post(app.config['REPLICA_SEARCH_URL'] + '/api/search', json=args)
        except Exception as e:
            raise BadRequest('Could not connect to search server')
        if r.status_code != 200:
            raise BadRequest('Bad answer from the search server : {}'.format(r.json().get('message')))
        result_output = []
        request_output = r.json()
        result_output_raw = request_output['results']
        # Filter duplicates
        if args['filter_duplicates']:
            image_uids = [r['uid'] for r in result_output_raw]
            image_uids = set(model.utils.filter_duplicates_image_uids(image_uids))
            result_output_raw = [r for r in result_output_raw if r['uid'] in image_uids]

        chos = model.CHO.get_from_image_uids([r['uid'] for r in result_output_raw])
        assert len(result_output_raw) == len(chos)
        for result, cho in zip(result_output_raw, chos):
            r = cho.to_dict()
            if 'box' in result.keys():
                r['images'][0]['box'] = result['box']
            result_output.append(r)
        result_output = result_output[:nb_results]
        return {'results': result_output, 'total': request_output['total']}


@api.route('/api/image/search_external')
class SearchImageExternalResource(Resource):
    parser = api.parser()
    parser.add_argument('image_b64', type=str, required=True, location='json', help="urlsafe b64 encoded version of the raw image file (JPG only)")
    parser.add_argument('nb_results', type=int, default=100)
    parser.add_argument('metadata', type=dict)
    parser.add_argument('rerank', type=bool, default=False, location='json')
    parser.add_argument('filter_duplicates', type=bool, default=True, location='json')

    @api.marshal_with(model_image_search_region)
    @api.expect(parser)
    def post(self):
        args = self.parser.parse_args()
        nb_results = args['nb_results']
        if args['filter_duplicates']:
            args['nb_results'] = int(2.5*args['nb_results'])
        if args.get('metadata'):
            metadata = args['metadata']
            ids, _ = elastic_search_ids(metadata.get('query', ''),
                                     metadata.get('all_terms', True),
                                     metadata.get('min_date'),
                                     metadata.get('max_date'),
                                     100000)
            filtered_uids = model.CHO.get_image_uids_from_ids(ids)
            del args['metadata']
            args['filtered_uids'] = filtered_uids
        try:
            r = requests.post(app.config['REPLICA_SEARCH_URL'] + '/api/search_external', json=args)
        except Exception as e:
            raise BadRequest('Could not connect to search server')
        if r.status_code != 200:
            raise BadRequest('Bad answer from the search server : {}'.format(r.json().get('message')))
        result_output = []
        request_output = r.json()
        result_output_raw = request_output['results']
        # Filter duplicates
        if args['filter_duplicates']:
            image_uids = [r['uid'] for r in result_output_raw]
            image_uids = set(model.utils.filter_duplicates_image_uids(image_uids))
            result_output_raw = [r for r in result_output_raw if r['uid'] in image_uids]

        chos = model.CHO.get_from_image_uids([r['uid'] for r in result_output_raw])
        assert len(result_output_raw) == len(chos)
        for result, cho in zip(result_output_raw, chos):
            r = cho.to_dict()
            if 'box' in result.keys():
                r['images'][0]['box'] = result['box']
            result_output.append(r)
        result_output = result_output[:nb_results]
        return {'results': result_output, 'total': request_output['total']}


@api.route('/api/transition_gif/<string:uid1>/<string:uid2>')
class TransitionGifResource(Resource):
    def get(self, uid1, uid2):
        req = requests.get(app.config['REPLICA_SEARCH_URL'] + '/api/transition_gif/{}/{}'.format(uid1, uid2),
                           stream=True)
        return Response(stream_with_context(req.iter_content(chunk_size=10000)),
                        content_type=req.headers['content-type'])


@api.route('/api/transition_gif_validity/<string:uid1>/<string:uid2>')
class TransitionGifResource(Resource):
    def get(self, uid1, uid2):
        req = requests.get(app.config['REPLICA_SEARCH_URL'] + '/api/transition_gif_validity/{}/{}'.format(uid1, uid2),
                           stream=True)
        return Response(stream_with_context(req.iter_content(chunk_size=10000)),
                        content_type=req.headers['content-type'])


@api.route('/api/image/distance_matrix')
class DistanceMatrixResource(Resource):
    parser = api.parser()
    parser.add_argument('image_uids', type=list, required=True, location='json')
    parser.add_argument('index', type=str, location='json')

    distance_matrix_model = api.model('DistanceMatrixModel', {'distances': fields.List(fields.List(fields.Float))})

    @api.marshal_with(distance_matrix_model)
    @api.expect(parser)
    def post(self):
        args = self.parser.parse_args()
        try:
            r = requests.post(app.config['REPLICA_SEARCH_URL'] + '/api/distance_matrix', json=args)
        except Exception as e:
            raise BadRequest('Could not connect to search server')
        if r.status_code != 200:
            raise BadRequest('Bad answer from the search server : {}'.format(r.json().get('message')))
        return r.json()


@api.route('/api/image/search_region')
class SearchImageRegionResource(Resource):
    parser = api.parser()
    parser.add_argument('image_uid', type=str, required=True, location='json')
    parser.add_argument('box_x', type=float, default=0.0, location='json')
    parser.add_argument('box_y', type=float, default=0.0, location='json')
    parser.add_argument('box_h', type=float, default=1.0, location='json')
    parser.add_argument('box_w', type=float, default=1.0, location='json')
    parser.add_argument('nb_results', type=int, default=100)
    parser.add_argument('index', type=str, location='json')
    parser.add_argument('metadata', type=dict)
    parser.add_argument('filter_duplicates', type=bool, default=True, location='json')

    @api.marshal_with(model_image_search_region)
    @api.expect(parser)
    def post(self):
        args = self.parser.parse_args()
        nb_results = args['nb_results']
        if args['filter_duplicates']:
            args['nb_results'] = int(2.5*args['nb_results'])
        if args.get('metadata'):
            metadata = args['metadata']
            ids, _ = elastic_search_ids(metadata.get('query', ''),
                                     metadata.get('all_terms', True),
                                     metadata.get('min_date'),
                                     metadata.get('max_date'),
                                     50000)
            filtered_uids = model.CHO.get_image_uids_from_ids(ids)
            del args['metadata']
            args['filtered_uids'] = filtered_uids
        try:
            r = requests.post(app.config['REPLICA_SEARCH_URL'] + '/api/search_region', json=args)
        except Exception as e:
            raise BadRequest('Could not connect to search server')
        if r.status_code != 200:
            raise BadRequest('Bad answer from the search server : {}'.format(r.json().get('message')))
        result_output = []
        request_output = r.json()
        result_output_raw = request_output['results']
        if args['filter_duplicates']:
            image_uids = [r['uid'] for r in result_output_raw]
            image_uids = set(model.utils.filter_duplicates_image_uids(image_uids))
            result_output_raw = [r for r in result_output_raw if r['uid'] in image_uids]

        chos = model.CHO.get_from_image_uids([r['uid'] for r in result_output_raw])
        for result, cho in zip(result_output_raw, chos):
            r = cho.to_dict()
            r['images'][0]['box'] = result['box']
            result_output.append(r)
        result_output = result_output[:nb_results]
        return {'results': result_output, 'total': request_output['total']}


@api.route('/api/auth')
class AuthenticationResource(Resource):
    parser = api.parser()
    parser.add_argument('username', type=str, required=True)
    parser.add_argument('password_sha256', type=str, required=True)

    @api.marshal_with(model_auth)
    @api.expect(parser)
    def post(self):
        args = self.parser.parse_args()
        username, password_sha256 = args['username'], args['password_sha256']
        user = model.User.nodes.get_or_none(username=username)
        if user is None:
            raise BadRequest("Unknwon username : {}".format(username))
        if password_sha256 != user.password_sha256:
            raise BadRequest("Invalid password")
        return {'token': auth.create_token(user.uid, user.username, user.authorization_level)}


@api.route('/api/user/current')
class CurrentUserResource(Resource):
    @api.marshal_with(api.models['User'])
    @auth.login_required
    def get(self):
        current_user = model.User.nodes.get(uid=g.user_uid)
        return current_user.to_dict()


@api.route('/api/user/groups')
class CurrentUserGroupsRessource(Resource):
    @api.marshal_with(api.models['Groups'])
    @auth.login_required
    def get(self):
        current_user = model.User.nodes.get(uid=g.user_uid)

        return {'groups': [group.to_dict() for group in current_user.groups]}


@api.route('/api/graph')
class GraphResource(Resource):
    parser = api.parser()
    parser.add_argument('image_uids', type=list, required=True, location='json')

    graph_link_model = api.model('GraphLinkData', {'source': fields.String,
                                                   'target': fields.String,
                                                   'data': fields.Nested(api.models['VisualLink'])})
    graph_model = api.model('GraphData',
                            {'nodes': fields.List(fields.Nested(api.models['Image'])),
                             'links': fields.List(fields.Nested(graph_link_model)),
                             'distances': fields.List(fields.List(fields.Float))})

    @api.marshal_with(graph_model)
    def post(self):
        args = self.parser.parse_args()
        print(args['image_uids'])
        nodes, links = model.get_subgraph(args['image_uids'])
        try:
            r = requests.post(app.config['REPLICA_SEARCH_URL'] + '/api/distance_matrix',
                              json={'image_uids': [img.uid for img in nodes]})
        except Exception as e:
            raise BadRequest('Could not connect to search server')
        if r.status_code != 200:
            raise BadRequest('Bad answer from the search server : {}'.format(r.json().get('message')))
        return {
            'nodes': [img.to_dict() for img in nodes],
            'links': [{'source': uid1,
                       'target': uid2,
                       'data': l.to_dict()} for uid1, uid2, l in links],
            'distances': r.json()['distances']
        }


_log_lock = Lock()
@api.route('/api/log')
class GraphResource(Resource):
    parser = api.parser()
    parser.add_argument('data', type=dict, required=True, location='json')

    @api.expect(parser)
    @auth.login_required
    def post(self):
        current_user = model.User.nodes.get(uid=g.user_uid)
        data = self.parser.parse_args()['data']
        data['user_uid'] = current_user.username
        with _log_lock:
            with open(app.config['LOG_FILE'], 'a') as f:
                f.write(json.dumps(data))
                f.write('\n')


if __name__ == '__main__':
    monitor(app, port=5010)
    app.run(host='0.0.0.0', debug=True, port=5000, threaded=True)
