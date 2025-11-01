// src/lib/publishMyKey.ts
import { ensureEOA, ensureRSA } from "./keychain";
import { storeFile } from "./api";

export type PublishOut = { cid: string; url?: string };

export async function publishMyKeyCard(): Promise<PublishOut> {
  const { address } = await ensureEOA();
  const { publicPem } = await ensureRSA();

  const card = {
    type: "dfsp-rsa-pubkey",
    version: 1 as const,
    address,
    rsa_public: publicPem,
    ts: Date.now(),
    // sig: (можно добавить позже подпись EIP-191/712)
  };

  const blob = new Blob([JSON.stringify(card)], { type: "application/json" });
  const file = new File([blob], "pubkey.json", { type: "application/json" });
  const out = await storeFile(file); // POST /storage/store (already exists)
  // storeFile возвращает { id_hex, cid, url } — забираем CID/URL
  return { cid: out.cid, url: out.url };
}

