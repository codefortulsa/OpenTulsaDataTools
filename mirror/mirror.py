#!/usr/bin/env python


from urllib2 import urlopen
import errno
import json
import logging
import os
import os.path
from subprocess import call

import tqdm


logger = logging.getLogger(__name__)

def file_iterator(f, block_size):
    while True:
        buffer = f.read(block_size)
        if not buffer:
            break
        else:
            yield buffer


def get_file(url, filename, verbose=False, use_cache=True):
    # Ensure directory exists
    path = os.path.join(*filename.split('/'))
    folder = os.path.dirname(path)
    if folder:
        try:
            os.makedirs(folder)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(folder):
                pass
            else:
                raise

    if not (use_cache and os.path.exists(path)):
        u = urlopen(url)
        if verbose:
            print "  Downloading from {} to {}".format(url, path)
        with open(path, 'wb') as f:
            meta = u.info()
            file_size = int(meta.getheaders("Content-Length")[0])
            block_size = 8192
            expected = file_size / block_size
            for block in tqdm.tqdm(file_iterator(u, 8192), total=expected):
                f.write(block)
    return path


def gather_datasets(verbose=False, use_cache=True):
    datasets_path = get_file(
        'https://www.cityoftulsa.org/cot/opendata/opendatasets.jsn',
        'City of Tulsa Open Datasets/Updated Each Minute.json',
        verbose, use_cache)
    datasets_json = file(datasets_path, 'rb')
    datasets = json.load(datasets_json)

    esri_query = (
        '/query?'
        'geometryType=esriGeometryEnvelope'
        '&spatialRel=esriSpatialRelIntersects'
        '&where=1%3D1'
        '&returnGeometry=true'
        '&outFields=*'
        '&f={}')


    for dataset in datasets['OpenData']['DataSets']['DataSet']:
        name = dataset['Name']
        if verbose:
            print name, "datasets"
        if isinstance(dataset['Instances']['Instance'], list):
            instances = dataset['Instances']['Instance']
        else:
            instances = [dataset['Instances']['Instance']]

        for count, instance in enumerate(instances):
            assert isinstance(instance, dict)
            url = instance['Link']
            dtype = instance['Type']
            frequency = instance['Frequency']
            if verbose:
                print "  Dataset {}: {} (type {} at {})".format(count, frequency, dtype, url)

            if dtype in ('PDF', 'JSON', 'RSS', 'XML', 'HTML'):
                filename = "{}/{}.{}".format(name, frequency, dtype.lower())
                get_file(url, filename, verbose, use_cache)
            elif dtype == 'REST':
                assert 'ArcGIS' in url
                # Get JSON
                filename = "{}/{}.{}".format(name, frequency, 'arcgis.json')
                query_url = url + esri_query.format('pjson')
                path = get_file(query_url, filename, verbose, use_cache)

                # Convert to GeoJSON
                geojson_name = "{}/{}.{}".format(name, frequency, 'geo.json')
                call(["ogr2ogr", "-f", "GeoJSON", geojson_name, filename, "OgrGeoJSON"])

            elif dtype == 'KML':
                assert 'ArcGIS' in url
                assert url.endswith('MapServer/KmlServer')
                continue  # KMZ is currently erroring out
                # Get KMZ
                filename = "{}/{}.{}".format(name, frequency, 'kmz')
                better_url = url.replace('KmlServer', '0')
                query_url = better_url + esri_query.format('kmz')
                get_file(query_url, filename, verbose, use_cache)
            else:
                logger.warn('Not handling type {}'.format(dtype))


if __name__ == '__main__':
    import argparse

    logging.basicConfig()
    parser = argparse.ArgumentParser(description='Mirror Open Tulsa Data')
    parser.add_argument(
        '-q', '--quiet', action='store_true', help="Don't print progress messages")
    parser.add_argument(
        '-f', '--fresh', action='store_true', help='Download fresh data')
    args = parser.parse_args()

    gather_datasets(verbose = not args.quiet, use_cache=not args.fresh)
