import { useEffect, useState } from 'react';
import { isEOAUnlocked, lockEOA } from '../lib/keychain';
import { Button } from './ui/button';
import { Lock, Unlock } from 'lucide-react';
import { toast } from 'sonner';
import { getSelectedAgentKind } from '../lib/agent/manager';

export default function KeyLockIndicator() {
  const agentKind = getSelectedAgentKind();
  const [unlocked, setUnlocked] = useState<boolean>(() => isEOAUnlocked());

  useEffect(() => {
    const onUnlocked = () => setUnlocked(true);
    const onLocked = () => setUnlocked(false);
    const onCancel = () => setUnlocked(isEOAUnlocked());
    const onStatus = (e: Event) => {
      const detail = (e as CustomEvent<{ status?: string }>).detail;
      if (detail?.status === 'locked') setUnlocked(false);
      if (detail?.status === 'unlocked') setUnlocked(true);
    };
    window.addEventListener('dfsp:unlocked', onUnlocked);
    window.addEventListener('dfsp:locked', onLocked);
    window.addEventListener('dfsp:unlock-cancel', onCancel);
    window.addEventListener('dfsp:key-status', onStatus as EventListener);
    return () => {
      window.removeEventListener('dfsp:unlocked', onUnlocked);
      window.removeEventListener('dfsp:locked', onLocked);
      window.removeEventListener('dfsp:unlock-cancel', onCancel);
      window.removeEventListener('dfsp:key-status', onStatus as EventListener);
    };
  }, []);

  if (agentKind !== 'local') return null;

  const handleUnlockClick = () => {
    try { window.dispatchEvent(new CustomEvent('dfsp:unlock-dialog')); } catch (e) { console.debug('dispatch unlock-dialog failed', e); }
  };

  const handleLock = () => {
    lockEOA();
    try { window.dispatchEvent(new CustomEvent('dfsp:locked')); } catch (e) { console.debug('dispatch locked failed', e); }
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
