import neomodel
from neomodel import StructuredNode, StructuredRel, db
from typing import List, Union, Tuple, Optional
from .iiif import Image
from .link import VisualLink, PersonalLink
from .user import User


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
    nodes += [Image.nodes.get(uid=uid) for uid in missing_image_uids]

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
