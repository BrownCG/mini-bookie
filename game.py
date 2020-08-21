from flask import Blueprint, request, jsonify
from google.cloud import datastore
import json
import verificationHelper
import constants

client = datastore.Client()

bp = Blueprint('game', __name__, url_prefix='/games')

# create and read all routes from url/games
@bp.route('/', methods=['POST','GET'])
def games_get_post():
    if request.method == 'POST':
        # authenticate user and prepare to set as game owner
        payload = verificationHelper.verify_jwt(request)
        if payload == 0:
            return ({"Error": "INVALID JWT"}, 401)
        content = request.get_json()
        # validate input
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
        if 'vig' not in content.keys() or content['vig'] < 0.05 or content['vig'] > 0.4:    # can change house cut if wanted, but defaults to industry standard 10pct
            content['vig'] = 0.1
        decOdds = content['odds']
        if decOdds[0] == 0 or decOdds[1] == 0 or decOdds[0] + decOdds[1] != 1:
            return("The decimal odds must add up to 1 and cannot be 0", 400)
        # set public facing odds
        homeOdds = (1 / decOdds[0]) * (1 - content['vig'])
        awayOdds = (1 / decOdds[1]) * (1 - content['vig'])
        # create and populate new entity
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

# from the individual game route, can read, "cancel", declare winner, or place wager
@bp.route('/<id>', methods=['DELETE', 'GET', 'POST', 'PUT'])
def games_post_put_delete_get(id):
    # deleting acts as cancelling a game, refunding amount bet but keeping ticket record for receipt
    if request.method == 'DELETE':
        # authenticate user
        payload = verificationHelper.verify_jwt(request)
        if payload == 0:
            return ({"Error": "INVALID JWT"}, 401)
        game_key = client.key(constants.games, int(id))
        game = client.get(key=game_key)
        if game is None:
            return({"Error": "Invalid game ID"}, 404)
        elif payload != game['owner']:                          # authorize user
            return({"Error": "Not your game to delete"}, 403)
        elif len(game['wagers']) == 0:
            client.delete(game_key)
            return ('', 204)
        else:
            for x in game['wagers']:
                wager_key = client.key(constants.wagers, int(x))
                wager = client.get(key=wager_key)
                wager['status'] = 'REFUND'
                client.put(wager)
                query = client.query(kind=constants.users)
                query.add_filter('name', '=', wager['owner'])
                betPlacer = list(query.fetch())
                refund = betPlacer[0]
                refund['balance'] += wager['betSize']
                client.put(refund)
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
    elif request.method == 'POST':
        # authenticate user to place bet
        payload = verificationHelper.verify_jwt(request)
        if payload == 0:
            return ({"Error": "INVALID JWT"}, 401)
        content = request.get_json()
        # validate input
        if 'betSize' not in content.keys() or content['betSize'] < 1:
            return("must bet at least one unit", 400)
        if 'betTeam' not in content.keys():
            return("need a team to bet on", 400)
        game_key = client.key(constants.games, int(id))
        game = client.get(key=game_key)
        if game is None:
            return({"Error": "Invalid game ID"}, 404)
        oddMulti = 0
        curLiability = 0
        betTeam = ''
        if content['betTeam'] == 'HOME':
            oddMulti = game['homeOdds']
            curLiability = game['homeLiability']
            betTeam = game['home']
        if content['betTeam'] == 'AWAY':
            oddMulti = game['awayOdds']
            curLiability = game['awayLiability']
            betTeam = game['away']
        propLiability = round((content['betSize'] * oddMulti), 2)
        # do not allow a single bet to eat up too much of the books risk 
        if propLiability > ((game['totalPool'] + game['maxLoss'] - curLiability) / 4):
            return ({"Error": "The bet you placed was too large for the current pool"}, 400) 
        # update the odds for future bets
        prevHomeOdds = (1 / game['homeOdds']) * (1 - game['vig'])
        prevAwayOdds = (1 / game['awayOdds']) * (1 - game['vig'])
        homePool = (game['totalPool'] + game['maxLoss']) * prevHomeOdds
        awayPool = (game['totalPool'] + game['maxLoss']) * prevAwayOdds
        if content['betTeam'] == 'HOME':
            game['homeLiability'] += propLiability
            homePool += propLiability
            if game['homeOdds'] <= 1.05:
                return ({"Error": "Action is not currently being taken on this side of the line"}, 400)
        if content['betTeam'] == 'AWAY':
            game['awayLiability'] += propLiability
            awayPool += propLiability
            if game['awayOdds'] <= 1.05:
                return ({"Error": "Action is not currently being taken on this side of the line"}, 400)
        game['totalPool'] += content['betSize']
        homePct = (homePool / (homePool + awayPool))
        awayPct = (awayPool / (homePool + awayPool))
        game['homeOdds'] = round((1 / homePct) * (1 - game['vig']), 2)
        game['awayOdds'] = round((1 / awayPct) * (1 - game['vig']), 2)
        if game['homeOdds'] <= 1.05 or game['awayOdds'] <= 1.05:
            return ({"Error": "Action is not currently being taken on this side of the line"})
        # create and populate new entity
        new_wager = datastore.entity.Entity(key=client.key(constants.wagers))
        new_wager.update({'betTeam': betTeam, 'betWin': propLiability,
          'betSize': content['betSize'], 'game': str(id), 
          'status': 'OPEN', 'bookie': game['owner'], 'owner': payload})
        client.put(new_wager)
        wagerInfo = {"wagerID": str(new_wager.key.id), "self": request.host_url + 'wagers/' + str(new_wager.key.id), "homeChance": homePct, "awayChance": awayPct}
        # update the game odds, pools, and wager list
        game['wagers'].append(new_wager.key.id)
        client.put(game)
        #update betPlacers balance
        query = client.query(kind=constants.users)
        query.add_filter('name', '=', payload)
        betPlacer = list(query.fetch())
        refund = betPlacer[0]
        refund['balance'] -= content['betSize']
        client.put(refund)
        return (wagerInfo, 201)
    elif request.method == 'PUT':
        return 200
    else:
        return ({"Error": "Method not recogonized"}, 405)
