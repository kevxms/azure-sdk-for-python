"""
Direct REST client for Service Bus management operations.

This module provides a client that bypasses Azure Resource Manager (ARM) and
communicates directly with internal Service Bus endpoints using certificate
authentication from Azure Key Vault.

Usage:
    Set these environment variables:
    - SERVICEBUS_RP_HOST: hostname:port without scheme
      Example: "swedencentral02.int.messaging.azure-int.net:44400"
    - SERVICEBUS_RP_CERT_KEYVAULT_URI: Key Vault certificate URI
      Example: "https://myvault.vault.azure.net/certificates/MyCert"
    
    Also requires (already used by other test infrastructure):
    - AZURE_SUBSCRIPTION_ID: Azure subscription ID
    - SERVICEBUS_RESOURCE_GROUP: Resource group name
"""

import atexit
import os
import json
import base64
import tempfile
import logging
import urllib3
from typing import Optional

import requests

# Suppress InsecureRequestWarning for internal endpoints
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# Environment variable configuration
SERVICEBUS_RP_HOST = os.environ.get("SERVICEBUS_RP_HOST", None)
SERVICEBUS_RP_CERT_KEYVAULT_URI = os.environ.get("SERVICEBUS_RP_CERT_KEYVAULT_URI", None)
# Reuse existing env vars for subscription and resource group
AZURE_SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID", None)
SERVICEBUS_RESOURCE_GROUP = os.environ.get("SERVICEBUS_RESOURCE_GROUP", None)

# Module-level temp file tracking for cleanup
_temp_files_to_cleanup = []


def _cleanup_temp_files():
    """Clean up any temporary certificate files at exit."""
    for path in _temp_files_to_cleanup:
        try:
            os.unlink(path)
        except Exception:
            pass


atexit.register(_cleanup_temp_files)


def _get_keyvault_certificate_as_pfx(cert_url: str) -> bytes:
    """
    Fetch certificate (with private key) from Key Vault using Azure CLI authentication.
    
    Args:
        cert_url: Key Vault certificate URL, e.g., 
                  "https://servicebustestkeyvault.vault.azure.net/certificates/AcisClientAuthCertForInt"
                  or with version: ".../AcisClientAuthCertForInt/1166c0beea1e47b9905dbe791a320bb0"
    
    Returns:
        PFX bytes containing the certificate and private key.
    """
    from azure.identity import AzureCliCredential
    from azure.keyvault.secrets import SecretClient
    
    # Parse the cert URL to extract vault URL and cert name
    # URL format: https://<vault-name>.vault.azure.net/certificates/<cert-name>[/<version>]
    parts = cert_url.rstrip("/").split("/")
    
    # Find the index of "certificates" in the URL
    try:
        cert_idx = parts.index("certificates")
    except ValueError:
        raise ValueError(f"Invalid Key Vault certificate URL: {cert_url}")
    
    vault_url = "/".join(parts[:cert_idx])  # e.g., "https://servicebustestkeyvault.vault.azure.net"
    cert_name = parts[cert_idx + 1] if len(parts) > cert_idx + 1 else None
    cert_version = parts[cert_idx + 2] if len(parts) > cert_idx + 2 else None
    
    if not cert_name:
        raise ValueError(f"Certificate name not found in URL: {cert_url}")
    
    credential = AzureCliCredential()
    
    # To get the private key, we need to fetch the certificate as a secret
    # Key Vault stores the full PFX (cert + private key) as a secret with the same name
    secret_client = SecretClient(vault_url=vault_url, credential=credential)
    
    if cert_version:
        secret = secret_client.get_secret(cert_name, cert_version)
    else:
        secret = secret_client.get_secret(cert_name)
    
    # The secret value is base64-encoded PFX
    pfx_bytes = base64.b64decode(secret.value)
    return pfx_bytes


def _create_cert_files_from_pfx(pfx_bytes: bytes, password: Optional[str] = None) -> tuple:
    """
    Extract certificate and key from PFX bytes and write to temporary PEM files.
    
    Returns:
        Tuple of (cert_file_path, key_file_path) for use with requests library.
        Files are registered for cleanup at process exit.
    """
    from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
    from cryptography.hazmat.backends import default_backend
    
    # Load the PFX
    private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
        pfx_bytes, 
        password.encode() if password else None,
        default_backend()
    )
    
    # Convert to PEM format
    cert_pem = certificate.public_bytes(Encoding.PEM)
    key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())
    
    # Write to temporary files - these must persist for the lifetime of the process
    cert_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False)
    key_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False)
    
    cert_file.write(cert_pem)
    cert_file.close()
    
    key_file.write(key_pem)
    key_file.close()
    
    # Register for cleanup at exit
    _temp_files_to_cleanup.append(cert_file.name)
    _temp_files_to_cleanup.append(key_file.name)
    
    return cert_file.name, key_file.name


