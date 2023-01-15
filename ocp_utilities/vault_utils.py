import logging
import requests
import urllib3
from hvac import Client as hvacClient
from urllib3.exceptions import InsecureRequestWarning

urllib3.disable_warnings(InsecureRequestWarning)

LOGGER = logging.getLogger(__name__)


def get_vault_config(vault_url, data_path, role_id, secret_id, verify=True):
    """
    Fetch vault data config
    Args:
        vault_url (str): vault url host to create client
        data_path (str): path within vault to read from 'apps/data/..
        role_id (str): for example: 'mps-qe'
        secret_id (str): could be exported env variable
        verify (bool): indicates whether TLS verification should be performed when sending requests to Vault
    Returns:
        dict: out if command succeeded, err otherwise.
    """
    try:
        vault_client = hvacClient(
            url=vault_url, verify=verify
        )

        vault_client.auth.approle.login(
            role_id=role_id,
            secret_id=secret_id,
        )

        return vault_client.read(path=data_path)
    except requests.exceptions.ConnectionError:
        LOGGER.error("Failed to connect to vault.")
        raise
