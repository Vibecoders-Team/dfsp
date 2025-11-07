import type { SignerAgent, AgentKind } from './agent';
import { LocalAgent } from './local';

const KEY = 'dfsp_agent_kind';
let cached: SignerAgent | null = null;
let cachedKind: AgentKind | null = null;

export function getSelectedAgentKind(): AgentKind {
  const k = (localStorage.getItem(KEY) as AgentKind | null) || 'local';
  if (k !== 'local' && k !== 'metamask' && k !== 'walletconnect') return 'local';
  return k;
}

export function setSelectedAgentKind(kind: AgentKind) {
  localStorage.setItem(KEY, kind);
  // reset cache so next getAgent() re-initializes
  cached = null;
  cachedKind = null;
}

export async function getAgent(): Promise<SignerAgent> {
  const sel = getSelectedAgentKind();
  if (cached && cachedKind === sel) return cached;
  if (sel === 'local') {
    cached = new LocalAgent();
    cachedKind = sel;
    return cached;
  }
  if (sel === 'metamask') {
    const { MetaMaskAgent } = await import('./metamask');
    cached = new MetaMaskAgent();
    cachedKind = sel;
    return cached;
  }
  const { WalletConnectAgent } = await import('./walletconnect');
  cached = new WalletConnectAgent();
  cachedKind = 'walletconnect';
  return cached;
}

