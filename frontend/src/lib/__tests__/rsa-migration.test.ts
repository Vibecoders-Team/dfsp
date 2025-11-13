import { describe, it, expect, beforeEach } from 'vitest';
import { __resetKeychainForTests, __injectLegacyRsaPkcs8, __getRsaAlgoForTests, ensureRSA } from '../keychain';
import { webcrypto as nodeCrypto } from 'crypto';

if (!(globalThis as any).crypto || !(globalThis as any).crypto.subtle) {
  (globalThis as any).crypto = nodeCrypto as unknown as Crypto;
}

async function generateLegacyPSS(): Promise<ArrayBuffer> {
  const pair = await crypto.subtle.generateKey({ name: 'RSA-PSS', modulusLength: 2048, publicExponent: new Uint8Array([1,0,1]), hash: 'SHA-256' }, true, ['sign','verify']);
  return crypto.subtle.exportKey('pkcs8', pair.privateKey);
}

describe('RSA migration from PSS to OAEP', () => {
  beforeEach(() => { __resetKeychainForTests(); });
  it('converts legacy PSS pkcs8 to OAEP on ensureRSA()', async () => {
    const legacy = await generateLegacyPSS();
    await __injectLegacyRsaPkcs8(legacy);
    const before = await __getRsaAlgoForTests();
    expect(before).toBe('PSS');

    const { privateKey, publicPem } = await ensureRSA();
    expect(privateKey).toBeTruthy();
    expect(publicPem).toContain('BEGIN PUBLIC KEY');

    const after = await __getRsaAlgoForTests();
    expect(after).toBe('OAEP');
  });
});

