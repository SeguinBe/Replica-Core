import neomodel
from flask import Flask, request, g
from flask_restplus import Api, Resource, fields
from flask_prometheus import monitor
from werkzeug.exceptions import BadRequest
import requests
from collections import namedtuple
from functools import partial
import json

from replica_core import model, auth

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

model.Image.add_schema(api)
model.Collection.add_schema(api)
model.CHO.add_schema(api)
model.Group.add_schema(api)
model.VisualLink.add_schema(api)
model.TripletComparison.add_schema(api)
api.clone('Link_from_source', api.models['VisualLink'], {'image': fields.Nested(api.models['Image'])})
model.User.add_schema(api)

model.Image.add_schema(api, extended=True)
model.Collection.add_schema(api, extended=True)
model.CHO.add_schema(api, extended=True)
model.VisualLink.add_schema(api, extended=True)
model.TripletComparison.add_schema(api, extended=True)

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
model_links = api.model('Links',
                        {'links': fields.List(fields.Nested(api.models['VisualLink_ext']), required=True)})
model_text_search = api.model('TextSearch',
                              {'query': fields.String, 'results': fields.List(fields.Nested(api.models['CHO']))})
model_image_search = api.model('ImageSearch',
                               {'results': fields.List(fields.Nested(api.models['CHO']))})
model_image_search_region = api.model('ImageSearchRegion',
                                      {'results': fields.List(fields.Nested(model_cho_box))})

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
        return coll.to_dict(extended=True)


@api.route('/api/element/<string:uid>')
class ElementResource(Resource):
    @api.marshal_with(api.models['CHO_ext'])
    def get(self, uid):
        cho = model.CHO.nodes.get_or_none(uid=uid)  # type: model.CHO
        if cho is None:
            raise BadRequest("{} is not an element".format(uid))
        return cho.to_dict(extended=True)


@api.route('/api/element/random')
class LinkResource(Resource):
    parser = api.parser()
    parser.add_argument('nb_elements', type=int, default=1)

    @api.expect(parser)
    @api.marshal_with(api.models['CHO_ext'])
    def get(self):
        args = self.parser.parse_args()
        chos = model.CHO.get_random(limit=args['nb_elements'])
        return [cho.to_dict(extended=True) for cho in chos]


@api.route('/api/image/<string:uid>')
class ImageResource(Resource):
    @api.marshal_with(api.models['Image_ext'])
    def get(self, uid):
        img = model.Image.nodes.get_or_none(uid=uid)  # type: model.Image
        if img is None:
            raise BadRequest("{} is not an image".format(uid))
        return img.to_dict(extended=True)


@api.route('/api/link/<string:uid>')
class LinkResource(Resource):
    @api.marshal_with(api.models['VisualLink'])
    def get(self, uid):
        link = model.VisualLink.nodes.get_or_none(uid=uid)  # type: model.VisualLink
        if link is None:
            raise BadRequest("{} is not a link".format(uid))
        return link.to_dict(extended=True)

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

        # Create the proposal first
        img1 = model.Image.nodes.get_or_none(uid=img1_uid)
        img2 = model.Image.nodes.get_or_none(uid=img2_uid)
        link = model.VisualLink.create_proposal(img1, img2, user, exist_ok=True)

        if link.type == model.VisualLink.Type.PROPOSAL:
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
        return [link.to_dict(extended=True) for link in links]


@api.route('/api/link/related')
class LinkResource(Resource):
    parser = api.parser()
    parser.add_argument('image_uids', type=list, required=True, location='json')

    graph_link_model = api.model('GraphLinkData', {'source': fields.String,
                                                   'target': fields.String,
                                                   'data': fields.Nested(api.models['VisualLink'])})
    related_data = api.model('RelatedData',
                             {'links': fields.List(fields.Nested(graph_link_model))})

    @api.marshal_with(related_data)
    @api.expect(parser)
    def post(self):
        args = self.parser.parse_args()
        _, links = model.get_subgraph(args['image_uids'], graph_depth=0)
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
        return [link.to_dict(extended=True) for link in links]


@api.route('/api/triplet/<string:uid>')
class LinkResource(Resource):
    @api.marshal_with(api.models['TripletComparison_ext'])
    def get(self, uid):
        link = model.TripletComparison.nodes.get_or_none(uid=uid)  # type: model.TripletComparison
        if link is None:
            raise BadRequest("{} is not a triplet".format(uid))
        return link.to_dict(extended=True)

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


