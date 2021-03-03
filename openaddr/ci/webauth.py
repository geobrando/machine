import logging; _L = logging.getLogger('openaddr.ci.webapi')

import os, json, hmac, hashlib
from urllib.parse import urljoin, urlencode, urlunparse
from datetime import datetime, timedelta
from dateutil.tz import tzutc
from base64 import b64encode
from functools import wraps
from random import randint

from flask import (
    request, url_for, current_app, render_template, session, redirect, Blueprint
    )

from itsdangerous import URLSafeSerializer
import requests, uritemplate, boto

from . import setup_logger
from .webcommon import log_application_errors, flask_log_level

github_authorize_url = 'https://github.com/login/oauth/authorize{?state,client_id,redirect_uri,response_type,scope}'
github_exchange_url = 'https://github.com/login/oauth/access_token'
github_membership_url = 'https://api.github.com/orgs/{org}/members/{username}'
github_user_url = 'https://api.github.com/user'

USER_KEY = 'github user'
TOKEN_KEY = 'github token'
MAX_UPLOAD_SIZE = 600 * 1024 * 1024

webauth = Blueprint('webauth', __name__)

def serialize(secret, data):
    return URLSafeSerializer(secret).dumps(data)

def unserialize(secret, data):
    return URLSafeSerializer(secret).loads(data)

def exchange_tokens(code, client_id, secret):
    ''' Exchange the temporary code for an access token

        http://developer.github.com/v3/oauth/#parameters-1
    '''
    data = dict(client_id=client_id, code=code, client_secret=secret)
    resp = requests.post(github_exchange_url, urlencode(data),
                         headers={'Accept': 'application/json'})
    auth = resp.json()

    if 'error' in auth:
        raise RuntimeError('Github said "{error}".'.format(**auth))

    elif 'access_token' not in auth:
        raise RuntimeError("missing `access_token`.")

    return auth

def user_information(token, org_name='openaddresses'):
    '''
    '''
    header = {'Authorization': 'token {}'.format(token)}
    resp1 = requests.get(github_user_url, headers=header)

    if resp1.status_code != 200:
        return None, None, None

    login, avatar_url = resp1.json().get('login'), resp1.json().get('avatar_url')

    membership_args = dict(org=org_name, username=login)
    membership_url = uritemplate.expand(github_membership_url, membership_args)
    resp2 = requests.get(membership_url, headers=header)

    return login, avatar_url, bool(resp2.status_code in range(200, 299))

def update_authentication(untouched_route):
    '''
    '''
    @wraps(untouched_route)
    def wrapper(*args, **kwargs):
        # remove this always
        if USER_KEY in session:
            session.pop(USER_KEY)

        if TOKEN_KEY in session:
            login, avatar_url, in_org = user_information(session[TOKEN_KEY])

            if login and in_org:
                session[USER_KEY] = dict(login=login, avatar_url=avatar_url)
            elif not login:
                session.pop(TOKEN_KEY)
                return render_template('oauth-hello.html', user_required=True,
                                       user=None, error_bad_login=True)
            elif not in_org:
                session.pop(TOKEN_KEY)
                return render_template('oauth-hello.html', user_required=True,
                                       user=None, error_org_membership=True)

        return untouched_route(*args, **kwargs)

    return wrapper

def s3_upload_form_fields(expires, bucketname, subdir, redirect_url, s3):
    '''
    '''
    policy = {
        "expiration": expires.strftime('%Y-%m-%dT%H:%M:%SZ'),
        "conditions": [
            {"bucket": bucketname},
            ["starts-with", "$key", "cache/uploads/{}/".format(subdir)],
            {"success_action_redirect": redirect_url},
            ["content-length-range", 16, MAX_UPLOAD_SIZE]
        ]
    }

    if s3.provider.security_token:
        policy['conditions'].append({'x-amz-security-token': s3.provider.security_token})

    policy_b64 = b64encode(json.dumps(policy).encode('utf8'))
    signature = hmac.new(s3.secret_key.encode('utf8'), policy_b64, hashlib.sha1)
    signature_b64 = b64encode(signature.digest())

    fields = dict(
        key=policy['conditions'][1][2] + '${filename}',
        policy=policy_b64.decode('utf8'),
        signature=signature_b64.decode('utf8'),
        access_key=s3.access_key
        )

    if s3.provider.security_token:
        fields['security_token'] = s3.provider.security_token

    return fields

@webauth.route('/auth')
@update_authentication
@log_application_errors
def app_auth():
    return render_template('oauth-hello.html', user_required=True,
                           user=session.get(USER_KEY, {}))

@webauth.route('/auth/callback')
@log_application_errors
def app_callback():
    state = unserialize(current_app.secret_key, request.args['state'])

    token = exchange_tokens(request.args['code'],
                            current_app.config['GITHUB_OAUTH_CLIENT_ID'],
                            current_app.config['GITHUB_OAUTH_SECRET'])

    session[TOKEN_KEY] = token['access_token']

    return redirect(state.get('url', url_for('webauth.app_auth')), 302)

@webauth.route('/auth/login', methods=['POST'])
@log_application_errors
def app_login():
    state = serialize(current_app.secret_key,
                      dict(url=request.headers.get('Referer')))

    args = dict(redirect_uri=url_for('webauth.app_callback', _external=True), response_type='code', state=state)
    args.update(client_id=current_app.config['GITHUB_OAUTH_CLIENT_ID'])
    args.update(scope='user,public_repo,read:org')

    return redirect(uritemplate.expand(github_authorize_url, args), 303)

@webauth.route('/auth/logout', methods=['POST'])
@log_application_errors
def app_logout():
    if TOKEN_KEY in session:
        session.pop(TOKEN_KEY)

    if USER_KEY in session:
        session.pop(USER_KEY)

    return redirect(url_for('webauth.app_auth'), 302)

@webauth.route('/upload-cache')
@update_authentication
def app_upload_cache_data():
    '''
    '''
    if USER_KEY not in session:
        return render_template('upload-cache.html', user_required=True, user=None)

    random = hex(randint(0x100000, 0xffffff))[2:]
    subdir = '{login}/{0}'.format(random, **session[USER_KEY])
    expires = datetime.now(tz=tzutc()) + timedelta(minutes=5)

    redirect_url = url_for('webauth.app_upload_cache_data', _external=True)
    bucketname, s3 = current_app.config['AWS_S3_BUCKET'], boto.connect_s3()
    fields = s3_upload_form_fields(expires, bucketname, subdir, redirect_url, s3)

    fields.update(
        bucket=current_app.config['AWS_S3_BUCKET'],
        redirect=redirect_url,
        callback=request.args
        )

    return render_template('upload-cache.html', user_required=True,
                           user=session[USER_KEY], **fields)

def apply_webauth_blueprint(app):
    '''
    '''
    app.register_blueprint(webauth)

    # Use Github OAuth secret to sign Github login cookies too.
    app.secret_key = app.config['GITHUB_OAUTH_SECRET']

    @app.before_first_request
    def app_prepare():
        setup_logger(os.environ.get('AWS_SNS_ARN'), None, flask_log_level(app.config))
