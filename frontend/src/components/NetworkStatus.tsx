import { useEffect, useState } from 'react';
import { getAgent } from '../lib/agent/manager';
import { Button } from './ui/button';
import { Alert, AlertDescription } from './ui/alert';
import { AlertCircle } from 'lucide-react';

const EXPECTED = Number((import.meta as unknown as { env?: Record<string, unknown> }).env?.VITE_CHAIN_ID || 31337);

export function NetworkStatus() {
  const [active, setActive] = useState<number | null>(null);
  const [error, setError] = useState<string>('');
  const [switching, setSwitching] = useState(false);

  const refresh = async () => {
    try {
      const agent = await getAgent();
      if (agent.getChainId) {
        const cid = await agent.getChainId();
        setActive(cid ?? null);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    }
  };

  useEffect(() => { refresh(); }, []);

  const doSwitch = async () => {
    setError('');
    setSwitching(true);
    try {
      const agent = await getAgent();
      if (!agent.switchChain) throw new Error('switchChain not supported');
      await agent.switchChain(EXPECTED);
      await refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setSwitching(false);
    }
  };

  const mismatch = active !== null && active !== EXPECTED;
  if (active === null && !error) return null;

  return (
    <div className="my-2">
      {mismatch && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="text-xs flex flex-col gap-2">
            Network mismatch: expected {EXPECTED}, active {active}. Configure RPC URL (VITE_CHAIN_RPC_URL) reachable by your wallet.
            <div className="flex gap-2">
              <Button size="sm" onClick={doSwitch} disabled={switching}>{switching ? 'Switching...' : 'Switch Network'}</Button>
              <Button size="sm" variant="outline" onClick={refresh}>Refresh</Button>
            </div>
            {error && <div className="text-red-700 break-all">{error}</div>}
          </AlertDescription>
        </Alert>
      )}
      {!mismatch && active !== null && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="text-xs">Active chain {active} matches expected {EXPECTED}.</AlertDescription>
        </Alert>
      )}
    </div>
  );
}