@api.route('/api/search/text')
class SearchTextResource(Resource):
    parser = api.parser()
    parser.add_argument('query', type=str, required=True)
    parser.add_argument('nb_results', type=int, default=40)

    @api.marshal_with(model_text_search)
    @api.expect(parser)
    def get(self):
        args = self.parser.parse_args()
        q = args['query']
        nb_results = args['nb_results']
        if True:
            es_results = requests.get('{}/_search'.format(app.config['ELASTICSEARCH_URL']),
                                      json={
                                          "query": {
                                              # "multi_match": {
                                              #     "query": q,
                                              #     #"type": "most_fields",
                                              #     "fuzziness": "AUTO",  # 1
                                              #     "fields": [
                                              #         "author",
                                              #         "title"
                                              #     ],
                                              #     "operator":   "and"
                                              # }
                                              "match": {
                                                  "_all": {
                                                      "query": q,
                                                      "operator": "and",
                                                      #"fuzziness": "AUTO",
                                                  }
                                              }
                                          },
                                          "size": nb_results
                                      })
            if es_results.status_code != 200:
                raise BadRequest('ElasticSearch query failed')
            ids = [int(r['_id']) for r in es_results.json()['hits']['hits']]
            # results = [model.CHO.get_by_id(_id) for _id in ids]
            results = model.CHO.get_by_ids(ids)
        else:
            results = model.CHO.search(q, nb_results)
        return {'query': q, 'results': [r.to_dict() for r in results]}


@api.route('/api/image/search')
class SearchImageResource(Resource):
    parser = api.parser()
    parser.add_argument('positive_image_uids', type=list, required=True, location='json')
    parser.add_argument('negative_image_uids', type=list, default=[], location='json')
    parser.add_argument('nb_results', type=int, default=100)
    parser.add_argument('index', type=str, location='json')

    @api.marshal_with(model_image_search)
    @api.expect(parser)
    def post(self):
        args = self.parser.parse_args()
        try:
            r = requests.post(app.config['REPLICA_SEARCH_URL'] + '/api/search', json=args)
        except Exception as e:
            raise BadRequest('Could not connect to search server')
        if r.status_code != 200:
            raise BadRequest('Bad answer from the search server : {}'.format(r.json().get('message')))
        result_output = []
        for result in r.json()['results']:
            result_output.append(model.CHO.get_from_image_uid(result['uid']).to_dict())
        return {'results': result_output}


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
class SearchImageResource(Resource):
    parser = api.parser()
    parser.add_argument('image_uid', type=str, required=True, location='json')
    parser.add_argument('box_x', type=float, default=0.0, location='json')
    parser.add_argument('box_y', type=float, default=0.0, location='json')
    parser.add_argument('box_h', type=float, default=1.0, location='json')
    parser.add_argument('box_w', type=float, default=1.0, location='json')
    parser.add_argument('nb_results', type=int, default=100)
    parser.add_argument('index', type=str, location='json')

    @api.marshal_with(model_image_search_region)
    @api.expect(parser)
    def post(self):
        args = self.parser.parse_args()
        try:
            r = requests.post(app.config['REPLICA_SEARCH_URL'] + '/api/search_region', json=args)
        except Exception as e:
            raise BadRequest('Could not connect to search server')
        if r.status_code != 200:
            raise BadRequest('Bad answer from the search server : {}'.format(r.json().get('message')))
        result_output = []
        for result in r.json()['results']:
            r = model.CHO.get_from_image_uid(result['uid']).to_dict()
            r['images'][0]['box'] = result['box']
            result_output.append(r)
        return {'results': result_output}


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
        return {'token': auth.create_token(user.uid)}


@api.route('/api/user/current')
class CurrentUserResource(Resource):
    @api.marshal_with(api.models['User'])
    @auth.login_required
    def get(self):
        current_user = model.User.nodes.get(uid=g.user_uid)
        return current_user.to_dict()


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
        with open(app.config['LOG_FILE'], 'a') as f:
            f.write(json.dumps(data))
            f.write('\n')


if __name__ == '__main__':
    monitor(app, port=5010)
    app.run(host='0.0.0.0', debug=True, port=5000, threaded=True)
