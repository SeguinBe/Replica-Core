from jwt import DecodeError, ExpiredSignature
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g, current_app


def create_token(user_uid):
    payload = {
        # 'sub': user.id,
        'user_uid': user_uid,  # subject
        'iat': datetime.utcnow(),  # issued at
        'exp': datetime.utcnow() + timedelta(days=14)  # expiry
    }
    token = jwt.encode(payload, current_app.secret_key)
    return token.decode('unicode_escape')


def parse_token(req):
    token = req.headers.get('Authorization').split()[1]
    return jwt.decode(token, current_app.secret_key)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not request.headers.get('Authorization'):
            response = jsonify(message='Missing authorization header')
            response.status_code = 401
            return response

        try:
            payload = parse_token(request)
        except DecodeError:
            response = jsonify(message='Token is invalid')
            response.status_code = 401
            return response
        except ExpiredSignature:
            response = jsonify(message='Token has expired')
            response.status_code = 401
            return response

        g.user_uid = payload['user_uid']

        return f(*args, **kwargs)

    return decorated_function
