/**
 * HMAC signing for navigation payloads (base64url). Uses a build-time secret from env:
 * VITE_MINI_NAV_HMAC_SECRET (hex or utf-8). Includes `ts` to avoid replay.
 */
const SECRET_RAW =
  (import.meta as unknown as { env?: Record<string, string | undefined> }).env?.VITE_MINI_NAV_HMAC_SECRET ?? "";

type InputPayload = Record<string, unknown>;
export type SignedPayload<T extends InputPayload = InputPayload> = { payload: T; ts: number; hmac: string };

export async function signNavigationPayload<T extends InputPayload>(payload: T): Promise<SignedPayload<T>> {
  const ts = Math.floor(Date.now() / 1000);
  const secret = await loadKey(SECRET_RAW);
  const body = JSON.stringify({ payload, ts });
  const mac = await crypto.subtle.sign("HMAC", secret, new TextEncoder().encode(body));
  return { payload, ts, hmac: toBase64Url(mac) };
}

async function loadKey(secret: string): Promise<CryptoKey> {
  if (!secret) throw new Error("VITE_MINI_NAV_HMAC_SECRET is not set");
  const bytes = hexToBytes(secret) ?? new TextEncoder().encode(secret);
  return crypto.subtle.importKey("raw", bytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
}

function hexToBytes(input: string): Uint8Array | null {
  const hex = input.trim();
  if (!/^([0-9a-fA-F]{2})+$/.test(hex)) return null;
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    out[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return out;
}

function toBase64Url(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
