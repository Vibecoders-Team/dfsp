import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { toast } from 'sonner';
import { isEOAUnlocked, unlockEOA } from '@/lib/keychain';

export default function UnlockPortal() {
  const [open, setOpen] = useState(false);
  const [pwd, setPwd] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const on = () => setOpen(true);
    window.addEventListener('dfsp:unlock-dialog', on);
    return () => window.removeEventListener('dfsp:unlock-dialog', on);
  }, []);

  const handleUnlock = async () => {
    if (!pwd) { toast.error('Enter password'); return; }
    setBusy(true);
    try {
      await unlockEOA(pwd);
      try {
        window.dispatchEvent(new CustomEvent('dfsp:unlocked'));
      } catch {
        // ignore dispatch errors in non-DOM env
      }
      toast.success('Key unlocked');
      setOpen(false);
      setPwd('');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Unlock error');
    } finally {
      setBusy(false);
    }
  };

  // Если уже разблокирован, диалог держим закрытым
  useEffect(() => {
    if (isEOAUnlocked() && open) setOpen(false);
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={o => { if(!o && !isEOAUnlocked()) { try { window.dispatchEvent(new CustomEvent('dfsp:unlock-cancel')); } catch {} } setOpen(o); if (!o) setPwd(''); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Unlock local key</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input type="password" placeholder="Password" value={pwd} onChange={e => setPwd(e.target.value)} disabled={busy} />
          <div className="flex gap-2 justify-end">
            <Button variant="outline" onClick={() => { setOpen(false); try { window.dispatchEvent(new CustomEvent('dfsp:unlock-cancel')); } catch {} }} disabled={busy}>Cancel</Button>
            <Button onClick={handleUnlock} disabled={busy || !pwd}>{busy ? '...' : 'Unlock'}</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
