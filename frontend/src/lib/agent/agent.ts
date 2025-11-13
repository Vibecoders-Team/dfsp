// SignerAgent interface and helpers
import type { TypedDataDomain, TypedDataField } from 'ethers';

export type AgentKind = 'local' | 'metamask' | 'walletconnect';

export interface SignerAgent {
  kind: AgentKind;
  getAddress(): Promise<`0x${string}`>;
  signTypedData(domain: TypedDataDomain, types: Record<string, TypedDataField[]>, message: Record<string, unknown>): Promise<string>;
  getChainId?(): Promise<number | undefined>;
  disconnect?(): Promise<void>;
  switchChain?(chainId: number): Promise<void>;
}

export function stripEip712Domain(types: Record<string, TypedDataField[]>): Record<string, TypedDataField[]> {
  // ethers v6 expects types without EIP712Domain key in the map
  const out: Record<string, TypedDataField[]> = {};
  for (const [k, v] of Object.entries(types)) {
    if (k !== 'EIP712Domain') out[k] = v;
  }
  return out;
}
