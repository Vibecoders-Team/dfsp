"""EIP712 signer for bot tests (copy from backend-test)."""

from eth_account import Account
from eth_account.messages import encode_typed_data

# --- Constants ---
DOMAIN_NAME = "DFSP-Login"
DOMAIN_VERSION = "1"


class EIP712Signer:
    """
    Class for creating EIP-712 signatures, KEPT IN SYNC with the server logic
    from app/routers/auth.py.
    """

    def __init__(self, private_key: str):
        if not (isinstance(private_key, str) and private_key.startswith("0x") and len(private_key) == 66):
            raise ValueError("Private key must be a 0x-prefixed 66-char hex string")
        self.account = Account.from_key(private_key)

    @property
    def address(self) -> str:
        return self.account.address

    def sign(self, nonce: str) -> tuple[str, dict]:
        """
        Signs the nonce using typed_data structure identical to the server one.
        """
        typed_data = self._build_typed_data(nonce)

        # eth_account > 0.10.0 requires full_message to be a dict, which we already have.
        # This function must now behave identically to the server _verify_login_signature
        signed_message = self.account.sign_message(encode_typed_data(full_message=typed_data))

        signature_hex = signed_message.signature.hex()
        return signature_hex, typed_data

    def sign_generic_typed_data(self, typed_data: dict) -> str:
        """
        Signs an arbitrary EIP-712 structure (typed_data).
        Used for meta-transactions.
        """
        # This logic is taken from the existing sign() method, but now
        # it works with any typed_data structure, not just login.
        signed_message = self.account.sign_message(encode_typed_data(full_message=typed_data))
        return signed_message.signature.hex()

    def _build_typed_data(self, nonce_hex: str) -> dict:
        """
        Builds the data structure for signing, exactly as on the server
        in the build_login_typed_data function.
        """
        return {
            # IMPORTANT: domain does NOT contain chainId, same as on the server
            "domain": {
                "name": DOMAIN_NAME,
                "version": DOMAIN_VERSION,
            },
            # Types must match the Pydantic model and server logic
            "types": {
                "LoginChallenge": [
                    {"name": "address", "type": "address"},
                    {"name": "nonce", "type": "bytes32"},
                ],
                # IMPORTANT: Unlike eth-account defaults, the server
                # does NOT require EIP712Domain here, so we remove it
                # to keep the structure identical.
            },
            "primaryType": "LoginChallenge",
            "message": {
                "address": self.address,
                "nonce": nonce_hex,
            },
        }
