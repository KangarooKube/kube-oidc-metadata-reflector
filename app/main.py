import os
from flask import Flask, jsonify
import json
from logging.config import dictConfig
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# setup logging
dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "default",
            }
        },
        "root": {"level": "DEBUG", "handlers": ["console"]},
    }
)

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

def get_k8s_client_well_known_api():
    try:
        # Load in-cluster config
        config.load_incluster_config()
    except config.config_exception.ConfigException:
        # Fall back to kube config file if not in a cluster
        config.load_kube_config()

    return client.WellKnownApi()

def get_k8s_client_openid_api():
    try:
        # Load in-cluster config
        config.load_incluster_config()
    except config.config_exception.ConfigException:
        # Fall back to kube config file if not in a cluster
        config.load_kube_config()

    return client.OpenidApi()

# Route for OIDC discovery document which contains the metadata about the issuer’s configurations
@app.route('/.well-known/openid-configuration', methods=['GET'])
def get_openid_configuration():
    k8s_client = get_k8s_client_well_known_api()
    try:
        # Fetch the OpenID configuration from the Kubernetes API
        api_response = k8s_client.get_service_account_issuer_open_id_configuration(_preload_content=False)
        openid_configuration = json.loads(api_response.data)
    except ApiException as e:
        app.logger.error(e)
        return jsonify({'error': str(e)}), 500

    return jsonify(openid_configuration)

# Route for JSON Web Key Sets (JWKS) document which contains the public signing key(s) for service accounts
@app.route('/openid/v1/jwks', methods=['GET'])
def get_jwks():
    k8s_client = get_k8s_client_openid_api()
    try:
        # Fetch the JWKS document from the Kubernetes API
        api_response = k8s_client.get_service_account_issuer_open_id_keyset(_preload_content=False)
        jwks = json.loads(api_response.data)
    except ApiException as e:
        app.logger.error(e)
        return jsonify({'error': str(e)}), 500

    return jsonify(jwks)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
