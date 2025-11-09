/* eslint-disable @typescript-eslint/no-explicit-any */
import { Wallet, type TypedDataDomain, type TypedDataField } from "ethers";

// ---- EIP712 Login Domain ----
export const LOGIN_DOMAIN: TypedDataDomain = { name: "DFSP-Login", version: "1" };
export const LOGIN_TYPES: Record<string, TypedDataField[]> = {
  LoginChallenge: [
    { name: "address", type: "address" },
    { name: "nonce", type: "bytes32" },
  ],
};

// ---- IndexedDB generic helpers ----
const DB_NAME = "dfsp";
const DB_VERSION = 1;
const STORE = "kv";
function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => { const db = req.result; if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE); };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function idbGet<T>(key: string): Promise<T | undefined> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const st = tx.objectStore(STORE);
    const rq = st.get(key);
    rq.onsuccess = () => resolve(rq.result as T | undefined);
    rq.onerror = () => reject(rq.error);
  });
}
async function idbSet<T>(key: string, val: T): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.objectStore(STORE).put(val, key);
  });
}

// ---- Helpers base64 ----
function ab2b64(ab: ArrayBuffer): string { const u8 = new Uint8Array(ab); let s=""; for (let i=0;i<u8.length;i++) s+=String.fromCharCode(u8[i]); return btoa(s); }
function b64toAb(b64: string): ArrayBuffer { const bin = atob(b64); const u8 = new Uint8Array(bin.length); for (let i=0;i<bin.length;i++) u8[i]=bin.charCodeAt(i); return u8.buffer; }

// ---- EOA encrypted storage ----
const KEY_EOA_PRIV_LEGACY = "eoaPrivHex"; // незашифрованный (для миграции)
const KEY_EOA_ENC = "eoaPrivEnc";
const KEY_EOA_SALT = "eoaPrivSalt";
const KEY_EOA_IV = "eoaPrivIv";
const EOA_KDF_ITER = 200_000;
let unlockedEOAPriv: string | null = null;
let autoLockTimer: number | null = null;
const AUTO_LOCK_MS = 15 * 60 * 1000;
const AUTOLOCK_KEY = 'dfsp_autolock_enabled';
function isAutolockEnabled(): boolean {
  try { return (localStorage.getItem(AUTOLOCK_KEY) ?? '1') === '1'; } catch { return true; }
}
function scheduleAutoLock(){
  if (!isAutolockEnabled()) return; // не ставим таймер, если выключено
  if(autoLockTimer) clearTimeout(autoLockTimer);
  autoLockTimer = window.setTimeout(()=>lockEOA(), AUTO_LOCK_MS);
}
export function isEOAUnlocked(): boolean { return !!unlockedEOAPriv; }
export function lockEOA(): void { unlockedEOAPriv=null; if(autoLockTimer){clearTimeout(autoLockTimer); autoLockTimer=null;} try { window.dispatchEvent(new CustomEvent('dfsp:locked')); } catch (e) { console.debug('dispatch locked failed', e); } }
async function deriveAesKey(pass: string, salt: Uint8Array): Promise<CryptoKey> { const material = await crypto.subtle.importKey("raw", new TextEncoder().encode(pass), "PBKDF2", false, ["deriveKey"]); return crypto.subtle.deriveKey({name:"PBKDF2",salt,iterations:EOA_KDF_ITER,hash:"SHA-256"},material,{name:"AES-GCM",length:256},false,["encrypt","decrypt"]); }
async function encryptEOA(pass: string, privHex: string){ const salt=crypto.getRandomValues(new Uint8Array(16)); const iv=crypto.getRandomValues(new Uint8Array(12)); const key=await deriveAesKey(pass,salt); const ct=await crypto.subtle.encrypt({name:"AES-GCM",iv},key,new TextEncoder().encode(privHex)); await idbSet(KEY_EOA_SALT,ab2b64(salt.buffer)); await idbSet(KEY_EOA_IV,ab2b64(iv.buffer)); await idbSet(KEY_EOA_ENC,ab2b64(ct)); }
async function decryptEOA(pass: string): Promise<string>{ const saltB64=await idbGet<string>(KEY_EOA_SALT); const ivB64=await idbGet<string>(KEY_EOA_IV); const ctB64=await idbGet<string>(KEY_EOA_ENC); if(!saltB64||!ivB64||!ctB64) throw new Error("EOA encrypted record missing"); const salt=new Uint8Array(b64toAb(saltB64)); const iv=new Uint8Array(b64toAb(ivB64)); const ct=b64toAb(ctB64); const key=await deriveAesKey(pass,salt); const plain=await crypto.subtle.decrypt({name:"AES-GCM",iv},key,ct); const hex=new TextDecoder().decode(plain); if(!/^0x[0-9a-fA-F]{64}$/.test(hex)) throw new Error("Decrypted EOA invalid"); return hex; }
export async function unlockEOA(password: string): Promise<`0x${string}`>{ if(unlockedEOAPriv) { return unlockedEOAPriv as `0x${string}`; } const enc=await idbGet<string>(KEY_EOA_ENC); const legacy=await idbGet<string>(KEY_EOA_PRIV_LEGACY); if(!enc && legacy && /^0x[0-9a-fA-F]{64}$/.test(legacy)){ await encryptEOA(password, legacy); unlockedEOAPriv=legacy; scheduleAutoLock(); try { window.dispatchEvent(new CustomEvent('dfsp:unlocked')); } catch (e) { console.debug('dispatch unlocked failed', e); } return legacy as `0x${string}`; } if(!enc && !legacy){ const w=Wallet.createRandom(); await encryptEOA(password,w.privateKey); unlockedEOAPriv=w.privateKey; scheduleAutoLock(); try { window.dispatchEvent(new CustomEvent('dfsp:unlocked')); } catch (e) { console.debug('dispatch unlocked failed', e); } return w.privateKey as `0x${string}`; } const hex=await decryptEOA(password); unlockedEOAPriv=hex; scheduleAutoLock(); try { window.dispatchEvent(new CustomEvent('dfsp:unlocked')); } catch (e) { console.debug('dispatch unlocked failed', e); } return hex as `0x${string}`; }
export async function ensureEOAUnlocked(password?: string): Promise<Wallet>{ if(unlockedEOAPriv) return new Wallet(unlockedEOAPriv); if(!password) { const err = new Error("EOA locked (password required)"); (err as any).code = 'EOA_LOCKED'; throw err; } const hex=await unlockEOA(password); return new Wallet(hex); }
// backward compat
export async function ensureEOA(password?: string){ return ensureEOAUnlocked(password); }
export async function reencryptEOA(oldPass: string, newPass: string){ const hex=await decryptEOA(oldPass); await encryptEOA(newPass, hex); unlockedEOAPriv=hex; scheduleAutoLock(); }

