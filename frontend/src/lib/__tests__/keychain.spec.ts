import { describe, it, expect, beforeEach, vi } from 'vitest';
import { unlockEOA, isEOAUnlocked, lockEOA, ensureEOAUnlocked, __resetKeychainForTests } from '../keychain';

function clearIndexedDBShim(): Promise<void> {
  __resetKeychainForTests();
  return Promise.resolve();
}

describe('EOA lock/unlock', () => {
  beforeEach(async () => {
    // Ensure window exists for dispatch (harmless in node)
    if (typeof globalThis.window === 'undefined') {
      // @ts-expect-error test shim
      globalThis.window = { dispatchEvent: () => {}, setTimeout: setTimeout, clearTimeout: clearTimeout };
    } else {
      // @ts-expect-error augment
      if (!window.setTimeout) window.setTimeout = setTimeout as any;
      // @ts-expect-error augment
      if (!window.clearTimeout) window.clearTimeout = clearTimeout as any;
      // @ts-expect-error augment
      if (!window.dispatchEvent) window.dispatchEvent = () => {};
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
    await expect(ensureEOAUnlocked(undefined as any)).rejects.toThrow(/password/i);
  });
});
