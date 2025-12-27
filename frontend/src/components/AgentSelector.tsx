/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useState, Suspense } from 'react';
import type { AgentKind } from '@/lib/agent';
import { getSelectedAgentKind, setSelectedAgentKind, getAgent } from '../lib/agent/manager';
import { Alert, AlertDescription } from './ui/alert';
import { Button } from './ui/button';
const MetaMaskFull = React.lazy(() => import('./icons/MetaMaskFull')) as any;
const WalletConnectFull = React.lazy(() => import('./icons/WalletConnectFull')) as any;
import { useAuth } from './useAuth';
const EXPECTED_CHAIN_ID = Number((import.meta as any).env?.VITE_CHAIN_ID || (import.meta as any).env?.VITE_EXPECTED_CHAIN_ID || 0);

export default function AgentSelector({ compact = false, showInlineError = true }: { compact?: boolean; showInlineError?: boolean }) {
  const { user } = useAuth();
  const [kind, setKind] = useState<AgentKind>(getSelectedAgentKind());
  const [addr, setAddr] = useState<string>('');
  const [err, setErr] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [chainId, setChainId] = useState<number | null>(null);

  const readAgentState = async () => {
    try {
      const agent = await getAgent();
      const a = await agent.getAddress();
      setAddr(`${a.slice(0,6)}...${a.slice(-4)}`);
      if (agent.getChainId) {
        const cid = await agent.getChainId();
        setChainId(cid ?? null);
      }
    } catch {
      // Do not show error on silent read
    }
  };

  const update = async (k: AgentKind) => {
    if (k === kind || busy) return; // no-op or in-progress
    setBusy(true);
    setErr('');
    try {
      setSelectedAgentKind(k);
      setKind(k);
      setAddr('');
      setChainId(null);
      // For local do not force unlock by reading address; just stop here
      if (k === 'local') return;
      if (k === 'walletconnect') {
        const hasSession = (() => { try { return sessionStorage.getItem('dfsp_wc_connected') === '1'; } catch { return false; } })();
        const agent = await getAgent();
        if (!hasSession && (agent as any).connect) { await (agent as any).connect(); }
        await readAgentState();
        return;
      }
      // metamask path
      await readAgentState();
    } catch (e: unknown) {
      // Не откатываемся обратно на Local: иначе выглядит как "само переключилось".
      // Оставляем выбранный signer и показываем ошибку.
      setErr(e instanceof Error ? e.message : 'Switch signer failed');
    } finally {
      setBusy(false);
    }
  };

  // Compact signed-in view: show only current signer kind
  if (compact && user) {
    return (
      <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600">
        <span>Signer:</span>
        <span className="flex items-center gap-1 font-medium text-gray-800">
          {kind === 'local' ? (
            <span className="px-1 py-0.5 rounded bg-gray-200 text-gray-700">Local</span>
          ) : kind === 'ton' ? (
            <span className="px-1 py-0.5 rounded bg-blue-100 text-blue-700">TON</span>
          ) : (
            <Suspense fallback={<span style={{display:'inline-block',width:16}}/>}>
              {kind === 'metamask' && <MetaMaskFull size={16} className="mr-0" />}
              {kind === 'walletconnect' && <WalletConnectFull size={16} className="mr-0" />}
            </Suspense>
          )}
        </span>
        {chainId !== null && <span className="text-gray-400">cid:{chainId}</span>}
      </div>
    );
  }

  // TON users - show read-only view with hint to link EVM wallet
  if (user?.authMethod === 'ton') {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-gray-600 shrink-0">Signer:</span>
        <span className="px-2 py-1 rounded bg-blue-100 text-blue-700 text-sm font-medium">TON Connect</span>
        <span className="text-xs text-amber-600">(Link EVM wallet for on-chain features)</span>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-gray-600 shrink-0">Signer:</span>
      <div className="flex gap-1 shrink-0">
        <Button size="sm" variant={kind==='local'?'secondary':'outline'} onClick={()=>update('local')} disabled={busy}>Local</Button>
        <Button size="sm" variant={kind==='metamask'?'secondary':'outline'} onClick={()=>update('metamask')} disabled={busy}>
          <Suspense fallback={<span style={{display:'inline-block',width:18}}/>}><MetaMaskFull className="mr-1" /></Suspense> MetaMask
        </Button>
        <Button size="sm" variant={kind==='walletconnect'?'secondary':'outline'} onClick={()=>update('walletconnect')} disabled={busy}>
          <Suspense fallback={<span style={{display:'inline-block',width:18}}/>}><WalletConnectFull className="mr-1" /></Suspense> WalletConnect
        </Button>
      </div>
      {addr && <span className="ml-2 text-xs text-gray-500 shrink-0">{addr}</span>}
      {chainId !== null && (
        <span className={`text-xs ${EXPECTED_CHAIN_ID && chainId !== EXPECTED_CHAIN_ID && (kind === 'metamask' || kind === 'walletconnect') ? 'text-red-600' : 'text-gray-500'} shrink-0`}>cid:{chainId}</span>
      )}
      {showInlineError && err && (
        <Alert className="ml-2 shrink-0">
          <AlertDescription className="text-xs">{err}</AlertDescription>
        </Alert>
      )}
    </div>
  );
}
