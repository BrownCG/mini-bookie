
from flask import Flask, request
from google.oauth2 import id_token
from google.auth import crypt
from google.auth import jwt
from google.auth.transport import requests
import cloud_keys

#Verification handler adopted from
def verify_jwt(request):
    try:
        auth_header = request.headers['Authorization'].split()
        token = auth_header[1]
        req = requests.Request()
        id_info = id_token.verify_oauth2_token( 
        token, req, cloud_keys.client_id)
        return id_info['sub']
    except:
        return ''