class ServiceBusDirectRestClient:
    """Direct REST client for Service Bus management operations using certificate auth from Key Vault."""
    
    DEFAULT_API_VERSION = "2017-04-01"
    
    def __init__(self, rp_host: str, keyvault_cert_uri: str, subscription_id: str, resource_group: str):
        # rp_host is hostname:port without scheme, e.g. "swedencentral02.int.messaging.azure-int.net:44400"
        self.base_url = f"https://{rp_host}".rstrip("/")
        self._cert_tuple = None  # (cert_file_path, key_file_path)
        self._keyvault_cert_uri = keyvault_cert_uri
        self._session = requests.Session()
        self.subscription_id = subscription_id
        self.resource_group = resource_group
    
    def _get_cert_tuple(self):
        """Lazy-load certificate files from Key Vault."""
        if self._cert_tuple is None:
            logging.info(f"Fetching certificate from Key Vault: {self._keyvault_cert_uri}")
            pfx_bytes = _get_keyvault_certificate_as_pfx(self._keyvault_cert_uri)
            self._cert_tuple = _create_cert_files_from_pfx(pfx_bytes)
            logging.info(f"Certificate loaded successfully: {self._cert_tuple}")
        return self._cert_tuple
    
    def _build_namespace_path(self, namespace: str) -> str:
        """Build the ARM-style path prefix for a namespace."""
        return f"/subscriptions/{self.subscription_id}/resourcegroups/{self.resource_group}/providers/Microsoft.ServiceBus/namespaces/{namespace}"
    
    def _request(self, method: str, path: str, body: Optional[dict] = None, api_version: str = None) -> dict:
        """Make an HTTP request with certificate authentication."""
        if api_version is None:
            api_version = self.DEFAULT_API_VERSION
        
        # Add api-version query parameter
        separator = "&" if "?" in path else "?"
        url = f"{self.base_url}{path}{separator}api-version={api_version}"
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        cert_tuple = self._get_cert_tuple()
        
        logging.info(f"Direct REST {method} {url}")
        
        response = self._session.request(
            method=method,
            url=url,
            headers=headers,
            json=body if body else None,
            cert=cert_tuple,
            verify=False,
        )
        
        logging.info(f"Direct REST response: {response.status_code}")
        
        if response.status_code in (200, 201, 202, 204):
            if response.text:
                return response.json()
            return {}
        
        response.raise_for_status()
    
    # Queue operations
    def create_queue(
        self,
        namespace: str,
        queue_name: str,
        lock_duration: str = "PT30S",
        requires_duplicate_detection: bool = False,
        dead_lettering_on_message_expiration: bool = False,
        requires_session: bool = False,
        enable_partitioning: bool = False,
        api_version: str = None,
    ) -> dict:
        path = f"{self._build_namespace_path(namespace)}/queues/{queue_name}"
        properties = {
            "properties": {
                "lockDuration": lock_duration,
                "requiresDuplicateDetection": requires_duplicate_detection,
                "deadLetteringOnMessageExpiration": dead_lettering_on_message_expiration,
                "requiresSession": requires_session,
                "enablePartitioning": enable_partitioning,
            }
        }
        return self._request("PUT", path, properties, api_version=api_version)
    
    def delete_queue(self, namespace: str, queue_name: str, api_version: str = None):
        path = f"{self._build_namespace_path(namespace)}/queues/{queue_name}"
        return self._request("DELETE", path, api_version=api_version)
    
    # Topic operations
    def create_topic(self, namespace: str, topic_name: str, api_version: str = None) -> dict:
        path = f"{self._build_namespace_path(namespace)}/topics/{topic_name}"
        return self._request("PUT", path, {"properties": {}}, api_version=api_version)
    
    def delete_topic(self, namespace: str, topic_name: str, api_version: str = None):
        path = f"{self._build_namespace_path(namespace)}/topics/{topic_name}"
        return self._request("DELETE", path, api_version=api_version)
    
    # Subscription operations
    def create_subscription(
        self,
        namespace: str,
        topic_name: str,
        sub_name: str,
        requires_session: bool = False,
        lock_duration: str = "PT60S",
        api_version: str = None,
    ) -> dict:
        path = f"{self._build_namespace_path(namespace)}/topics/{topic_name}/subscriptions/{sub_name}"
        properties = {
            "properties": {
                "requiresSession": requires_session,
                "lockDuration": lock_duration,
            }
        }
        return self._request("PUT", path, properties, api_version=api_version)
    
    def delete_subscription(self, namespace: str, topic_name: str, sub_name: str, api_version: str = None):
        path = f"{self._build_namespace_path(namespace)}/topics/{topic_name}/subscriptions/{sub_name}"
        return self._request("DELETE", path, api_version=api_version)


# Singleton client instance
_direct_rest_client = None


def use_direct_rest_client() -> bool:
    """Check if direct REST client should be used instead of ARM."""
    return bool(
        SERVICEBUS_RP_HOST 
        and SERVICEBUS_RP_CERT_KEYVAULT_URI
        and AZURE_SUBSCRIPTION_ID
        and SERVICEBUS_RESOURCE_GROUP
    )


def get_direct_rest_client() -> ServiceBusDirectRestClient:
    """Get or create the direct REST client singleton."""
    global _direct_rest_client
    if _direct_rest_client is None:
        _direct_rest_client = ServiceBusDirectRestClient(
            rp_host=SERVICEBUS_RP_HOST,
            keyvault_cert_uri=SERVICEBUS_RP_CERT_KEYVAULT_URI,
            subscription_id=AZURE_SUBSCRIPTION_ID,
            resource_group=SERVICEBUS_RESOURCE_GROUP,
        )
    return _direct_rest_client
