#from flask import Flask, request, Response
import flask
import logging

import core
import flasktask
import db
import tasks

# FIXME: Load this from a preference file
DB_URI = 'sqlite:///test.db'
CACHE_URI = '/perma/cache/'

dbo = db.DBInterface(DB_URI)
cacheo = cache.Cache(CACHE_URI)

app = flask.Flask(__name__)

@app.route('/')
def index():
    return "Index"

@app.route('/hello')
def hello():
    flasktask.hello()
    return 'Hello World'

@app.route('/partial', methods=['POST'])
def trigger_partial():
    """
    Needs params: mar_from, mar_to, mar_from_hash, mar_to_hash
    """

    logging.debug('Parameters passed in : %s' % flask.request.form)

    required_params = ('mar_from', 'mar_to', 'mar_from_hash', 'mar_to_hash')
    # Check we have all params
    if not all(param in flask.request.form.keys() for param in required_params):
        logging.info('Parameters could not we validated')
        flask.abort(400)

    # TODO: Validate params and values in form Ideally
    #pprint.pprint(flask.request.form)
    mar_from = flask.request.form['mar_from']
    mar_to = flask.request.form['mar_to']
    mar_from_hash = flask.request.form['mar_from_hash']
    mar_to_hash = flask.request.form['mar_to_hash']
    # TODO: Verify hashes and URLs are valid before returning the URL with a 201
    #       or return the concat anyway and just return a 202?

    # Try inserting into DB, if it fails, check error
    identifier = mar_from_hash+'-'+mar_to_hash
    url = flask.url_for('get_partial', identifier=identifier)

    try:
        # error testing and parameter validation, maybe do this up close to checking
        # existence
        #db.insert(identifier=None, url=url, status=db.status_code['IN_PROGRESS'])

        dbo.insert(identifier=identifier, url=url, status=db.status_code['IN_PROGRESS'])
    except db.IntegrityError, e:
        #print "Couldn't insert, got error: %s" % e
        # Lookup and get url and return it
        partial = dbo.lookup(identifier=identifier)
        print "**"*10
        print partial
        print "**"*10
        resp = flask.Response(
                "{'result': '%s'}" % partial.url,
                status=201,
                mimetype='application/json'
                )
        return resp
    else:
        print "calling generation functions"
        # Call generation functions here
        resp = flask.Response("{'result' : '%s'}" % url, status=202, mimetype='application/json')

        tasks.build_partial_mar.delay(mar_to, mar_to_hash, mar_from,
                mar_from_hash, identifier)

        return resp

    # If record exists, just say done
    # If other major error, do something else
    # TODO: Hook responses up with relengapi -- https://api.pub.build.mozilla.org/docs/development/api_methods/
    return resp

@app.route('/partial/<identifier>', methods=['GET'])
def get_partial(identifier):
    # Check DB state corresponding to URL
    # if "Completed", return blob and hash
    # if "Started", stall by inprogress error code
    # if "Invalid", return error code
    # if "does not exist", return different error code

    logging.debug('Request recieved with headers : %s' % flask.request.headers)
    logging.info('Request recieved for identifier %s' % identifier)
    partial = dbo.lookup(identifier=identifier)

    if not partial:
        logging.info('Record corresponding to identifier %s does not exist.' % identifier)
        resp = flask.Response("{'result':'partial does not exist'}", status=404)
    else:
        logging.info('Record corresponding to identifier %s found.' % identifier)
        status = partial.status
        print status
        if status == db.status_code['COMPLETED']:
            # Lookup DB and return blob
            # Call relevant functions from the core section.
            # We'll want to stream the data to the client eventually, right now,
            # we can just throw it at the client just like that.
            identifier = partial.identifier
            resp = flask.Response("{'result': '%s'}" % identifier, status=200)

        elif status == db.status_code['ABORTED']:
            # Something went wrong, what do we do?
            resp = flask.Response("{'result': '%s'}" %
                        "Something went wrong while generating this partial",
                        status=204)

        elif status == db.status_code['IN_PROGRESS']:
            # Stall still status changes
            resp = flask.Response("{'result': '%s'}" % "wait", status=202)

        elif status == db.status_code['INVALID']:
            # Not sure what this status code is even for atm.
            resp = flask.Response("{'result': '%s'}" % "invalid partial", status=204)


        else:
            # This should not happen
            resp = flask.Response("{'result':'%s'}" % 
                                  "Status of this partial is unknown",
                                  status=400)

    return resp

if __name__ == '__main__':
    app.run(debug=True)
    dbo.close()