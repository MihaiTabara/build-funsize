"""
funsize.frontend.api
~~~~~~~~~~~~~~~~~~

This module contains all the Flask related code for routing and handling the
API call parameters

"""

import argparse
import ConfigParser
import flask
import logging
import os
import sys
try:
    import simplejson
except ImportError:
    import json

import funsize.cache.cache as cache
import funsize.backend.tasks as tasks
import funsize.utils.oddity as oddity

CACHE_URI = None

__here__ = os.path.dirname(os.path.abspath(__file__))

app = flask.Flask(__name__)


def _get_identifier(id_sha1, id_sha2):
    """ Function to generate the identifier of a patch based on two shas given
        The reason we keep this function is that in the future we might change
        the '-' to something more sophisticated.
    """
    return '-'.join([id_sha1, id_sha2])


@app.route('/')
def index():
    """ Mockup message to fill in the index page """
    return "Welcome to Funsize, the Partial MAR on demand Web-Service."\
           "Please see https://wiki.mozilla.org/User:Ffledgling/Senbonzakura"


@app.route('/cache', methods=['POST'])
def save_patch():
    """ Function to cache a patch in funsize """
    logging.debug('Parameters passed in : %s', flask.request.form)
    logging.debug('Files passed in : %s', flask.request.files.lists())

    required_params = ('sha_from', 'sha_to')
    if not all(param in flask.request.form.keys() for param in required_params):
        logging.info('Parameters could not be validated')
        flask.abort(400)

    files = flask.request.files
    if 'patch_file' not in files.keys():
        logging.info('Parameters passed could not be found on disk')
        flask.abort(400)
    storage = files.get('patch_file')

    form = flask.request.form
    sha_from, sha_to = form['sha_from'], form['sha_to']
    identifier = _get_identifier(sha_from, sha_to)

    logging.info('Saving patch file to cache with key %s', identifier)
    cacheo = cache.Cache()
    cacheo.save(storage.read(), identifier, 'patch')

    url = flask.url_for('get_patch', sha_from=sha_from, sha_to=sha_to)
    return flask.Response(json.dumps({
        "result": url,
        }),
        status=200,
        mimetype='application/json'
    )


@app.route('/cache', methods=['GET'])
def get_patch():
    """ Function to return a patch from cache """
    logging.debug('Request received with args : %s', flask.request.args)

    required_params = ('sha_from', 'sha_to')
    if not all(param in flask.request.args.keys() for param in required_params):
        logging.info('Arguments could not be validated')
        flask.abort(400)

    identifier = _get_identifier(flask.request.args['sha_from'],
                                 flask.request.args['sha_to'])

    logging.debug('Looking up record with identifier %s', identifier)
    cacheo = cache.Cache()
    if not cacheo.find(identifier, 'patch'):
        logging.info('Invalid partial request')
        resp = flask.Response(json.dumps({
            "result": "Patch with identifier %s not found" % identifier,
            }),
            status=400,
        )
        return resp

    logging.info('Patch found, retrieving ...')
    return flask.Response(cacheo.retrieve(identifier, 'patch'),
                          status=200,
                          mimetype='application/octet-stream')