// ---- RSA (unchanged except naming) ----
const KEY_RSA_PRIV_PKCS8 = "rsaPrivPkcs8";
const KEY_RSA_PUB_PEM = "rsaPubPem";
export async function ensureRSA(): Promise<{privateKey:CryptoKey;publicPem:string}>{ const existing=await idbGet<ArrayBuffer>(KEY_RSA_PRIV_PKCS8); if(existing){ const priv=await crypto.subtle.importKey("pkcs8",existing,{name:"RSA-PSS",hash:"SHA-256"},true,["sign"]); const stored=await idbGet<string>(KEY_RSA_PUB_PEM); const pubPem=stored ?? await exportRsaPublicPemFromPrivate(priv); if(!stored) await idbSet(KEY_RSA_PUB_PEM,pubPem); return {privateKey:priv,publicPem:pubPem}; } const pair=await crypto.subtle.generateKey({name:"RSA-PSS",modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:"SHA-256"},true,["sign","verify"]); const pkcs8=await crypto.subtle.exportKey("pkcs8",pair.privateKey); const pubPem=await exportRsaPublicPem(pair.publicKey); await idbSet(KEY_RSA_PRIV_PKCS8,pkcs8); await idbSet(KEY_RSA_PUB_PEM,pubPem); return {privateKey:pair.privateKey,publicPem:pubPem}; }
async function exportRsaPublicPemFromPrivate(priv: CryptoKey): Promise<string>{ const jwk=await crypto.subtle.exportKey("jwk",priv) as JsonWebKey; if(!jwk.n||!jwk.e) throw new Error("Invalid RSA private JWK"); const pub=await crypto.subtle.importKey("jwk",{kty:"RSA",n:jwk.n,e:jwk.e,alg:"PS256",ext:true},{name:"RSA-PSS",hash:"SHA-256"},true,["verify"]); return exportRsaPublicPem(pub); }
async function exportRsaPublicPem(pub: CryptoKey): Promise<string>{ const spki=await crypto.subtle.exportKey("spki",pub); const b64=ab2b64(spki).match(/.{1,64}/g)!.join("\n"); return `-----BEGIN PUBLIC KEY-----\n${b64}\n-----END PUBLIC KEY-----\n`; }

