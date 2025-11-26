"""EIP712 signer для тестов бота (копия из backend-test)."""

from eth_account import Account
from eth_account.messages import encode_typed_data

# --- Константы ---
DOMAIN_NAME = "DFSP-Login"
DOMAIN_VERSION = "1"


class EIP712Signer:
    """
    Класс для создания EIP-712 подписей, СИНХРОНИЗИРОВАННЫЙ с логикой
    сервера из app/routers/auth.py.
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
        Подписывает nonce, используя структуру typed_data, идентичную серверной.
        """
        typed_data = self._build_typed_data(nonce)

        # eth_account > 0.10.0 требует, чтобы full_message был dict, что у нас и есть.
        # Эта функция теперь должна работать идентично серверной _verify_login_signature
        signed_message = self.account.sign_message(encode_typed_data(full_message=typed_data))

        signature_hex = signed_message.signature.hex()
        return signature_hex, typed_data

    def sign_generic_typed_data(self, typed_data: dict) -> str:
        """
        Подписывает произвольную EIP-712 структуру (typed_data).
        Используется для мета-транзакций.
        """
        # Эта логика взята из существующего метода sign(), но теперь
        # она работает с любой структурой typed_data, а не только с логином.
        signed_message = self.account.sign_message(encode_typed_data(full_message=typed_data))
        return signed_message.signature.hex()

    def _build_typed_data(self, nonce_hex: str) -> dict:
        """
        Собирает структуру данных для подписи, в точности как на сервере
        в функции build_login_typed_data.
        """
        return {
            # ВАЖНО: domain НЕ СОДЕРЖИТ chainId, как и на сервере
            "domain": {
                "name": DOMAIN_NAME,
                "version": DOMAIN_VERSION,
            },
            # Types должны соответствовать Pydantic-модели и серверной логике
            "types": {
                "LoginChallenge": [
                    {"name": "address", "type": "address"},
                    {"name": "nonce", "type": "bytes32"},
                ],
                # ВАЖНО: В отличие от eth-account по умолчанию, сервер
                # НЕ требует здесь EIP712Domain, поэтому мы его убираем,
                # чтобы структура была идентичной.
            },
            "primaryType": "LoginChallenge",
            "message": {
                "address": self.address,
                "nonce": nonce_hex,
            },
        }
