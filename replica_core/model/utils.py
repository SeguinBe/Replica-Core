import neomodel
from neomodel import StructuredNode, StructuredRel, db
from typing import List, Union, Tuple, Optional
from .iiif import Image
from .link import VisualLink, PersonalLink, CHO
from .user import User
import networkx as nx
from collections import defaultdict


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

    if len(results) > 0:
        nodes_data, links_data = results[0]
    else:
        nodes_data, links_data = [], []
    nodes, links = [Image.inflate(d) for d in nodes_data], [(uid1, uid2, VisualLink.inflate(d)) for uid1, uid2, d in links_data]

    missing_image_uids = set(image_uids).difference([img.uid for img in nodes])
    nodes += Image.get_by_uids(missing_image_uids)

    return nodes, links


def get_subgraph_personal(image_uids: List[str], user: User, graph_depth=3) -> (List[Image], List[Tuple[str, str, VisualLink]]):
    results, _ = db.cypher_query("""
                                    MATCH (n:Image) where n.uid IN {image_uids}
                                    WITH DISTINCT(n) as n_previous
                                    """ +
                                 """MATCH (n_previous:Image)<-[]-(v:PersonalLink)-[]->(n:Image), (user:User)<-[CREATED_BY]-(v) where user.uid={user_uid}
                                    WITH DISTINCT(n) as n_previous
                                    """ * graph_depth +
                                 """WITH COLLECT(n_previous) as nodes
                                    MATCH (n1:Image)<-[]-(v:PersonalLink)-[]->(n2:Image), (user:User)<-[CREATED_BY]-(v)
                                    where n1 in nodes and n2 in nodes and id(n1)<id(n2) and user.uid={user_uid}
                                    return nodes, collect([n1.uid, n2.uid, v]) as links
                                    """,
                                 dict(image_uids=image_uids, user_uid=user.uid))

    if len(results) > 0:
        nodes_data, links_data = results[0]
    else:
        nodes_data, links_data = [], []
    nodes, links = [Image.inflate(d) for d in nodes_data], [(uid1, uid2, PersonalLink.inflate(d)) for uid1, uid2, d in links_data]

    missing_image_uids = set(image_uids).difference([img.uid for img in nodes])
    nodes += [Image.nodes.get(uid=uid) for uid in missing_image_uids]

    return nodes, links


def _filter_duplicates(candidates, edges) -> List:
    g = nx.Graph(edges)
    to_ignore = defaultdict(list)
    for comp in nx.connected_components(g):
        for n in comp:
            to_ignore[n] = comp

    ignored = set()
    result = []
    for uid in candidates:
        if uid not in ignored:
            ignored.update(to_ignore[uid])
            result.append(uid)

    return result


DEFAULT_SPATIAL_SPREAD_FILTERING = None


def filter_duplicates_cho_uids(cho_uids: List[str]) -> List[str]:
    results, _ = db.cypher_query("""
                                    MATCH (c1:CHO)-[]->(n1:Image)<-[]-(v:VisualLink)-[]->(n2:Image)<-[]-(c2:CHO)
                                    where c1.uid IN {cho_uids} and c2.uid IN {cho_uids} and id(c1) < id(c2)
                                    and v.type = 'DUPLICATE'
                                    return c1.uid, c2.uid
                                    """,
                                 dict(cho_uids=cho_uids))
    return _filter_duplicates(cho_uids, results)


def filter_duplicates_image_uids(image_uids: List[str]) -> List[str]:
    results, _ = db.cypher_query("""
                                    MATCH (n1:Image)<-[]-(v:VisualLink)-[]->(n2:Image)
                                    where n1.uid IN {image_uids} and n2.uid IN {image_uids} and id(n1) < id(n2)
                                    and v.type = 'DUPLICATE'
                                    return n1.uid, n2.uid
                                    """,
                                 dict(image_uids=image_uids))
    return _filter_duplicates(image_uids, results)


def filter_duplicates_cho_ids(cho_ids: List[str]) -> List[str]:
    results, _ = db.cypher_query("""
                                    MATCH (c1:CHO)-[]->(n1:Image)<-[]-(v:VisualLink)-[]->(n2:Image)<-[]-(c2:CHO)
                                    where id(c1) IN {cho_ids} and id(c2) IN {cho_ids} and id(c1) < id(c2)
                                    and v.type = 'DUPLICATE'
                                    return id(c1), id(c2)
                                    """,
                                 dict(cho_ids=cho_ids))
    return _filter_duplicates(cho_ids, results)


def filter_duplicates_cho(chos: List[CHO]) -> List[CHO]:
    cho_ids = filter_duplicates_cho_ids([cho.id for cho in chos])
    d = {cho.id: cho for cho in chos}
    return [d[_id] for _id in cho_ids]
