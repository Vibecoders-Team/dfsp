import { describe, it, expect, beforeEach } from 'vitest';
import { unlockEOA, isEOAUnlocked, lockEOA, ensureEOAUnlocked, __resetKeychainForTests } from '../keychain';

function clearIndexedDBShim(): Promise<void> {
  __resetKeychainForTests();
  return Promise.resolve();
}

describe('EOA lock/unlock', () => {
  beforeEach(async () => {
    if (typeof globalThis.window === 'undefined') {
      const shim: Partial<Window & typeof globalThis> = { dispatchEvent: () => true, setTimeout, clearTimeout };
      globalThis.window = shim as Window & typeof globalThis;
    } else {
      const w = globalThis.window as Partial<Window & typeof globalThis>;
      if (!w.setTimeout) (globalThis.window as unknown as { setTimeout: typeof setTimeout }).setTimeout = setTimeout;
      if (!w.clearTimeout) (globalThis.window as unknown as { clearTimeout: typeof clearTimeout }).clearTimeout = clearTimeout;
      if (!w.dispatchEvent) (globalThis.window as unknown as { dispatchEvent: (ev: Event)=>boolean }).dispatchEvent = () => true;
    }
    lockEOA();
    await clearIndexedDBShim();
  });

  it('creates new EOA on first unlock and locks/unlocks correctly', async () => {
    expect(isEOAUnlocked()).toBe(false);
    const addrHex = await unlockEOA('test-password-123');
    expect(addrHex).toMatch(/^0x[0-9a-fA-F]{64}$/);
    expect(isEOAUnlocked()).toBe(true);
    lockEOA();
    expect(isEOAUnlocked()).toBe(false);
  });

  it('ensureEOAUnlocked throws when locked and no password', async () => {
    await expect(ensureEOAUnlocked(undefined as unknown as string)).rejects.toThrow(/password/i);
  });
});
