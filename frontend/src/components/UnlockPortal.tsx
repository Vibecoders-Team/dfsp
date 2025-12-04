import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { notify } from '@/lib/toast';
import { isEOAUnlocked, unlockEOA } from '@/lib/keychain';
import { getErrorMessage } from '@/lib/errors';
import { rememberLastUnlockPassword } from '@/lib/unlock';

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
    if (!pwd) { notify.error('Enter password', { dedupeId: 'unlock-empty' }); return; }
    setBusy(true);
    try {
      await unlockEOA(pwd);
      rememberLastUnlockPassword(pwd);
      try { window.dispatchEvent(new CustomEvent('dfsp:unlocked')); } catch (e) { console.debug('dispatch unlocked failed', e); }
      notify.success('Key unlocked', { dedupeId: 'unlock-ok' });
      setOpen(false);
      setPwd('');
    } catch (e) {
      // Map common WebCrypto/AES-GCM failure messages to user-friendly text
      let msg = getErrorMessage(e, 'Unlock error');
      if ((e as { code?: string }).code === 'IDB_QUOTA' || /quota/i.test((e as Error)?.message || '')) {
        msg = 'Browser storage is full. Clear site data or free disk space, then try unlocking again.';
      }
      if (e instanceof DOMException && /Operation failed|decrypt/.test(e.message)) {
        msg = 'Incorrect password. Please try again.';
      }
      if (msg === 'Unlock error' && e instanceof Error && !e.message) {
        msg = 'Failed to unlock key. Check your password.';
      }
      notify.error(msg, { dedupeId: 'unlock-error' });
    } finally {
      setBusy(false);
    }
  };

  // Если уже разблокирован, диалог держим закрытым
  useEffect(() => {
    if (isEOAUnlocked() && open) setOpen(false);
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={o => { if(!o && !isEOAUnlocked()) { try { window.dispatchEvent(new CustomEvent('dfsp:unlock-cancel')); } catch (e) { console.debug('dispatch unlock-cancel failed', e); } } setOpen(o); if (!o) setPwd(''); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Unlock local key</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Input type="password" placeholder="Password" value={pwd} onChange={e => setPwd(e.target.value)} disabled={busy} />
          {busy && <div className="text-xs text-gray-500">Unlocking...</div>}
          <div className="flex gap-2 justify-end">
            <Button variant="outline" onClick={() => { setOpen(false); try { window.dispatchEvent(new CustomEvent('dfsp:unlock-cancel')); } catch (e) { console.debug('dispatch unlock-cancel failed', e); } }} disabled={busy}>Cancel</Button>
            <Button onClick={handleUnlock} disabled={busy || !pwd}>{busy ? '...' : 'Unlock'}</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
