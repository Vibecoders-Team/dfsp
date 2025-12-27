import type { SignerAgent, AgentKind } from './agent';
import { LocalAgent } from './local';

const KEY = 'dfsp_agent_kind';
let cached: SignerAgent | null = null;
let cachedKind: AgentKind | null = null;
let pending: Promise<SignerAgent> | null = null;

export function getSelectedAgentKind(): AgentKind {
  const k = (localStorage.getItem(KEY) as AgentKind | null) || 'local';
  if (k !== 'local' && k !== 'metamask' && k !== 'walletconnect' && k !== 'ton') return 'local';
  return k;
}

export function setSelectedAgentKind(kind: AgentKind) {
  localStorage.setItem(KEY, kind);
  // reset cache so next getAgent() re-initializes
  cached = null;
  cachedKind = null;
  pending = null;
  try { window.dispatchEvent(new CustomEvent('dfsp:agent-kind', { detail: { kind } })); } catch { /* ignore */ }
}

export async function getAgent(): Promise<SignerAgent> {
  const sel = getSelectedAgentKind();
  if (cached && cachedKind === sel) return cached;
  if (pending) return pending;
  pending = (async () => {
    let agent: SignerAgent;
    if (sel === 'local') {
      agent = new LocalAgent();
    } else if (sel === 'metamask') {
      const { MetaMaskAgent } = await import('./metamask');
      agent = new MetaMaskAgent();
    } else if (sel === 'ton') {
      const { TonAgent } = await import('./ton');
      agent = new TonAgent();
    } else {
      const { WalletConnectAgent } = await import('./walletconnect');
      agent = new WalletConnectAgent();
    }
    cached = agent;
    cachedKind = sel;
    return agent;
  })();
  try {
    return await pending;
  } finally {
    pending = null;
  }
}
