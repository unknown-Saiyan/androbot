import pytest

from cdp.openapi_client.models.evm_account import EvmAccount as EvmServerAccountModel


@pytest.fixture
def server_account_model_factory():
    """Create and return a factory for WalletModel fixtures."""

    def _create_server_account_model(
        address="0x1234567890123456789012345678901234567890",
        name="test-server-account",
    ):
        return EvmServerAccountModel(address=address, name=name)

    return _create_server_account_model
