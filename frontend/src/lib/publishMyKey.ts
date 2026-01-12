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
    // sig: (can add EIP-191/712 signature later)
  };

  const blob = new Blob([JSON.stringify(card)], { type: "application/json" });
  const file = new File([blob], "pubkey.json", { type: "application/json" });
  const out = await storeFile(file); // POST /storage/store (already exists)
  // storeFile returns { id_hex, cid, url } - take CID/URL
  return { cid: out.cid, url: out.url };
}
