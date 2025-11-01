type MsgOut = { nonce: string };

function hexOf(bytes: Uint8Array): string {
  let s = "";
  for (let i = 0; i < bytes.length; i++) {
    const b = bytes[i].toString(16).padStart(2, "0");
    s += b;
  }
  return s;
}

async function sha256(bytes: Uint8Array): Promise<Uint8Array> {
  const ab = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const buf = await crypto.subtle.digest("SHA-256", ab);
  return new Uint8Array(buf);
}

self.onmessage = async (e: MessageEvent<MsgIn>) => {
  const { challenge, difficulty, start = 0, step = 1 } = e.data;
  const enc = new TextEncoder();

  // required hex zero prefix length aligns with backend: ceil(difficulty/4)
  const zeroHexLen = Math.floor((difficulty + 3) / 4);
  const prefix = "0".repeat(Math.max(1, zeroHexLen));

  let nonce = start;
  const BATCH = 2000;

  for (;;) {
    for (let i = 0; i < BATCH; i++) {
      const input = enc.encode(challenge + String(nonce));
      const hBytes = await sha256(input);
      const hHex = hexOf(hBytes);
      if (hHex.startsWith(prefix)) {
        const out: MsgOut = { nonce: String(nonce) };
        (self as unknown as Worker).postMessage(out);
        return;
      }
      nonce += step;
    }
    await new Promise((r) => setTimeout(r, 0));
  }
};

