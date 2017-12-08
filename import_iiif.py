import requests
import tqdm
from replica_core.model import CHO, Image, Collection
import argparse

import core_server

pbar = tqdm.tqdm(desc='#Images added')
pbar_failed = tqdm.tqdm(desc='#Resource failed')

METADATA_AUTHOR_FIELD = None
METADATA_TITLE_FIELD = None


def get_id(data, required=False):
    if isinstance(data, dict):
        return data['@id']
    elif required:
        assert data is not None
        return data
    else:
        return data


def to_list(data):
    if data is None:
        return []
    if isinstance(data, list):
        return data
    else:
        return [data]


def get_one(data):
    if data is None:
        return None
    return to_list(data)[0]


def download_json(uri, verbose=False):
    if verbose:
        print('Downloading : {}'.format(uri))
    r = requests.get(uri)
    return r.json()


def create_coll(data, overwrite_ok=True):
    uri = get_id(data, required=True)
    if isinstance(data, str) or ('collections' not in data.keys() and 'manifests' not in data.keys()):
        data = download_json(uri, verbose=True)
    assert data['@type'] == 'sc:Collection', uri
    assert 'collections' in data.keys() or 'manifests' in data.keys()
    # assert not ('collections' in data.keys() and 'manifests' in data.keys())

    coll = Collection.nodes.get_or_none(uri=uri)
    if coll is not None and not overwrite_ok:
        raise Exception()
    if coll is None:
        coll = Collection()
    coll.uri = get_id(data, required=True)
    coll.label = data.get('label', '')
    coll.raw_metadata = data.get('metadata', {})
    coll.description = data.get('description', '')
    coll.thumbnail = get_id(data.get('thumbnail'))
    coll.save()

    for new_coll_data in data.get('collections', []):
        new_coll = create_coll(new_coll_data, overwrite_ok)
        coll.children_collections.connect(new_coll)

    for new_manifest_data in data.get('manifests', []):
        cho = create_cho(new_manifest_data, overwrite_ok)
        coll.elements.connect(cho)

    return coll


def create_cho(data, overwrite_ok=True):
    uri = get_id(data, required=True)
    if isinstance(data, str) or 'sequences' not in data.keys():
        data = download_json(uri, verbose=False)
    assert data['@type'] == 'sc:Manifest'
    assert 'sequences' in data.keys()

    # Parse Manifest base
    cho = CHO.nodes.get_or_none(uri=uri)
    if cho is not None and not overwrite_ok:
        raise Exception()
    if cho is None:
        cho = CHO()
    cho.uri = uri
    cho.label = data.get('label', '')
    cho.description = data.get('description', '')
    cho.attribution = data.get('attribution')
    cho.license = data.get('license')
    cho.raw_metadata = data.get('metadata', {})
    cho.logo = get_id(data.get('logo'))
    cho.thumbnail = get_id(data.get('thumbnail'))
    cho.related = get_id(data.get('related'))

    # Parse Metadata
    metadata = {d['label']: d['value'] for d in cho.raw_metadata}
    def _parse_element(e):
        if isinstance(e, list):
            return e[0]
        if isinstance(e, str):
            return e
    if METADATA_TITLE_FIELD in metadata.keys():
        cho.title = _parse_element(metadata[METADATA_TITLE_FIELD])
    else:
        cho.title = None
    if METADATA_AUTHOR_FIELD in metadata.keys():
        cho.author = _parse_element(metadata[METADATA_AUTHOR_FIELD])
    else:
        cho.author = None
    begin_range_date, end_range_date = cho.get_date_range_from_fields(['date', 'daterange', 'timeline', 'timeframe'])
    cho.date_begin = begin_range_date
    cho.date_end = end_range_date
    cho.save()

    # Gather all the image ressources
    painting_annotations = [img for seq in data['sequences'] for can in seq['canvases'] for img in can['images']
                            if img['@type'] == 'oa:Annotation' and img['motivation'] == 'sc:painting']
    resources = [anno['resource'] for anno in painting_annotations if 'resource' in anno.keys()]

    for res in resources:
        try:
            img = create_image(res)
            cho.images.connect(img)
        except Exception as e:
            pbar_failed.update(1)

    return cho


def create_image(resource, overwrite_ok=True):
    _standard_str = 'http://iiif.io/api/image/2/'
    _standard_str_old = 'http://library.stanford.edu/iiif/image-api/'

    assert resource['@type'] == 'dctypes:Image', resource['@type']
    assert 'service' in resource.keys()
    assert resource['service'].get('dcterms:conformsTo', '').startswith(_standard_str_old) or \
           resource['service'].get('profile', '').startswith(_standard_str_old) or \
           resource['service'].get('dcterms:conformsTo', '').startswith(_standard_str) or \
           resource['service'].get('profile', '').startswith(_standard_str)
    iiif_url = resource['service']['@id']
    img = Image.nodes.get_or_none(iiif_url=iiif_url)
    if img is not None and not overwrite_ok:
        raise Exception()
    if img is None:
        img = Image()
    img.iiif_url = iiif_url
    img.height = resource.get('height')
    img.width = resource.get('width')
    img.save()
    pbar.update(1)
    return img


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", "--top-manifest", required=True, help="Top collection manifest to be imported")
    ap.add_argument("-a", "--author-field", required=True, help="Author field in the metadata")
    ap.add_argument("-t", "--title-field", required=True, help="Title field in the metadata")
    args = vars(ap.parse_args())

    METADATA_AUTHOR_FIELD = args['author_field']
    METADATA_TITLE_FIELD = args['title_field']

    create_coll(args['top_manifest'])

