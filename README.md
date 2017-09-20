# Replica Core

This is the core sub-system of the Replica project. It takes care of IIIF parsing,
the internal data representation, the textual queries, authentication etc....

Also this repository holds a webapp frontend calling the REST API backend.

_The image searching capabilities are not part of this repository._
The image similarity system is a separate server.


## Instalation


### Neo4j Installation and Configuration

- Download the 3.1.x package (to be compatible with the elastic-search extension)
- in neo4j.conf allow external connections
- Go to `<neo4j-server>:7474` to set username and password


- Add the schemas constraints from the ORM :
   `neomodel_install_labels app.py replica_core --db bolt://<neo4j-username>:<neo4j-password>@<neo4j-server>:7687`
- Add the elastic-search linking (https://github.com/neo4j-contrib/neo4j-elasticsearch) download the matching (3.1.x) release and unzip it in plugins
- Add to `neo4j.conf` : 
```
elasticsearch.host_name=http://<elasticsearch-address>:9200
elasticsearch.index_spec=cho:CHO(author,title,date)
```

### Elasticsearch Installation

- download it
- unzip it
- start it


### Modify configuration file

Make a `config.py` based on `config_example.py` at the root of the repository.


## Import IIIF

Populating the database from a IIIF Collection entry point is possible.
The extraction process convert every manifest to a single object in the database.
Additionally, all the ressource images of the manifest are added to the object, though in practice
many uses of the system just rely on the first image of the manifest which is usually a full frame color picture of the work of art.

The import script takes two additional parameters in order to specify which IIIF metadata field represents the Author and the Title for better displaying.

`python import_iiif.py -m <Data-Provider>/collection/top.json -a AUTHOR -t TITLE`


## Saving database

```
bin/neo4j stop
bin/neo4j-admin dump --to=/mnt/cluster-nas/benoit/neo4j_backups/2017_07_19.dump
bin/neo4j start
```
