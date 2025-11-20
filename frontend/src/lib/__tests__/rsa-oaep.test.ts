import { ensureRSA, pemToArrayBuffer } from '../keychain';
import { describe, it, expect } from 'vitest';
import { webcrypto as nodeCrypto } from 'crypto';

function b64(bytes: Uint8Array): string { let s = ''; for (let i=0;i<bytes.length;i++) s+=String.fromCharCode(bytes[i]); return btoa(s); }

// happy-dom provides window.crypto.subtle in vitest env configured in package.json
if (!(globalThis as unknown as { crypto?: Crypto }).crypto || !(globalThis as unknown as { crypto?: Crypto }).crypto!.subtle) {
  (globalThis as unknown as { crypto?: Crypto }).crypto = nodeCrypto as unknown as Crypto;
}

describe('RSA-OAEP enc/dec K_file (32B)', () => {
  it('should encrypt with public key and decrypt with private key', async () => {
    const { privateKey, publicPem } = await ensureRSA();
    // import public for encrypt
    const spki = pemToArrayBuffer(publicPem);
    const pub = await crypto.subtle.importKey('spki', spki, { name:'RSA-OAEP', hash:'SHA-256' }, false, ['encrypt']);
    const K = crypto.getRandomValues(new Uint8Array(32));
    const ct = await crypto.subtle.encrypt({ name:'RSA-OAEP' }, pub, K);
    expect(ct.byteLength).toBeGreaterThan(0);
    const pt = new Uint8Array(await crypto.subtle.decrypt({ name:'RSA-OAEP' }, privateKey, ct));
    expect(b64(pt)).toEqual(b64(K));
  }, 15_000);
});
