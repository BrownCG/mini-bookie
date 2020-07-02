from flask import Blueprint, request, jsonify
from google.cloud import datastore
import json
import verificationHelper
import constants

client = datastore.Client()

bp = Blueprint('wager', __name__, url_prefix='/wagers')

#Get all the wagers placed from this profile
@bp.route('/', methods=['GET'])
def wagers_get():
    if request.method == 'GET':
         #authenticate user
        payload = verificationHelper.verify_jwt(request)
        if payload == 0:
            return ({"Error": "INVALID JWT"}, 401)
        query = client.query(kind=constants.wagers)
        if 'all' not in content.keys():
            query.add_filter('status', '=', 'OPEN')
        query.add_filter('owner', '=', 'OPEN')
        q_limit = int(request.args.get('limit', '10'))
        q_offset = int(request.args.get('offset', '0'))
        l_iterator = query.fetch(limit= q_limit, offset=q_offset)
        pages = l_iterator.pages
        results = list(next(pages))
        wagerBlurbs = []
        if l_iterator.next_page_token:
            next_offset = q_offset + q_limit
            next_url = request.base_url + "?limit=" + str(q_limit) + "&offset=" + str(next_offset)
        else:
            next_url = None
        for e in results:
            selfLink = request.host_url + 'wagers/' + str(e.key.id)
            wagerBlurb = {'betTeam': e['betTeam']}
            wagerBlurb['betSize'] = e['betSize']
            wagerBlurb['bookie'] = e['bookie']
            wagerBlurb['betWin'] = e['betWin']
            wagerBlurb['self'] = selfLink
            wagerBlurbs.append(wagerBlurb)
        output = {"wagers": wagerBlurbs}
        if next_url:
            output["next"] = next_url
        return json.dumps(output)
    else:
        return ({"Error": "Method not recogonized"}, 405)

#Inspect an individiual wager
@bp.route('/<id>', methods=['GET'])
def wagers_put_get(id):
    if request.method == 'GET':
        #authenticate user
        payload = verificationHelper.verify_jwt(request)
        if payload == 0:
            return ({"Error": "INVALID JWT"}, 401)
        wager_key = client.key(constants.wagers, int(id))
        wager = client.get(key=wager_key)
        if wager is None:
            return({"Error": "Invalid wager ID"}, 404)
        elif payload != wager['owner']:                          #authorize user
            return({"Error": "Not your wager to delete"}, 403)
        else:
            # output = []
            # for x in wager['loads']:
            #     load_key = client.key(constants.loads, int(x))
            #     load = client.get(key=load_key)
            #     load['self'] = request.host_url + '/loads/' + str(x)
            #     output.append(load)
            # wager['loads'] = output
            return (wager, 200)
    else:
        return ({"Error": "Method not recogonized"}, 405)