import io, requests
from typing import Tuple

class IpfsClient:
    def __init__(self, api_url: str, gateway_url: str | None = None, public_gateway_url: str | None = None):
        self.api = api_url.rstrip("/")
        self.gateway_internal = (gateway_url or self.api).rstrip("/")
        self.gateway_public = (public_gateway_url or self.gateway_internal).rstrip("/")

    def add_bytes(self, data: bytes, filename: str = "blob") -> str:
        files = {'file': (filename, io.BytesIO(data))}
        r = requests.post(f"{self.api}/api/v0/add", files=files, params={"pin":"true"})
        r.raise_for_status()
        return r.json()["Hash"]  # CID

    def cat(self, cid: str) -> bytes:
        r = requests.post(f"{self.api}/api/v0/cat", params={"arg": cid}, stream=True)
        r.raise_for_status()
        return r.content

    def url(self, cid: str) -> str:
        return f"{self.gateway_public}/ipfs/{cid}"

