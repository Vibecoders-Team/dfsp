/// <reference lib="webworker" />
// src/workers/pow.worker.ts

type MsgIn = { challenge: string; difficulty: number };
type MsgOut = { nonce: string };

function hasLeadingZeroBits(hash: Uint8Array, bits: number): boolean {
  const full = Math.floor(bits / 8);
  const rem = bits % 8;
  for (let i = 0; i < full; i++) if (hash[i] !== 0) return false;
  if (rem === 0) return true;
  const mask = 0xff << (8 - rem);
  return (hash[full] & mask) === 0;
}

async function sha256(bytes: Uint8Array): Promise<Uint8Array> {
  const buf = await crypto.subtle.digest("SHA-256", bytes);
  return new Uint8Array(buf);
}

self.onmessage = async (e: MessageEvent<MsgIn>) => {
  const { challenge, difficulty } = e.data;
  const enc = new TextEncoder();

  // Простой брутфорс с батчами (снижает блокировку event loop)
  let nonce = 0;
  const BATCH = 500; // маленькие батчи дают ~50–150 мс в среднем на diff 18–22
  // При необходимости можно рандомизировать старт: nonce = Math.floor(Math.random()*1e7);

  for (;;) {
    for (let i = 0; i < BATCH; i++) {
      const input = enc.encode(challenge + ":" + nonce);
      const h = await sha256(input);
      if (hasLeadingZeroBits(h, difficulty)) {
        const out: MsgOut = { nonce: String(nonce) };
        (self as unknown as Worker).postMessage(out);
        return;
      }
      nonce++;
    }
    // отдаём управление, чтобы не зависал воркер при длинных батчах
    await new Promise(r => setTimeout(r, 0));
  }
};
