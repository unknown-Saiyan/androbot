"""HTTP client implementations for CDP authentication.

This module exports concrete HTTP client implementations for making authenticated
requests to CDP services.
"""

from cdp.auth.clients.urllib3.client import Urllib3AuthClient, Urllib3AuthClientOptions

__all__ = [
    "Urllib3AuthClient",
    "Urllib3AuthClientOptions",
]
