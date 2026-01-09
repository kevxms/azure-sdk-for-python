# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
# --------------------------------------------------------------------------
"""
Base class for direct REST clients that bypass Azure Resource Manager (ARM).

This module provides a base client for communicating directly with internal
Azure service endpoints using certificate authentication from Azure Key Vault.

Subclasses should implement service-specific operations (e.g., create_queue for
Service Bus, create_event_hub for Event Hubs).
"""

import atexit
import os
import base64
import tempfile
import logging
import urllib3
from typing import Optional, Tuple, List

import requests

# Suppress InsecureRequestWarning for internal endpoints
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Module-level temp file tracking for cleanup
_temp_files_to_cleanup: List[str] = []


def _cleanup_temp_files():
    """Clean up any temporary certificate files at exit."""
    for path in _temp_files_to_cleanup:
        try:
            os.unlink(path)
        except Exception:
            pass


atexit.register(_cleanup_temp_files)


def get_keyvault_certificate_as_pfx(cert_url: str) -> bytes:
    """
    Fetch certificate (with private key) from Key Vault using Azure CLI authentication.
    
    Args:
        cert_url: Key Vault certificate URL, e.g., 
                  "https://myvault.vault.azure.net/certificates/MyCert"
                  or with version: ".../MyCert/1166c0beea1e47b9905dbe791a320bb0"
    
    Returns:
        PFX bytes containing the certificate and private key.
    
    Raises:
        ValueError: If the certificate URL is invalid.
    """
    from azure.identity import AzureCliCredential
    from azure.keyvault.secrets import SecretClient
    
    # Parse the cert URL to extract vault URL and cert name
    # URL format: https://<vault-name>.vault.azure.net/certificates/<cert-name>[/<version>]
    parts = cert_url.rstrip("/").split("/")
    
    try:
        cert_idx = parts.index("certificates")
    except ValueError:
        raise ValueError(f"Invalid Key Vault certificate URL: {cert_url}")
    
    vault_url = "/".join(parts[:cert_idx])
    cert_name = parts[cert_idx + 1] if len(parts) > cert_idx + 1 else None
    cert_version = parts[cert_idx + 2] if len(parts) > cert_idx + 2 else None
    
    if not cert_name:
        raise ValueError(f"Certificate name not found in URL: {cert_url}")
    
    credential = AzureCliCredential()
    
    # To get the private key, fetch the certificate as a secret
    # Key Vault stores the full PFX (cert + private key) as a secret with the same name
    secret_client = SecretClient(vault_url=vault_url, credential=credential)
    
    if cert_version:
        secret = secret_client.get_secret(cert_name, cert_version)
    else:
        secret = secret_client.get_secret(cert_name)
    
    # The secret value is base64-encoded PFX
    pfx_bytes = base64.b64decode(secret.value)
    return pfx_bytes


def create_cert_files_from_pfx(pfx_bytes: bytes, password: Optional[str] = None) -> Tuple[str, str]:
    """
    Extract certificate and key from PFX bytes and write to temporary PEM files.
    
    Args:
        pfx_bytes: The PFX certificate bytes.
        password: Optional password for the PFX file.
    
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


class DirectRestClient:
    """
    Base class for direct REST clients using certificate authentication from Key Vault.
    
    This client bypasses Azure Resource Manager (ARM) and communicates directly with
    internal Azure service endpoints. Subclasses should implement service-specific
    operations.
    
    Args:
        rp_host: The resource provider host (hostname:port without scheme),
                 e.g., "swedencentral02.int.messaging.azure-int.net:44400"
        keyvault_cert_uri: Key Vault certificate URI for authentication,
                           e.g., "https://myvault.vault.azure.net/certificates/MyCert"
        subscription_id: Azure subscription ID.
        resource_group: Azure resource group name.
    """
    
    DEFAULT_API_VERSION = "2017-04-01"
    PROVIDER_NAMESPACE = "Microsoft.Resources"  # Override in subclasses
    
    def __init__(
        self,
        rp_host: str,
        keyvault_cert_uri: str,
        subscription_id: str,
        resource_group: str,
    ):
        self.base_url = f"https://{rp_host}".rstrip("/")
        self._cert_tuple: Optional[Tuple[str, str]] = None
        self._keyvault_cert_uri = keyvault_cert_uri
        self._session = requests.Session()
        self.subscription_id = subscription_id
        self.resource_group = resource_group
    
    def _get_cert_tuple(self) -> Tuple[str, str]:
        """Lazy-load certificate files from Key Vault."""
        if self._cert_tuple is None:
            logging.info(f"Fetching certificate from Key Vault: {self._keyvault_cert_uri}")
            pfx_bytes = get_keyvault_certificate_as_pfx(self._keyvault_cert_uri)
            self._cert_tuple = create_cert_files_from_pfx(pfx_bytes)
            logging.info(f"Certificate loaded successfully: {self._cert_tuple}")
        return self._cert_tuple
    
    def _build_resource_path(self, resource_name: str) -> str:
        """
        Build the ARM-style path prefix for a resource.
        
        Override this in subclasses for service-specific path building.
        
        Args:
            resource_name: The name of the resource (e.g., namespace name).
        
        Returns:
            The ARM-style resource path.
        """
        return (
            f"/subscriptions/{self.subscription_id}"
            f"/resourcegroups/{self.resource_group}"
            f"/providers/{self.PROVIDER_NAMESPACE}"
        )
    
    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        api_version: Optional[str] = None,
        verify_ssl: bool = False,
    ) -> dict:
        """
        Make an HTTP request with certificate authentication.
        
        Args:
            method: HTTP method (GET, PUT, POST, DELETE, etc.).
            path: Request path (will be appended to base_url).
            body: Optional request body (will be JSON-encoded).
            api_version: API version to use (defaults to DEFAULT_API_VERSION).
            verify_ssl: Whether to verify SSL certificates (default False for internal endpoints).
        
        Returns:
            Response body as a dictionary, or empty dict for 204 responses.
        
        Raises:
            requests.HTTPError: If the response status code indicates an error.
        """
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
            verify=verify_ssl,
        )
        
        logging.info(f"Direct REST response: {response.status_code}")
        
        if response.status_code in (200, 201, 202, 204):
            if response.text:
                return response.json()
            return {}
        
        response.raise_for_status()
        return {}  # Should not reach here
    
    def get(self, path: str, api_version: Optional[str] = None) -> dict:
        """Perform a GET request."""
        return self._request("GET", path, api_version=api_version)
    
    def put(self, path: str, body: Optional[dict] = None, api_version: Optional[str] = None) -> dict:
        """Perform a PUT request."""
        return self._request("PUT", path, body=body, api_version=api_version)
    
    def post(self, path: str, body: Optional[dict] = None, api_version: Optional[str] = None) -> dict:
        """Perform a POST request."""
        return self._request("POST", path, body=body, api_version=api_version)
    
    def delete(self, path: str, api_version: Optional[str] = None) -> dict:
        """Perform a DELETE request."""
        return self._request("DELETE", path, api_version=api_version)
    
    def patch(self, path: str, body: Optional[dict] = None, api_version: Optional[str] = None) -> dict:
        """Perform a PATCH request."""
        return self._request("PATCH", path, body=body, api_version=api_version)
