from flask import Blueprint, request, jsonify
from google.cloud import datastore
import json
import verificationHelper
import constants

client = datastore.Client()

bp = Blueprint('game', __name__, url_prefix='/games')

@bp.route('/', methods=['POST','GET'])
def games_get_post():
    if request.method == 'POST':
        payload = verificationHelper.verify_jwt(request)
        if len(payload) == 0:
            return ("INVALID JWT", 401)
        content = request.get_json()
        if 'home' not in content.keys():
            return("need home team", 400)
        if 'away' not in content.keys():
            return("need away team", 400)
        if 'odds' not in content.keys() or len(content['odds']) != 2:
            return("please give home then away odds as decimal in a list", 400)
        if 'maxLoss' not in content.keys() or content['maxLoss'] < 100:
            return("Need to know the potential loss for the game", 400)
        if 'description' not in content.keys():
            content['description'] = ''
        decOdds = content['odds']
        if decOdds[0] == 0 or decOdds[1] == 0 or decOdds[0] + decOdds[1] != 1:
            return("The decimal odds must add up to 1 and cannot be 0", 400)
        homeOdds = (1 / decOdds[0]) * 0.9
        awayOdds = (1 / decOdds[1]) * 0.9
        new_game = datastore.entity.Entity(key=client.key(constants.games))
        new_game.update({'home': content['home'], 'away': content['away'],
          'homeOdds': homeOdds, 'awayOdds': awayOdds, 'totalPool': 0, 
          'maxLoss': content['maxLoss'], 'wagers': [],
          'homeLiability': 0, 'awayLiability': 0, 'completed': False, 
          'description': content['description'], 'owner': payload})
        client.put(new_game)
        return str(new_game.key.id)
    elif request.method == 'GET':
        query = client.query(kind=constants.games)
        q_limit = int(request.args.get('limit', '5'))
        q_offset = int(request.args.get('offset', '0'))
        l_iterator = query.fetch(limit= q_limit, offset=q_offset)
        pages = l_iterator.pages
        results = list(next(pages))
        if l_iterator.next_page_token:
            next_offset = q_offset + q_limit
            next_url = request.base_url + "?limit=" + str(q_limit) + "&offset=" + str(next_offset)
        else:
            next_url = None
        for e in results:
            selfLink = request.host_url + 'games/' + str(e.key.id)
            e["self"] = selfLink
        output = {"games": results}
        if next_url:
            output["next"] = next_url
        return json.dumps(output)
    else:
        return 'Method not recogonized'

@bp.route('/<id>', methods=['DELETE', 'GET'])
def games_put_delete_get(id):
    if request.method == 'DELETE':
        game_key = client.key(constants.games, int(id))
        game = client.get(key=game_key)
        if game is None:
            return('Invalid game ID', 400)
        elif len(game['loads']) == 0:
            client.delete(game_key)
            return ('', 200)
        else:
            for x in game['loads']:
                load_key = client.key(constants.loads, int(x))
                load = client.get(key=load_key)
                load.update({'owner': load['owner'], 'game': '', 'weight': load['weight'], 'contents': load['contents']})
                client.put(load)
            client.delete(game_key)
            return ('', 200)
    elif request.method == 'GET':
        game_key = client.key(constants.games, int(id))
        game = client.get(key=game_key)
        if game is None:
            return('Invalid game ID', 400)
        else:
            output = []
            for x in game['loads']:
                load_key = client.key(constants.loads, int(x))
                load = client.get(key=load_key)
                load['self'] = request.host_url + '/loads/' + str(x)
                output.append(load)
            game['loads'] = output
            return (game, 200)
    else:
        return 'Method not recogonized'