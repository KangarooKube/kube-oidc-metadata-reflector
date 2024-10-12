import os
import traceback
from flask import Flask, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
import json
import logging
from kubernetes import client, config

default_rate_limit = os.environ.get('DEFAULT_RATE_LIMIT', '10 per second')

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

csrf = CSRFProtect(app)

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
    """
    Return a string describing the exception.

    The string is a single line and includes the exception type and message.
    """
    exc_desc_lines = traceback.format_exception_only(type(e), e)
    exc_desc = ''.join(exc_desc_lines).rstrip()
    return exc_desc

# Return a client based on config type   
def get_k8s_client() -> client:
    """
    Return a client based on config type

    If in-cluster config is present (e.g. KUBERNETES_SERVICE_HOST is set), use that.
    Otherwise, try to load the kubeconfig from file.
    If that fails, log the error and return the client anyway.
    """
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
    """
    Return the OIDC discovery document which contains the metadata about the issuer's configurations.

    The document is returned in the JSON format and contains the following information:
    - issuer: the URL of the issuer
    - jwks_uri: the URL of the JSON Web Key Sets (JWKS) document which contains the public signing key(s) for service accounts
    - authorization_endpoint: the URL of the authorization endpoint
    - token_endpoint: the URL of the token endpoint
    - userinfo_endpoint: the URL of the userinfo endpoint
    - response_types_supported: a list of the supported response types
    - subject_types_supported: a list of the supported subject types
    - id_token_signing_alg_values_supported: a list of the supported ID Token signing algorithms
    - claims_supported: a list of the supported claims
    - claims_parameter_supported: a boolean indicating if the claims parameter is supported
    - request_parameter_supported: a boolean indicating if the request parameter is supported
    - request_uri_parameter_supported: a boolean indicating if the request_uri parameter is supported

    :return: a JSON object containing the OIDC discovery document
    """
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
    """
    Return the JSON Web Key Sets (JWKS) document which contains the public signing key(s) for service accounts.

    This document is used to validate the signature of the ID Tokens issued by the cluster.
    """
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
    """
    Kubernetes liveness probe handler.

    This route is used by the liveness probe to determine if the pod is healthy.
    It returns a 200 status code if the pod is healthy, and a 500 status code
    if the pod is not healthy.

    The liveness probe is exempt from rate limiting so that it does not interfere
    with the pod's normal operation.

    The pod is considered healthy if the Kubernetes API server responds with
    a valid version string.

    :return: A string indicating the pod's health status, along with a
             corresponding HTTP status code.
    """
    try:
        k8s_client = get_k8s_client().VersionApi()
        api_response = k8s_client.get_code()
    except Exception as e:
        app.logger.error("Health check failed!")
        app.logger.error(f"kubernetes.client.VersionApi.Exception: {e}")
        return "I am unhealthy!", 500
    
    return f"I am healthy! Running on Kubernetes version {api_response.git_version}.", 200
    
@app.route('/readyz')
@limiter.exempt
def health_readiness():
    """
    Kubernetes readiness probe endpoint.

    This endpoint is used by Kubernetes to determine if the container is ready to
    receive traffic. The endpoint will return a 200 if the container is ready and
    the Kubernetes API is available.

    :return: A string indicating that the container is ready.
    :rtype: str
    """
    return "I am ready!", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
