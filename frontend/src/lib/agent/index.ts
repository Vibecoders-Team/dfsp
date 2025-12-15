export type { SignerAgent, AgentKind } from './agent';
export { stripEip712Domain } from './agent';
export { LocalAgent } from './local';

import { LocalAgent } from './local';

// NOTE: Do NOT import MetaMaskAgent or WalletConnectAgent eagerly here —
// importing them at module top-level pulls their dependencies into the
// initial bundle. Use dynamic import when a caller needs an instance.

export async function getAgent(kind: 'local' | 'metamask' | 'walletconnect') {
  if (kind === 'local') return new LocalAgent();
  if (kind === 'metamask') {
    const mod = await import('./metamask');
    return new mod.MetaMaskAgent();
  }
  const mod = await import('./walletconnect');
  return new mod.WalletConnectAgent();
}
