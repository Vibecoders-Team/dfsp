import { useMemo } from 'react';
import { isEOAUnlocked, lockEOA } from '../lib/keychain';
import { Button } from './ui/button';
import { Lock, Unlock } from 'lucide-react';
import { toast } from 'sonner';
import { getSelectedAgentKind } from '../lib/agent/manager';

export default function KeyLockIndicator() {
  const agentKind = getSelectedAgentKind();
  const unlocked = useMemo(() => isEOAUnlocked(), []);

  if (agentKind !== 'local') return null;

  const handleUnlockClick = () => {
    try { window.dispatchEvent(new CustomEvent('dfsp:unlock-dialog')); } catch {}
  };

  const handleLock = () => {
    lockEOA();
    toast.message('Key locked');
  };

  return (
    <div className="flex items-center gap-2">
      {unlocked ? (
        <Button variant="outline" size="sm" onClick={handleLock} className="gap-1" title="Lock key">
          <Lock className="h-4 w-4" /> Lock
        </Button>
      ) : (
        <Button variant="outline" size="sm" onClick={handleUnlockClick} className="gap-1" title="Unlock for signing">
          <Unlock className="h-4 w-4" /> Unlock
        </Button>
      )}
    </div>
  );
}