// ---- Backup v2 (split) ----
interface BackupV2Full { version:2; mode:"EOA+RSA"; eoaPrivHex:`0x${string}`; rsaPrivPkcs8_b64:string; createdAt:number; }
interface BackupV2RSAOnly { version:2; mode:"RSA-only"; rsaPrivPkcs8_b64:string; createdAt:number; }
async function encryptBackup(password:string, payload:BackupV2Full|BackupV2RSAOnly):Promise<Blob>{ const salt=crypto.getRandomValues(new Uint8Array(16)); const iv=crypto.getRandomValues(new Uint8Array(12)); const material=await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]); const key=await crypto.subtle.deriveKey({name:"PBKDF2",salt,iterations:EOA_KDF_ITER,hash:"SHA-256"},material,{name:"AES-GCM",length:256},true,["encrypt","decrypt"]); const ct=await crypto.subtle.encrypt({name:"AES-GCM",iv},key,new TextEncoder().encode(JSON.stringify(payload))); const out={ version:payload.version, mode:payload.mode, kdf:{name:"PBKDF2",iterations:EOA_KDF_ITER,hash:"SHA-256",salt_b64:ab2b64(salt.buffer)}, cipher:{name:"AES-GCM",iv_b64:ab2b64(iv.buffer),data_b64:ab2b64(ct)} }; return new Blob([JSON.stringify(out,null,2)],{type:"application/json"}); }
export async function createBackupBlob(password:string):Promise<Blob>{ const eoa=unlockedEOAPriv || await idbGet<string>(KEY_EOA_PRIV_LEGACY) || null; const rsa=await idbGet<ArrayBuffer>(KEY_RSA_PRIV_PKCS8); if(!rsa) throw new Error("RSA private missing"); if(!eoa || !/^0x[0-9a-fA-F]{64}$/.test(eoa)) throw new Error("EOA not available (unlock first)"); const payload:BackupV2Full={version:2,mode:"EOA+RSA",eoaPrivHex:eoa as `0x${string}`,rsaPrivPkcs8_b64:ab2b64(rsa),createdAt:Math.floor(Date.now()/1000)}; return encryptBackup(password,payload); }
export async function createBackupBlobRSAOnly(password:string):Promise<Blob>{ const rsa=await idbGet<ArrayBuffer>(KEY_RSA_PRIV_PKCS8); if(!rsa) throw new Error("RSA private missing"); const payload:BackupV2RSAOnly={version:2,mode:"RSA-only",rsaPrivPkcs8_b64:ab2b64(rsa),createdAt:Math.floor(Date.now()/1000)}; return encryptBackup(password,payload); }

// ---- Restore legacy v1 (.dfspkey) ----
interface LegacyBackupV1 { version:1; eoaPrivHex:`0x${string}`; rsaPrivPkcs8_b64:string; createdAt:number; }
export async function restoreFromBackupLegacy(file:File,password:string):Promise<{address:string}>{ const txt=await file.text(); const j=JSON.parse(txt) as any; if(j.version!==1) throw new Error("Not legacy v1"); const salt=b64toAb(j.kdf?.salt_b64||""); const iv=b64toAb(j.cipher?.iv_b64||""); const data=b64toAb(j.cipher?.data_b64||""); const material=await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]); const key=await crypto.subtle.deriveKey({name:"PBKDF2",salt:new Uint8Array(salt),iterations:j.kdf?.iterations||200000,hash:"SHA-256"},material,{name:"AES-GCM",length:256},true,["decrypt"]); const plain=await crypto.subtle.decrypt({name:"AES-GCM",iv:new Uint8Array(iv)},key,data); const payload=JSON.parse(new TextDecoder().decode(plain)) as LegacyBackupV1; if(!/^0x[0-9a-fA-F]{64}$/.test(payload.eoaPrivHex)) throw new Error("Invalid EOA in legacy backup"); await idbSet(KEY_EOA_PRIV_LEGACY,payload.eoaPrivHex); const rsaBuf=b64toAb(payload.rsaPrivPkcs8_b64); await idbSet(KEY_RSA_PRIV_PKCS8,rsaBuf); const priv=await crypto.subtle.importKey("pkcs8",rsaBuf,{name:"RSA-PSS",hash:"SHA-256"},true,["sign"]); const pubPem=await exportRsaPublicPemFromPrivate(priv); await idbSet(KEY_RSA_PUB_PEM,pubPem); return {address:new Wallet(payload.eoaPrivHex).address}; }

// ---- Login signing ----
export type LoginMessage = { address:`0x${string}`; nonce:`0x${string}` };
export async function signLoginTyped(message: LoginMessage): Promise<string>{ const w = unlockedEOAPriv ? new Wallet(unlockedEOAPriv) : await ensureEOA(); return w.signTypedData(LOGIN_DOMAIN, LOGIN_TYPES, message); }

// ---- Share helpers ----
export function pemToArrayBuffer(pem: string): ArrayBuffer { const b64=pem.replace(/-----[^-]+-----/g,"").replace(/\s+/g,""); const bin=atob(b64); const bytes=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++) bytes[i]=bin.charCodeAt(i); return bytes.buffer; }
export function arrayBufferToBase64(buf: ArrayBuffer): string { const bytes=new Uint8Array(buf); let bin=""; for(let i=0;i<bytes.length;i++) bin+=String.fromCharCode(bytes[i]); return btoa(bin); }

// Exports already defined above
export async function hasEOA(): Promise<boolean> {
  const enc = await idbGet<string>(KEY_EOA_ENC);
  const legacy = await idbGet<string>(KEY_EOA_PRIV_LEGACY);
  return !!(enc || legacy);
}

export async function restoreFromBackup(file: File, password: string): Promise<{address:string}> {
  // Пытаемся сначала как v2: не расшифровываем здесь — v2 формат хранит только шифртекст, его применяет другое место.
  // Так как сейчас у нас используется v1 в UI, оставим явный вызов legacy.
  return restoreFromBackupLegacy(file, password);
}
