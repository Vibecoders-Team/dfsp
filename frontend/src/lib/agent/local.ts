import type { TypedDataDomain, TypedDataField } from 'ethers';
import type { SignerAgent } from './agent';
import { ensureEOA } from '../keychain';

export class LocalAgent implements SignerAgent {
  kind = 'local' as const;

  async getAddress(): Promise<`0x${string}`> {
    const w = await ensureEOA();
    return w.address as `0x${string}`;
  }

  async signTypedData(domain: TypedDataDomain, types: Record<string, TypedDataField[]>, message: Record<string, unknown>): Promise<string> {
    const w = await ensureEOA();
    return w.signTypedData(domain, types, message as any);
  }
}
