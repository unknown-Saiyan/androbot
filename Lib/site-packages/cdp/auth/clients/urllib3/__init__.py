"""Request hooks for different HTTP clients."""

from .client import Urllib3AuthClient, Urllib3AuthClientOptions

__all__ = ["Urllib3AuthClient", "Urllib3AuthClientOptions"]
