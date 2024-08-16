import os
import traceback
from flask import Flask, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import json
import logging
from kubernetes import client, config

default_rate_limit = os.environ.get('DEFAULT_RATE_LIMIT', '10 per second')

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
app.config['WTF_CSRF_ENABLED'] = False

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[default_rate_limit],
    storage_uri="memory://",
)

# Setup logging
if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

def get_exception_description(e: Exception) -> str:
    exc_desc_lines = traceback.format_exception_only(type(e), e)
    exc_desc = ''.join(exc_desc_lines).rstrip()
    return exc_desc

# Return a client based on config type   
def get_k8s_client() -> client:
    if "KUBERNETES_SERVICE_HOST" in os.environ:
        config.load_incluster_config()
    else:    
        try:
            config.load_kube_config()
        except config.ConfigException as e:
            app.logger.error(get_exception_description(e))
            
    return client

# Route for OIDC discovery document which contains the metadata about the issuer’s configurations
@app.route('/.well-known/openid-configuration', methods=['GET'])
def get_openid_configuration() -> json:
    try:
        k8s_client = get_k8s_client().WellKnownApi()
        api_response = k8s_client.get_service_account_issuer_open_id_configuration(_preload_content=False)
        openid_configuration = json.loads(api_response.data)
    except Exception as e:
        app.logger.error(f"kubernetes.client.WellKnownApi.Exception: {e}")
        return "Internal error check logs", 500

    return jsonify(openid_configuration)

# Route for JSON Web Key Sets (JWKS) document which contains the public signing key(s) for service accounts
@app.route('/openid/v1/jwks', methods=['GET'])
def get_jwks() -> json:
    try:
        k8s_client = get_k8s_client().OpenidApi()
        api_response = k8s_client.get_service_account_issuer_open_id_keyset(_preload_content=False)
        jwks = json.loads(api_response.data)
    except Exception as e:
        app.logger.error(f"kubernetes.client.OpenidApi.Exception: {e}")
        return "Internal error check logs", 500

    return jsonify(jwks)

@app.route('/livez')
@limiter.exempt
def health_liveness():
    try:
        k8s_client = get_k8s_client().VersionApi()
        api_response = k8s_client.get_code()#_preload_content=False)
    except Exception as e:
        app.logger.error("Health check failed!")
        app.logger.error(f"kubernetes.client.VersionApi.Exception: {e}")
        return "I am unhealthy!", 500
    
    return f"I am healthy! Running on Kubernetes version {api_response.git_version}.", 200
    
@app.route('/readyz')
@limiter.exempt
def health_readiness():

    return "I am ready!", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
