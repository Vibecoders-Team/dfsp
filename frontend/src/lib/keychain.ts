import { Wallet } from "ethers";

/** EIP-712 логин: домен/типы должны строго совпадать с бэкендом */
export const LOGIN_DOMAIN = { name: "DFSP-Login", version: "1" } as const;
export const LOGIN_TYPES = {
  LoginChallenge: [
    { name: "address", type: "address" },
    { name: "nonce",   type: "bytes32" },
  ],
} as const;

const DB_NAME = "dfsp";
const STORE = "kv";

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function idbGet<T = any>(key: string): Promise<T | undefined> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const st = tx.objectStore(STORE);
    const rq = st.get(key);
    rq.onsuccess = () => resolve(rq.result as T);
    rq.onerror = () => reject(rq.error);
  });
}
async function idbSet(key: string, val: any) {
  const db = await openDB();
  return new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    const st = tx.objectStore(STORE);
    st.put(val, key);
  });
}

/** ---------- EOA (secp256k1) ---------- */

const KEY_EOA_PRIV = "eoaPrivHex";

export async function hasEOA(): Promise<boolean> {
  return !!(await idbGet(KEY_EOA_PRIV));
}
export async function ensureEOA(): Promise<Wallet> {
  const existing = await idbGet<string>(KEY_EOA_PRIV);
  if (existing && /^0x[0-9a-fA-F]{64}$/.test(existing)) {
    return new Wallet(existing);
  }
  const w = Wallet.createRandom();
  await idbSet(KEY_EOA_PRIV, w.privateKey);
  return w;
}
export async function getEOA(): Promise<Wallet | null> {
  const existing = await idbGet<string>(KEY_EOA_PRIV);
  return existing ? new Wallet(existing) : null;
}

/** ---------- RSA ---------- */

const KEY_RSA_PRIV_PKCS8 = "rsaPrivPkcs8"; // ArrayBuffer
const KEY_RSA_PUB_PEM = "rsaPubPem";       // string

function ab2b64(ab: ArrayBuffer): string {
  const u8 = new Uint8Array(ab);
  let s = ""; for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]);
  return btoa(s);
}
function b64toAb(b64: string): ArrayBuffer {
  const bin = atob(b64);
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return u8.buffer;
}

export async function hasRSA(): Promise<boolean> {
  return !!(await idbGet(KEY_RSA_PRIV_PKCS8));
}

export async function ensureRSA(): Promise<{ privateKey: CryptoKey; publicPem: string }> {
  // есть?
  const existing = await idbGet<ArrayBuffer>(KEY_RSA_PRIV_PKCS8);
  if (existing) {
    const priv = await crypto.subtle.importKey(
      "pkcs8", existing,
      { name: "RSA-PSS", hash: "SHA-256" },
      true, ["sign"]
    );
    const pubPem = (await idbGet<string>(KEY_RSA_PUB_PEM)) || (await exportRsaPublicPemFromPrivate(priv));
    if (!await idbGet<string>(KEY_RSA_PUB_PEM)) await idbSet(KEY_RSA_PUB_PEM, pubPem);
    return { privateKey: priv, publicPem: pubPem };
  }
  // генерим
  const pair = await crypto.subtle.generateKey(
    { name: "RSA-PSS", modulusLength: 2048, publicExponent: new Uint8Array([1,0,1]), hash: "SHA-256" },
    true, ["sign","verify"]
  );
  const pkcs8 = await crypto.subtle.exportKey("pkcs8", pair.privateKey);
  const pubPem = await exportRsaPublicPem(pair.publicKey);
  await idbSet(KEY_RSA_PRIV_PKCS8, pkcs8);
  await idbSet(KEY_RSA_PUB_PEM, pubPem);
  return { privateKey: pair.privateKey, publicPem: pubPem };
}

