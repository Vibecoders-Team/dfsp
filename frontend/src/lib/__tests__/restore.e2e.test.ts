import { describe, it, expect, beforeEach } from 'vitest';
import { createBackupBlobRSAOnly, restoreFromBackup, unlockEOA, hasEOA, __resetKeychainForTests } from '../keychain';
import { webcrypto as nodeCrypto } from 'crypto';

if (!(globalThis as unknown as { crypto?: Crypto }).crypto || !(globalThis as unknown as { crypto?: Crypto }).crypto!.subtle) {
  (globalThis as unknown as { crypto?: Crypto }).crypto = nodeCrypto as unknown as Crypto;
}

// minimal window shim for timers and events used by keychain helpers
if (typeof globalThis.window === 'undefined') {
  const shim: Partial<Window & typeof globalThis> = { dispatchEvent: () => true, setTimeout, clearTimeout };
  globalThis.window = shim as Window & typeof globalThis;
} else {
  const w = globalThis.window as Partial<Window & typeof globalThis>;
  if (!w.setTimeout) (globalThis.window as unknown as { setTimeout: typeof setTimeout }).setTimeout = setTimeout;
  if (!w.clearTimeout) (globalThis.window as unknown as { clearTimeout: typeof clearTimeout }).clearTimeout = clearTimeout;
  if (!w.dispatchEvent) (globalThis.window as unknown as { dispatchEvent: (ev: Event)=>boolean }).dispatchEvent = () => true;
}

describe('RSA-only restore flow', () => {
  beforeEach(() => {
    __resetKeychainForTests();
  });

  it('clears existing local EOA and reports RSA-only mode', async () => {
    // seed a local EOA to ensure restore wipes it
    await unlockEOA('old-pass');
    expect(await hasEOA()).toBe(true);

    const blob = await createBackupBlobRSAOnly('restore-pass');
    const file: File = {
      name: 'rsa-only.dfspkey',
      lastModified: Date.now(),
      webkitRelativePath: '',
      size: blob.size,
      type: blob.type || 'application/json',
      arrayBuffer: () => blob.arrayBuffer(),
      slice: (start?: number, end?: number, contentType?: string) => blob.slice(start, end, contentType),
      stream: () => (blob as unknown as { stream: () => ReadableStream<Uint8Array> }).stream(),
      text: () => blob.text(),
      [Symbol.toStringTag]: 'File',
    } as unknown as File;

    const res = await restoreFromBackup(file, 'restore-pass');
    expect(res.mode).toBe('RSA-only');
    expect(await hasEOA()).toBe(false);
  });
});