@app.route('/partial', methods=['POST'])
def trigger_partial(version='latest'):
    """
    Function to trigger a  partial generation
    Needs params: mar_from, mar_to, mar_from_hash, mar_to_hash
    """
    api_result = {
        'result': 'Version %s of API ' % version
    }
    if version in app.config['unsupported_versions']:
        api_result['result'] += ' no longer supported'
        return flask.Response(str(api_result), status=410)
    if version not in app.config['supported_versions']:
        api_result['result'] += ' does not exist'
        return flask.Response(str(api_result), status=400)

    logging.debug('Parameters passed in : %s', flask.request.form)
    required_params = ('mar_from', 'mar_to', 'mar_from_hash',
                       'mar_to_hash', 'channel_id', 'product_version')
    form = flask.request.form
    if not all(param in form.keys() for param in required_params):
        logging.info('Parameters could not be validated')
        flask.abort(400)

    mar_from, mar_to = form['mar_from'], form['mar_to']
    mar_from_hash, mar_to_hash = form['mar_from_hash'], form['mar_to_hash']
    channel_id, product_version = form['channel_id'], form['product_version']

    identifier = _get_identifier(mar_from_hash, mar_to_hash)
    url = flask.url_for('get_partial', identifier=identifier)

    cacheo = cache.Cache()
    if cacheo.find(identifier, 'partial'):
        logging.info('Partial has already been triggered')
        resp = flask.Response(json.dumps({
            "result": url
            }),
            status=201,
            mimetype='application/json'
        )
        return resp

    try:
        cacheo.save_blank_file(identifier, 'partial')
    except oddity.CacheError:
        logging.error('Error while processing trigger request for URL: %s\n',
                      url)
        resp = flask.Response(json.dumps({
            "result": "Error while processing request %s" % url,
            }),
            status=500,
            mimetypge='application/json'
        )
        return resp

    logging.info('Calling generation functions')

    # TODO - here we should get try-except thing to retry + ack late
    # catch LCA exception
    tasks.build_partial_mar.delay(mar_to, mar_to_hash, mar_from,
                                  mar_from_hash, identifier,
                                  channel_id, product_version)

    logging.critical('Called build and moved on')
    resp = flask.Response(json.dumps({
        "result": url,
        }),
        status=202,
        mimetype='application/json'
    )
    return resp


@app.route('/partial/<identifier>', methods=['GET'])
def get_partial(identifier, version='latest'):
    """ Function to return a generated partial """
    api_result = {
        'result': 'Version %s of API ' % version
    }
    if version in app.config['unsupported_versions']:
        api_result['result'] += ' no longer supported'
        return flask.Response(str(api_result), status=410)
    if version not in app.config['supported_versions']:
        api_result['result'] += ' does not exist'
        return flask.Response(str(api_result), status=400)

    logging.debug('Request received with headers : %s', flask.request.headers)
    logging.debug('looking up record with identifier %s', identifier)

    cacheo = cache.Cache()
    if not cacheo.find(identifier, 'partial'):
        logging.info('Invalid partial request')
        resp = flask.Response(json.dumps({
            "result": "Partial with identifier %s not found" % identifier,
            }),
            status=400,
        )
        return resp

    if cacheo.is_blank_file(identifier, 'partial'):
        logging.info('Record found, status: IN PROGRESS')
        resp = flask.Response(json.dumps({
            "result": "wait",
            }),
            status=202,
        )
    else:
        logging.info('Record found, status: COMPLETED')
        resp = flask.Response(cacheo.retrieve(identifier, 'partial'),
                              status=200,
                              mimetype='application/octet-stream')
    return resp


def main(argv):
    """ Parse args, config files and perform configuration """
    parser = argparse.ArgumentParser(description='Some description')
    parser.add_argument('-c', '--config-file', type=str,
                        default='../configs/default.ini',
                        required=False, dest='config_file',
                        help='The application config file. INI format')
    args = parser.parse_args(argv)
    config_file = os.path.join(__here__, args.config_file)

    config = ConfigParser.ConfigParser()
    config.read(config_file)
    app.config['LOG_FILE'] = config.get('log', 'file_path')
    app.config['supported_versions'] = [
        x.strip() for x in config.get('version', 'supported_versions').split(',')
    ]
    app.config['unsupported_versions'] = [
        x.strip() for x in config.get('version', 'unsupported_versions').split(',')
    ]
    logging.info('Flask config at startup: %s' % app.config)


if __name__ == '__main__':

    main(sys.argv[1:])

    for version in app.config['unsupported_versions'] + app.config['supported_versions']:
        app.add_url_rule('/%s/partial' % version,
                         'trigger_partial',
                         trigger_partial,
                         methods=['POST'],
                         defaults={
                             'version': version
                         })
        app.add_url_rule('/%s/partial/<identifier>' % version,
                         'get_partial',
                         view_func=get_partial,
                         methods=['GET'],
                         defaults={
                             'version': version
                         })

    logging.basicConfig(filename=app.config['LOG_FILE'], level=logging.INFO)
    app.run(debug=False, host='0.0.0.0', processes=6)