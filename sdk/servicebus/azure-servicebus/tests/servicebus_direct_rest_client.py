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
"""

import os
import json
import base64
import ssl
import tempfile
import logging
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError


# Environment variable configuration
SERVICEBUS_RP_HOST = os.environ.get("SERVICEBUS_RP_HOST", None)
SERVICEBUS_RP_CERT_KEYVAULT_URI = os.environ.get("SERVICEBUS_RP_CERT_KEYVAULT_URI", None)


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


def _create_ssl_context_from_pfx(pfx_bytes: bytes, password: Optional[str] = None) -> ssl.SSLContext:
    """
    Create an SSL context from PFX bytes using the cryptography library.
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
    
    # Write to temporary files (SSL context needs file paths)
    cert_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False)
    key_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False)
    
    try:
        cert_file.write(cert_pem)
        cert_file.close()
        
        key_file.write(key_pem)
        key_file.close()
        
        context = ssl.create_default_context()
        context.load_cert_chain(certfile=cert_file.name, keyfile=key_file.name)
        
        # For internal endpoints, may need to disable hostname verification
        # Uncomment these lines if certificate validation fails:
        # context.check_hostname = False
        # context.verify_mode = ssl.CERT_NONE
        
        return context
    finally:
        # Clean up temp files
        try:
            os.unlink(cert_file.name)
            os.unlink(key_file.name)
        except Exception:
            pass


class ServiceBusDirectRestClient:
    """Direct REST client for Service Bus management operations using certificate auth from Key Vault."""
    
    def __init__(self, rp_host: str, keyvault_cert_uri: str):
        # rp_host is hostname:port without scheme, e.g. "swedencentral02.int.messaging.azure-int.net:44400"
        self.base_url = f"https://{rp_host}".rstrip("/")
        self._ssl_context = None
        self._keyvault_cert_uri = keyvault_cert_uri
    
    def _get_ssl_context(self):
        """Lazy-load SSL context with certificate from Key Vault."""
        if self._ssl_context is None:
            logging.info(f"Fetching certificate from Key Vault: {self._keyvault_cert_uri}")
            pfx_bytes = _get_keyvault_certificate_as_pfx(self._keyvault_cert_uri)
            self._ssl_context = _create_ssl_context_from_pfx(pfx_bytes)
            logging.info("Certificate loaded successfully")
        return self._ssl_context
    
    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        """Make an HTTP request with certificate authentication."""
        url = f"{self.base_url}{path}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        data = json.dumps(body).encode("utf-8") if body else None
        req = Request(url, data=data, headers=headers, method=method)
        
        logging.debug(f"Direct REST {method} {url}")
        
        try:
            with urlopen(req, context=self._get_ssl_context()) as response:
                if response.status in (200, 201, 202, 204):
                    content_length = response.headers.get("Content-Length", "0")
                    if content_length != "0":
                        return json.loads(response.read().decode("utf-8"))
                    return {}
                raise Exception(f"Unexpected status {response.status}")
        except HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            raise Exception(f"HTTP {e.code}: {e.reason} - {error_body}")
    
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
    ) -> dict:
        path = f"/{namespace}/queues/{queue_name}"
        properties = {
            "lockDuration": lock_duration,
            "requiresDuplicateDetection": requires_duplicate_detection,
            "deadLetteringOnMessageExpiration": dead_lettering_on_message_expiration,
            "requiresSession": requires_session,
            "enablePartitioning": enable_partitioning,
        }
        return self._request("PUT", path, properties)
    
    def delete_queue(self, namespace: str, queue_name: str):
        path = f"/{namespace}/queues/{queue_name}"
        return self._request("DELETE", path)
    
    # Topic operations
    def create_topic(self, namespace: str, topic_name: str) -> dict:
        path = f"/{namespace}/topics/{topic_name}"
        return self._request("PUT", path, {})
    
    def delete_topic(self, namespace: str, topic_name: str):
        path = f"/{namespace}/topics/{topic_name}"
        return self._request("DELETE", path)
    
    # Subscription operations
    def create_subscription(
        self,
        namespace: str,
        topic_name: str,
        sub_name: str,
        requires_session: bool = False,
        lock_duration: str = "PT60S",
    ) -> dict:
        path = f"/{namespace}/topics/{topic_name}/subscriptions/{sub_name}"
        properties = {
            "requiresSession": requires_session,
            "lockDuration": lock_duration,
        }
        return self._request("PUT", path, properties)
    
    def delete_subscription(self, namespace: str, topic_name: str, sub_name: str):
        path = f"/{namespace}/topics/{topic_name}/subscriptions/{sub_name}"
        return self._request("DELETE", path)


# Singleton client instance
_direct_rest_client = None


def use_direct_rest_client() -> bool:
    """Check if direct REST client should be used instead of ARM."""
    return bool(SERVICEBUS_RP_HOST and SERVICEBUS_RP_CERT_KEYVAULT_URI)


def get_direct_rest_client() -> ServiceBusDirectRestClient:
    """Get or create the direct REST client singleton."""
    global _direct_rest_client
    if _direct_rest_client is None:
        _direct_rest_client = ServiceBusDirectRestClient(
            rp_host=SERVICEBUS_RP_HOST,
            keyvault_cert_uri=SERVICEBUS_RP_CERT_KEYVAULT_URI
        )
    return _direct_rest_client
