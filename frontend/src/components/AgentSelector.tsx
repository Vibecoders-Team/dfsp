/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from 'react';
import type { AgentKind } from '../lib/agent/agent';
import { getSelectedAgentKind, setSelectedAgentKind, getAgent } from '../lib/agent/manager';
import { Alert, AlertDescription } from './ui/alert';
import { Button } from './ui/button';
import MetaMaskIcon from './icons/MetaMaskIcon';
import WalletConnectIcon from './icons/WalletConnectIcon';
const EXPECTED_CHAIN_ID = Number((import.meta as any).env?.VITE_CHAIN_ID || (import.meta as any).env?.VITE_EXPECTED_CHAIN_ID || 0);

export default function AgentSelector() {
  const [kind, setKind] = useState<AgentKind>(getSelectedAgentKind());
  const [addr, setAddr] = useState<string>('');
  const [err, setErr] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [chainId, setChainId] = useState<number | null>(null);

  const update = (k: AgentKind) => {
    setSelectedAgentKind(k);
    setKind(k);
    setErr('');
    setAddr('');
    setChainId(null);
  };

  const connect = async () => {
    setBusy(true);
    setErr('');
    try {
      const agent = await getAgent();
      const a = await agent.getAddress();
      setAddr(`${a.slice(0,6)}...${a.slice(-4)}`);
      if (agent.getChainId) {
        const cid = await agent.getChainId();
        if (cid) setChainId(cid);
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Unable to connect signer');
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      const agent = await getAgent();
      if (agent.disconnect) await agent.disconnect();
      setAddr('');
      setChainId(null);
    } catch {
      // ignore
    } finally {
      setBusy(false);
    }
  };

  const switchNet = async () => {
    setBusy(true);
    setErr('');
    try {
      if (!EXPECTED_CHAIN_ID) {
        setErr('No expected chain configured');
        return;
      }
      const agent = await getAgent();
      if (!agent.switchChain) {
        setErr('Switch not supported');
        return;
      }
      await agent.switchChain(EXPECTED_CHAIN_ID);
      if (agent.getChainId) {
        const cid = await agent.getChainId();
        setChainId(cid || null);
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Switch failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-600">Signer:</span>
      <div className="flex gap-1">
        <Button size="sm" variant={kind==='local'?'secondary':'outline'} onClick={()=>update('local')}>Local</Button>
        <Button size="sm" variant={kind==='metamask'?'secondary':'outline'} onClick={()=>update('metamask')}>
          <MetaMaskIcon className="mr-1" /> MetaMask
        </Button>
        <Button size="sm" variant={kind==='walletconnect'?'secondary':'outline'} onClick={()=>update('walletconnect')}>
          <WalletConnectIcon className="mr-1" /> WalletConnect
        </Button>
      </div>
      {addr && <span className="ml-2 text-xs text-gray-500">{addr}</span>}
      {chainId !== null && (
        <span className={`text-xs ${EXPECTED_CHAIN_ID && chainId !== EXPECTED_CHAIN_ID ? 'text-red-600' : 'text-gray-500'}`}>cid:{chainId}</span>
      )}
      <div className="flex gap-1 ml-2">
        <Button size="sm" variant="outline" onClick={connect} disabled={busy}>{busy ? '...' : 'Connect'}</Button>
        <Button size="sm" variant="ghost" onClick={disconnect} disabled={busy}>Disconnect</Button>
        {EXPECTED_CHAIN_ID && (kind==='metamask' || kind==='walletconnect') ? (
          <Button size="sm" variant="outline" onClick={switchNet} disabled={busy || (!addr && kind!=='walletconnect')}>
            {kind==='metamask' ? <MetaMaskIcon className="mr-1" /> : <WalletConnectIcon className="mr-1" />}
            {busy ? '...' : 'Switch'}
          </Button>
        ) : null}
      </div>
      {err && (
        <Alert className="ml-2">
          <AlertDescription className="text-xs">{err}</AlertDescription>
        </Alert>
      )}
    </div>
  );
}