async function exportRsaPublicPemFromPrivate(priv: CryptoKey): Promise<string> {
  const jwk = await crypto.subtle.exportKey("jwk", priv);
  // Восстановим публичный ключ из jwk (n,e)
  const pub = await crypto.subtle.importKey(
    "jwk",
    { kty: "RSA", n: (jwk as any).n, e: (jwk as any).e, alg: "PS256", ext: true },
    { name: "RSA-PSS", hash: "SHA-256" },
    true, ["verify"]
  );
  return exportRsaPublicPem(pub);
}
async function exportRsaPublicPem(pub: CryptoKey): Promise<string> {
  const spki = await crypto.subtle.exportKey("spki", pub);
  const b64 = ab2b64(spki).match(/.{1,64}/g)!.join("\n");
  return `-----BEGIN PUBLIC KEY-----\n${b64}\n-----END PUBLIC KEY-----\n`;
}

/** ---------- Backup/Restore (.dfspkey) ---------- */

type BackupPayload = {
  version: 1;
  eoaPrivHex: string;       // 0x + 64
  rsaPrivPkcs8_b64: string; // base64
  createdAt: number;
};

export async function createBackupBlob(password: string): Promise<Blob> {
  const eoa = await idbGet<string>(KEY_EOA_PRIV);
  const rsaPkcs8 = await idbGet<ArrayBuffer>(KEY_RSA_PRIV_PKCS8);
  if (!eoa || !rsaPkcs8) throw new Error("Keys not found");
  const payload: BackupPayload = {
    version: 1,
    eoaPrivHex: eoa,
    rsaPrivPkcs8_b64: ab2b64(rsaPkcs8),
    createdAt: Math.floor(Date.now()/1000),
  };
  const enc = new TextEncoder();
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const keyMaterial = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveKey"]);
  const aesKey = await crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations: 200_000, hash: "SHA-256" },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    true, ["encrypt","decrypt"]
  );
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, aesKey, enc.encode(JSON.stringify(payload)));
  const out = {
    version: 1,
    kdf: { name: "PBKDF2", iterations: 200000, hash: "SHA-256", salt_b64: ab2b64(salt.buffer) },
    cipher: { name: "AES-GCM", iv_b64: ab2b64(iv.buffer), data_b64: ab2b64(ct) },
  };
  const blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
  return blob;
}

export async function restoreFromBackup(file: File, password: string): Promise<{ address: string }> {
  const txt = await file.text();
  const j = JSON.parse(txt);
  if (j?.version !== 1) throw new Error("Unsupported backup version");

  const enc = new TextEncoder();
  const salt = b64toAb(j.kdf?.salt_b64);
  const iv = b64toAb(j.cipher?.iv_b64);
  const data = b64toAb(j.cipher?.data_b64);

  const keyMaterial = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveKey"]);
  const aesKey = await crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations: j.kdf?.iterations ?? 200000, hash: "SHA-256" },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    true, ["decrypt"]
  );
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, aesKey, data);
  const payload = JSON.parse(new TextDecoder().decode(plain)) as BackupPayload;
  if (!/^0x[0-9a-fA-F]{64}$/.test(payload.eoaPrivHex)) throw new Error("Invalid EOA in backup");

  await idbSet(KEY_EOA_PRIV, payload.eoaPrivHex);
  await idbSet(KEY_RSA_PRIV_PKCS8, b64toAb(payload.rsaPrivPkcs8_b64));
  // восстановим и сохраним pub pem
  const priv = await crypto.subtle.importKey(
    "pkcs8", b64toAb(payload.rsaPrivPkcs8_b64),
    { name: "RSA-PSS", hash: "SHA-256" },
    true, ["sign"]
  );
  const pubPem = await exportRsaPublicPemFromPrivate(priv);
  await idbSet(KEY_RSA_PUB_PEM, pubPem);

  const addr = new Wallet(payload.eoaPrivHex).address;
  return { address: addr };
}


export type LoginMessage = { address: string; nonce: `0x${string}` };

// ensureEOA() должен вернуть ethers.Wallet из твоего локального приватника,
// и НИКОГДА не генерировать новый, если уже есть!
export async function signLoginTyped(message: LoginMessage) {
  const wallet = await ensureEOA(); // должен вернуть СУЩЕСТВУЮЩИЙ, а не сгенерить новый
  return wallet.signTypedData(LOGIN_DOMAIN, LOGIN_TYPES, message); // EIP-712
}