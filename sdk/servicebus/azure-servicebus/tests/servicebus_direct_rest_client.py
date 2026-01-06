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

import os
from typing import Optional

from devtools_testutils import DirectRestClient


# Environment variable configuration
SERVICEBUS_RP_HOST = os.environ.get("SERVICEBUS_RP_HOST", None)
SERVICEBUS_RP_CERT_KEYVAULT_URI = os.environ.get("SERVICEBUS_RP_CERT_KEYVAULT_URI", None)
# Reuse existing env vars for subscription and resource group
AZURE_SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID", None)
SERVICEBUS_RESOURCE_GROUP = os.environ.get("SERVICEBUS_RESOURCE_GROUP", None)


class ServiceBusDirectRestClient(DirectRestClient):
    """Direct REST client for Service Bus management operations."""
    
    PROVIDER_NAMESPACE = "Microsoft.ServiceBus"
    
    def _build_namespace_path(self, namespace: str) -> str:
        """Build the ARM-style path prefix for a Service Bus namespace."""
        return (
            f"/subscriptions/{self.subscription_id}"
            f"/resourcegroups/{self.resource_group}"
            f"/providers/{self.PROVIDER_NAMESPACE}"
            f"/namespaces/{namespace}"
        )
    
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
        api_version: Optional[str] = None,
    ) -> dict:
        """Create a Service Bus queue."""
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
        return self.put(path, properties, api_version=api_version)
    
    def delete_queue(self, namespace: str, queue_name: str, api_version: Optional[str] = None) -> dict:
        """Delete a Service Bus queue."""
        path = f"{self._build_namespace_path(namespace)}/queues/{queue_name}"
        return self.delete(path, api_version=api_version)
    
    # Topic operations
    def create_topic(self, namespace: str, topic_name: str, api_version: Optional[str] = None) -> dict:
        """Create a Service Bus topic."""
        path = f"{self._build_namespace_path(namespace)}/topics/{topic_name}"
        return self.put(path, {"properties": {}}, api_version=api_version)
    
    def delete_topic(self, namespace: str, topic_name: str, api_version: Optional[str] = None) -> dict:
        """Delete a Service Bus topic."""
        path = f"{self._build_namespace_path(namespace)}/topics/{topic_name}"
        return self.delete(path, api_version=api_version)
    
    # Subscription operations
    def create_subscription(
        self,
        namespace: str,
        topic_name: str,
        sub_name: str,
        requires_session: bool = False,
        lock_duration: str = "PT60S",
        api_version: Optional[str] = None,
    ) -> dict:
        """Create a Service Bus subscription."""
        path = f"{self._build_namespace_path(namespace)}/topics/{topic_name}/subscriptions/{sub_name}"
        properties = {
            "properties": {
                "requiresSession": requires_session,
                "lockDuration": lock_duration,
            }
        }
        return self.put(path, properties, api_version=api_version)
    
    def delete_subscription(
        self,
        namespace: str,
        topic_name: str,
        sub_name: str,
        api_version: Optional[str] = None,
    ) -> dict:
        """Delete a Service Bus subscription."""
        path = f"{self._build_namespace_path(namespace)}/topics/{topic_name}/subscriptions/{sub_name}"
        return self.delete(path, api_version=api_version)


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
