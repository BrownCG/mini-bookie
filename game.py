from flask import Blueprint, request, jsonify
from google.cloud import datastore
import json
import verificationHelper
import constants

client = datastore.Client()

bp = Blueprint('game', __name__, url_prefix='/games')

#create and read all routes from url/games
@bp.route('/', methods=['POST','GET'])
def games_get_post():
    if request.method == 'POST':
        #authenticate user and prepare to set as game owner
        payload = verificationHelper.verify_jwt(request)
        if payload == 0:
            return ({"Error": "INVALID JWT"}, 401)
        content = request.get_json()
        #validate input
        if 'home' not in content.keys():
            return("need home team", 400)
        if 'away' not in content.keys():
            return("need away team", 400)
        if 'odds' not in content.keys() or type(content['odds']) != list:
            return("please give home then away odds as decimal in a list", 400)
        if 'maxLoss' not in content.keys() or content['maxLoss'] < 100:
            return("Need to know the potential loss for the game", 400)
        if 'description' not in content.keys():
            content['description'] = ''
        if 'vig' not in content.keys() or content['vig'] < 0.05 or content['vig'] > 0.4:    #can change house cut if wanted, but defaults to industry standard 10pct
            content['vig'] = 0.1
        decOdds = content['odds']
        if decOdds[0] == 0 or decOdds[1] == 0 or decOdds[0] + decOdds[1] != 1:
            return("The decimal odds must add up to 1 and cannot be 0", 400)
        #set public facing odds
        homeOdds = (1 / decOdds[0]) * (1 - content['vig'])
        awayOdds = (1 / decOdds[1]) * (1 - content['vig'])
        #create and populate new entity
        new_game = datastore.entity.Entity(key=client.key(constants.games))
        new_game.update({'home': content['home'], 'away': content['away'],
          'homeOdds': homeOdds, 'awayOdds': awayOdds, 'totalPool': 0, 
          'maxLoss': content['maxLoss'], 'wagers': [],
          'homeLiability': 0, 'awayLiability': 0, 'vig': content['vig'], 'completed': False, 
          'description': content['description'], 'owner': payload})
        client.put(new_game)
        gameInfo = {"gameID": str(new_game.key.id), "self": request.host_url + 'games/' + str(new_game.key.id)}
        return (gameInfo, 201)
    elif request.method == 'GET':
        query = client.query(kind=constants.games)
        q_limit = int(request.args.get('limit', '5'))
        q_offset = int(request.args.get('offset', '0'))
        l_iterator = query.fetch(limit= q_limit, offset=q_offset)
        pages = l_iterator.pages
        results = list(next(pages))
        gameBlurbs = []
        if l_iterator.next_page_token:
            next_offset = q_offset + q_limit
            next_url = request.base_url + "?limit=" + str(q_limit) + "&offset=" + str(next_offset)
        else:
            next_url = None
        for e in results:
            selfLink = request.host_url + 'games/' + str(e.key.id)
            gameBlurb = {'home': e['home']}
            gameBlurb['homeOdds'] = e['homeOdds']
            gameBlurb['away'] = e['away']
            gameBlurb['awayOdds'] = e['awayOdds']
            gameBlurb['description'] = e['description']
            gameBlurb['self'] = selfLink
            gameBlurbs.append(gameBlurb)
        output = {"games": gameBlurbs}
        if next_url:
            output["next"] = next_url
        return json.dumps(output)
    else:
        return ({"Error": "Method not recogonized"}, 405)

#get or delete (i.e. cancel and refund) a specific game
@bp.route('/<id>', methods=['DELETE', 'GET'])
def games_put_delete_get(id):
    if request.method == 'DELETE':
        #authenticate user
        payload = verificationHelper.verify_jwt(request)
        if payload == 0:
            return ({"Error": "INVALID JWT"}, 401)
        game_key = client.key(constants.games, int(id))
        game = client.get(key=game_key)
        if game is None:
            return({"Error": "Invalid game ID"}, 404)
        elif payload != game['owner']:                          #authorize user
            return({"Error": "Not your game to delete"}, 403)
        elif len(game['wagers']) == 0:
            client.delete(game_key)
            return ('', 204)
        else:
            # for x in game['wagers']:
            #     load_key = client.key(constants.loads, int(x))
            #     load = client.get(key=load_key)
            #     load.update({'owner': load['owner'], 'game': '', 'weight': load['weight'], 'contents': load['contents']})
            #     client.put(load)
            client.delete(game_key)
            return ('', 204)
    elif request.method == 'GET':
        game_key = client.key(constants.games, int(id))
        game = client.get(key=game_key)
        if game is None:
            return({"Error": "Invalid game ID"}, 404)
        else:
            # output = []
            # for x in game['loads']:
            #     load_key = client.key(constants.loads, int(x))
            #     load = client.get(key=load_key)
            #     load['self'] = request.host_url + '/loads/' + str(x)
            #     output.append(load)
            # game['loads'] = output
            return (game, 200)
    else:
        return ({"Error": "Method not recogonized"}, 405)