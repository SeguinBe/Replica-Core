from tqdm import tqdm
import requests
from concurrent.futures import ThreadPoolExecutor
import core_server
from replica_core import model

pbar = tqdm(total=len(model.CHO.nodes))


def process_one(cho):
    img = cho.get_first_image()
    pbar.update(1)
    r = requests.post('{}/api/element/{}'.format(core_server.app.config['REPLICA_SEARCH_URL'], img.uid),
                 params={'iiif_resource_url': img.iiif_url})
    if r.status_code != 200:
        print(img.iiif_url)


with ThreadPoolExecutor(1) as e:
    e.map(process_one, model.CHO.nodes)