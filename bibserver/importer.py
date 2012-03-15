# the data import manager
# gets an uploaded file or retrieves a file from a URL
# indexes the records found in the file by upserting via the DAO
import urllib2
import re
from cStringIO import StringIO
import unicodedata
import uuid
import json

import bibserver.dao
import bibserver.util as util
from bibserver.config import config

class Importer(object):
    def __init__(self, owner, requesturl=False):
        self.owner = owner
        self.requesturl = requesturl

    def upload(self, fileobj, collection=None):
        '''Import a bibjson collection into the database.
       
        :param fileobj: a fileobj pointing to file from which to import
        collection records (and possibly collection metadata)
        :param collection: collection dict for use when creating collection. If
        undefined collection must be extractable from the fileobj.

        :return: same as `index` method.
        '''
        jsonin = json.load(fileobj)
        metadata = jsonin.get('metadata',False)
        record_dicts = jsonin.get('records', jsonin)

        # if metadata provided from file, roll it into the collection object
        if metadata:
            metadata.update(collection)
            collection = metadata
        
        return self.index(collection, record_dicts)

    def bulk_upload(self, colls_list):
        '''upload a list of collections from provided file locations.

        :param colls_list: a list of dictionaries with 3 keys::

            {
                # source = url source for data
                # upfile = local file path for data
                # data = raw data
                source | upfile | data: ...,
                format: {the-format-of-the-data-e.g.-bibtex},
                collection: {label for the collection}
            }
        '''
        for coll in colls_list["collections"]:
            if "upfile" in coll:
                fileobj = coll["upfile"]
            elif "data" in coll:
                fileobj = StringIO(coll['data'])
            elif "source" in coll:
                fileobj = urllib2.urlopen(coll["source"])
            format_ = coll['format']
            collection_dict = {
                'label': coll['collection']
                }
            self.upload(fileobj, format_, collection_dict)
        return True
    
    def index(self, collection_dict, record_dicts):
        '''Add this collection and its records to the database index.
        :return: (collection, records) tuple of collection and associated
        record objects.
        '''
        col_label_slug = util.slugify(collection_dict['label'])
        collection = bibserver.dao.Collection.get_by_owner_coll(self.owner.id, col_label_slug)
        if not collection:
            collection = bibserver.dao.Collection(**collection_dict)
            assert 'label' in collection, 'Collection must have a label'
            if not 'collection' in collection:
                collection['collection'] = col_label_slug
            collection['owner'] = self.owner.id

        collection.save()

        for rec in record_dicts:
            if not type(rec) is dict: continue
            rec['owner'] = collection['owner']
            if 'collection' in rec:
                if collection['collection'] != rec['collection']:
                    rec['collection'] = collection['collection']
            else:
                rec['collection'] = collection['collection']
            if not self.requesturl and 'SITE_URL' in config:
                self.requesturl = str(config['SITE_URL'])
            if self.requesturl:
                if not self.requesturl.endswith('/'):
                    self.requesturl += '/'
                if 'id' not in rec:
                    rec['id'] = bibserver.dao.make_id(rec)
                rec['url'] = self.requesturl + collection['owner'] + '/' + collection['collection'] + '/'
                if 'cid' in rec:
                    rec['url'] += rec['cid']
                elif 'id' in rec:
                    rec['url'] += rec['id']
        records = bibserver.dao.Record.bulk_upsert(record_dicts)
        return collection, records

def findformat(filename):
    if filename.endswith(".json"): return "json"
    if filename.endswith(".bibtex"): return "bibtex"
    if filename.endswith(".bib"): return "bibtex"
    if filename.endswith(".csv"): return "csv"
    return "bibtex"

