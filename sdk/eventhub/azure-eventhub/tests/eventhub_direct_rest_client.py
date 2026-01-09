"""
Direct REST client for Event Hubs management operations.

This module provides a client that bypasses Azure Resource Manager (ARM) and
communicates directly with internal Event Hubs endpoints using certificate
authentication from Azure Key Vault.

Usage:
    Set these environment variables:
    - EVENTHUB_RP_HOST: hostname:port without scheme
      Example: "swedencentral02.int.eventhubs.azure-int.net:44400"
    - EVENTHUB_RP_CERT_KEYVAULT_URI: Key Vault certificate URI
      Example: "https://myvault.vault.azure.net/certificates/MyCert"
    
    Also requires (already used by other test infrastructure):
    - AZURE_SUBSCRIPTION_ID: Azure subscription ID
    - EVENTHUB_RESOURCE_GROUP: Resource group name
"""

import os
from typing import Optional

from devtools_testutils import DirectRestClient


# Environment variable configuration
EVENTHUB_RP_HOST = os.environ.get("EVENTHUB_RP_HOST", None)
EVENTHUB_RP_CERT_KEYVAULT_URI = os.environ.get("EVENTHUB_RP_CERT_KEYVAULT_URI", None)
# Reuse existing env vars for subscription and resource group
AZURE_SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID", None)
EVENTHUB_RESOURCE_GROUP = os.environ.get("EVENTHUB_RESOURCE_GROUP", None)


class EventHubDirectRestClient(DirectRestClient):
    """Direct REST client for Event Hubs management operations."""
    
    PROVIDER_NAMESPACE = "Microsoft.EventHub"
    
    def _build_namespace_path(self, namespace: str) -> str:
        """Build the ARM-style path prefix for an Event Hubs namespace."""
        return (
            f"/subscriptions/{self.subscription_id}"
            f"/resourcegroups/{self.resource_group}"
            f"/providers/{self.PROVIDER_NAMESPACE}"
            f"/namespaces/{namespace}"
        )
    
    # Event Hub operations
    def create_event_hub(
        self,
        namespace: str,
        event_hub_name: str,
        partition_count: int = 4,
        message_retention_in_days: int = 1,
        api_version: Optional[str] = None,
    ) -> dict:
        """Create an Event Hub."""
        path = f"{self._build_namespace_path(namespace)}/eventhubs/{event_hub_name}"
        properties = {
            "properties": {
                "partitionCount": partition_count,
                "messageRetentionInDays": message_retention_in_days,
            }
        }
        return self.put(path, properties, api_version=api_version)
    
    def get_event_hub(
        self,
        namespace: str,
        event_hub_name: str,
        api_version: Optional[str] = None,
    ) -> dict:
        """Get an Event Hub."""
        path = f"{self._build_namespace_path(namespace)}/eventhubs/{event_hub_name}"
        return self.get(path, api_version=api_version)
    
    def delete_event_hub(
        self,
        namespace: str,
        event_hub_name: str,
        api_version: Optional[str] = None,
    ) -> dict:
        """Delete an Event Hub."""
        path = f"{self._build_namespace_path(namespace)}/eventhubs/{event_hub_name}"
        return self.delete(path, api_version=api_version)
    
    def list_event_hubs(
        self,
        namespace: str,
        api_version: Optional[str] = None,
    ) -> dict:
        """List all Event Hubs in a namespace."""
        path = f"{self._build_namespace_path(namespace)}/eventhubs"
        return self.get(path, api_version=api_version)
    
    # Consumer Group operations
    def create_consumer_group(
        self,
        namespace: str,
        event_hub_name: str,
        consumer_group_name: str,
        user_metadata: Optional[str] = None,
        api_version: Optional[str] = None,
    ) -> dict:
        """Create a consumer group."""
        path = (
            f"{self._build_namespace_path(namespace)}"
            f"/eventhubs/{event_hub_name}"
            f"/consumergroups/{consumer_group_name}"
        )
        properties = {"properties": {}}
        if user_metadata:
            properties["properties"]["userMetadata"] = user_metadata
        return self.put(path, properties, api_version=api_version)
    
    def get_consumer_group(
        self,
        namespace: str,
        event_hub_name: str,
        consumer_group_name: str,
        api_version: Optional[str] = None,
    ) -> dict:
        """Get a consumer group."""
        path = (
            f"{self._build_namespace_path(namespace)}"
            f"/eventhubs/{event_hub_name}"
            f"/consumergroups/{consumer_group_name}"
        )
        return self.get(path, api_version=api_version)
    
    def delete_consumer_group(
        self,
        namespace: str,
        event_hub_name: str,
        consumer_group_name: str,
        api_version: Optional[str] = None,
    ) -> dict:
        """Delete a consumer group."""
        path = (
            f"{self._build_namespace_path(namespace)}"
            f"/eventhubs/{event_hub_name}"
            f"/consumergroups/{consumer_group_name}"
        )
        return self.delete(path, api_version=api_version)
    
    def list_consumer_groups(
        self,
        namespace: str,
        event_hub_name: str,
        api_version: Optional[str] = None,
    ) -> dict:
        """List all consumer groups for an Event Hub."""
        path = (
            f"{self._build_namespace_path(namespace)}"
            f"/eventhubs/{event_hub_name}"
            f"/consumergroups"
        )
        return self.get(path, api_version=api_version)

    # Authorization Rule / Key operations
    def list_keys(
        self,
        namespace: str,
        authorization_rule_name: str = "RootManageSharedAccessKey",
        api_version: Optional[str] = None,
    ) -> dict:
        """List keys for a namespace authorization rule."""
        path = (
            f"{self._build_namespace_path(namespace)}"
            f"/authorizationRules/{authorization_rule_name}/listKeys"
        )
        return self.post(path, body=None, api_version=api_version)


# Singleton client instance
_direct_rest_client = None


def use_direct_rest_client() -> bool:
    """Check if direct REST client should be used instead of ARM."""
    return bool(
        EVENTHUB_RP_HOST 
        and EVENTHUB_RP_CERT_KEYVAULT_URI
        and AZURE_SUBSCRIPTION_ID
        and EVENTHUB_RESOURCE_GROUP
    )


def get_direct_rest_client() -> EventHubDirectRestClient:
    """Get or create the direct REST client singleton."""
    global _direct_rest_client
    if _direct_rest_client is None:
        _direct_rest_client = EventHubDirectRestClient(
            rp_host=EVENTHUB_RP_HOST,
            keyvault_cert_uri=EVENTHUB_RP_CERT_KEYVAULT_URI,
            subscription_id=AZURE_SUBSCRIPTION_ID,
            resource_group=EVENTHUB_RESOURCE_GROUP,
        )
    return _direct_rest_client
