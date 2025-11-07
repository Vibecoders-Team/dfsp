// src/lib/importKeyCard.ts
import { saveKey } from "./pubkeys";

const IPFS = import.meta.env.VITE_IPFS_PUBLIC_GATEWAY ?? "http://localhost:8080";

type KeyCardV1 = {
  type: "dfsp-rsa-pubkey";
  version: 1;
  address: string;
  rsa_public: string;
  ts?: number;
  sig?: string; // на будущее, можно добавить проверку подписи
};

function normalizeCidOrUrl(input: string): string {
  const v = input.trim();
  if (v.startsWith("http://") || v.startsWith("https://")) return v;
  // допускаем только CID → собираем URL вида {gateway}/ipfs/{cid}
  return `${IPFS.replace(/\/+$/,"")}/ipfs/${v}`;
}

export async function importKeyFromCid(cidOrUrl: string): Promise<{ address: string }> {
  const url = normalizeCidOrUrl(cidOrUrl);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch key card (${res.status})`);
  const card = (await res.json()) as Partial<KeyCardV1>;

  if (card.type !== "dfsp-rsa-pubkey" || card.version !== 1) {
    throw new Error("Unsupported key card format");
  }
  const address = String(card.address || "");
  const pem = String(card.rsa_public || "");
  if (!/^0x[0-9a-fA-F]{40}$/.test(address)) throw new Error("Bad address in key card");
  if (!pem.includes("BEGIN PUBLIC KEY")) throw new Error("Bad PEM in key card");

  // TODO (позже): проверить подпись card.sig
  saveKey(address, pem);
  return { address };
}

