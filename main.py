from google.cloud import datastore
from flask import Flask, request, jsonify
from requests_oauthlib import OAuth2Session
import json
import constants
import cloud_keys
import verificationHelper
import game
from google.oauth2 import id_token
from google.auth import crypt
from google.auth import jwt
from google.auth.transport import requests

# This disables the requirement to use HTTPS so that you can test locally.
import os 
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.register_blueprint(game.bp)
client = datastore.Client()


# These should be copied from an OAuth2 Credential section at
# https://console.cloud.google.com/apis/credentials
client_id = cloud_keys.client_id
client_secret = cloud_keys.client_secret

# This is the page that you will use to decode and collect the info from
# the Google authentication flow
redirect_uri = 'https://minibookie.wn.r.appspot.com/oauth'

# These let us get basic info to identify a user and not much else
# they are part of the Google People API
scope = ['openid', 'https://www.googleapis.com/auth/userinfo.email',
             'https://www.googleapis.com/auth/userinfo.profile']
oauth = OAuth2Session(client_id, redirect_uri=redirect_uri,
                          scope=scope)

#error handler from Piazza
class AuthError(Exception):
    def __init__(self, error, status_code):
        self.error = error
        self.status_code = status_code


@app.errorhandler(AuthError)
def handle_auth_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    return response


# This link will redirect users to begin the OAuth flow with Google
@app.route('/')
def index():
    authorization_url, state = oauth.authorization_url(
        'https://accounts.google.com/o/oauth2/auth',
        # access_type and prompt are Google specific extra
        # parameters.
        access_type="offline", prompt="select_account")
    return 'Please go <a href=%s>here</a> and authorize access.' % authorization_url

# This is where users will be redirected back to and where you can collect
# the JWT for use in future requests
@app.route('/oauth')
def oauthroute():
    token = oauth.fetch_token(
        'https://accounts.google.com/o/oauth2/token',
        authorization_response=request.url,
        client_secret=client_secret)
    req = requests.Request()

    id_info = id_token.verify_oauth2_token( 
    token['id_token'], req, client_id)

    if id_info['email_verified'] == False:
        return ({'error': "invalid email"}, 401)

    query = client.query(kind=constants.users)
    query.add_filter('email', '=', id_info['email'])
    results = list(query.fetch())
    if len(results) == 0:
        new_user = datastore.entity.Entity(key=client.key(constants.users))
        new_user.update({'name': id_info['sub'], 'email': id_info['email'], 'balance': 0})
        client.put(new_user)

    return ("Your JWT is: %s" % token['id_token'], 201)


@app.route('/users', methods=['GET'])
def users_get():
    if request.method == 'GET':
        query = client.query(kind=constants.users)
        results = list(query.fetch())
        for e in results:
            e["id"] = e.key.id
        return (json.dumps(results), 200)
    else:
        return ({'Error': "Method not recognized"}, 405)
