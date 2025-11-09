import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';

export default function WalletConnectPortal() {
  const [open, setOpen] = useState(false);
  const [uri, setUri] = useState<string | null>(null);

  useEffect(() => {
    const onUri = (e: Event) => {
      const ce = e as CustomEvent<{ uri: string }>;
      setUri(ce.detail?.uri || null);
      setOpen(true);
    };
    const onClose = () => { setOpen(false); setUri(null); };
    window.addEventListener('dfsp:wc-display-uri', onUri as EventListener);
    window.addEventListener('dfsp:wc-close-qr', onClose);
    return () => {
      window.removeEventListener('dfsp:wc-display-uri', onUri as EventListener);
      window.removeEventListener('dfsp:wc-close-qr', onClose);
    };
  }, []);

  return (
    <Dialog open={open} onOpenChange={o=>setOpen(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Connect with WalletConnect</DialogTitle>
        </DialogHeader>
        {uri ? (
          <div className="flex flex-col items-center gap-3">
            <img src={`https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(uri)}&size=256x256`} alt="WalletConnect QR" className="w-56 h-56" />
            <a href={uri} className="text-sm text-blue-600 hover:underline" target="_blank" rel="noreferrer">Open in wallet</a>
          </div>
        ) : (
          <div className="text-sm text-gray-500">Preparing session...</div>
        )}
        <div className="flex justify-end mt-4">
          <Button onClick={()=>{ setOpen(false); setUri(null); }}>Close</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

