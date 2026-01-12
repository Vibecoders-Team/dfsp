from eth_account import Account
from eth_account.messages import encode_typed_data

# --- Constants ---
DOMAIN_NAME = "DFSP-Login"
DOMAIN_VERSION = "1"


class EIP712Signer:
    """
    Class for creating EIP-712 signatures, SYNCHRONIZED with the server logic
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
        Signs the nonce using a typed_data structure identical to the server's.
        """
        typed_data = self._build_typed_data(nonce)

        # eth_account > 0.10.0 requires full_message to be a dict, which we have.
        # This function should now work identically to the server's _verify_login_signature
        signed_message = self.account.sign_message(encode_typed_data(full_message=typed_data))

        signature_hex = signed_message.signature.hex()
        return signature_hex, typed_data

    def sign_generic_typed_data(self, typed_data: dict) -> str:
        """
        Signs an arbitrary EIP-712 structure (typed_data).
        Used for meta-transactions.
        """
        # This logic is taken from the existing sign() method, but now
        # it works with any typed_data structure, not just for login.
        signed_message = self.account.sign_message(encode_typed_data(full_message=typed_data))
        return signed_message.signature.hex()

    def _build_typed_data(self, nonce_hex: str) -> dict:
        """
        Assembles the data structure for signing, exactly as on the server
        in the build_login_typed_data function.
        """
        return {
            # IMPORTANT: domain DOES NOT CONTAIN chainId, just like on the server
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
                # IMPORTANT: Unlike the eth-account default, the server
                # DOES NOT require EIP712Domain here, so we remove it
                # to make the structure identical.
            },
            "primaryType": "LoginChallenge",
            "message": {
                "address": self.address,
                "nonce": nonce_hex,
            },
        }
