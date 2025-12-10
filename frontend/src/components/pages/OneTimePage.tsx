import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Alert, AlertDescription } from '../ui/alert';
import { Progress } from '../ui/progress';
import { Download, AlertCircle, CheckCircle2, Key } from 'lucide-react';
import { Button } from '../ui/button';
import { notify } from '@/lib/toast';
import { ensureRSA } from '@/lib/keychain';
import { getErrorMessage } from '@/lib/errors';
import { decryptStream } from '@/lib/cryptoClient';
import { sanitizeFilename } from '@/lib/sanitize.ts';
import { api } from '@/lib/api';

const IPFS_GATEWAY =
  ((import.meta as unknown as { env?: { VITE_IPFS_PUBLIC_GATEWAY?: string } }).env?.VITE_IPFS_PUBLIC_GATEWAY)
  ?? 'https://ipfs.dfsp.app';

type OneTimePayload = {
  encK: string;
  ipfsPath: string;
  fileName?: string;
};

function b64ToU8(b64: string): Uint8Array {
  const bin = atob(b64);
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return u8;
}

export default function OneTimePage() {
  const { token = '' } = useParams();
  const [phase, setPhase] = useState<'loading'|'ready'|'downloading'|'decrypting'|'done'|'error'|'expired'|'need_keys'>('loading');
  const [err, setErr] = useState('');
  const [progress, setProgress] = useState(0);
  const [payload, setPayload] = useState<OneTimePayload | null>(null);

  // Check if we have RSA keys
  useEffect(() => {
    (async () => {
      try {
        await ensureRSA();
      } catch {
        setPhase('need_keys');
      }
    })();
  }, []);

  // Fetch metadata (this consumes the token!)
  useEffect(() => {
    if (phase !== 'loading' || !token) return;

    (async () => {
      try {
        const { data } = await api.get<OneTimePayload>(`/dl/one-time/${token}`, {
          headers: { accept: 'application/json' }
        });
        setPayload(data);
        setPhase('ready');
      } catch (e: unknown) {
        const msg = getErrorMessage(e, 'Failed to load download link');
        if (msg.includes('410') || msg.toLowerCase().includes('expired')) {
          setPhase('expired');
        } else {
          setErr(msg);
          setPhase('error');
        }
      }
    })();
  }, [token, phase]);

  async function startDownload() {
    if (!payload) return;

    try {
      setErr('');
      setProgress(0);
      setPhase('downloading');

      // Decrypt symmetric key with RSA private key
      const { privateKey } = await ensureRSA();
      const encBytes = b64ToU8(payload.encK).buffer as ArrayBuffer;
      let K_file: Uint8Array | null = null;
      try {
        const plain = await crypto.subtle.decrypt({ name: 'RSA-OAEP' }, privateKey as CryptoKey, encBytes);
        K_file = new Uint8Array(plain);
      } catch (e) {
        console.warn('Failed to decrypt encK, will download encrypted blob:', e);
      }

      // Download from IPFS
      const base = IPFS_GATEWAY.replace(/\/+$/, '');
      const path = payload.ipfsPath.startsWith('/') ? payload.ipfsPath : `/${payload.ipfsPath}`;
      const url = `${base}${path}`;
      const resp = await fetch(url);
      if (!resp.ok || !resp.body) {
        throw new Error(`Download failed: ${resp.status} ${resp.statusText}`);
      }

      setPhase('decrypting');

      let blob: Blob;
      if (K_file) {
        try {
          blob = await decryptStream(resp.clone(), K_file, (done, total) => {
            if (total > 0) setProgress(Math.round((done / total) * 100));
          });
        } catch (e) {
          console.warn('Decrypt stream failed, fallback to raw blob:', e);
          blob = await resp.blob();
        }
      } else {
        blob = await resp.blob();
      }

      // Save file
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = sanitizeFilename(payload.fileName) || 'downloaded-file';
      a.click();
      URL.revokeObjectURL(a.href);

      setProgress(100);
      setPhase('done');
      notify.success('Download complete');
    } catch (e) {
      setErr(getErrorMessage(e, 'Download failed'));
      setPhase('error');
      setProgress(0);
    }
  }

  if (phase === 'need_keys') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-destructive" />
              Keys Required
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                You need to restore your RSA private key before you can download files.
              </AlertDescription>
            </Alert>
            <div className="text-center">
              <Link to="/settings/keys">
                <Button className="gap-2">
                  <Key className="h-4 w-4" />
                  Restore Keys in Settings
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (phase === 'expired') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-destructive" />
              Link Expired
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                This one-time download link has already been used or has expired (410).
              </AlertDescription>
            </Alert>
            <div className="text-center text-sm text-muted-foreground">
              Please request a new link from the sender.
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (phase === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardContent className="pt-6">
            <div className="text-center space-y-4">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto"></div>
              <p className="text-sm text-muted-foreground">Loading download link...</p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (phase === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-destructive" />
              Error
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{err}</AlertDescription>
            </Alert>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (phase === 'done') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-green-500" />
              Download Complete
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Alert>
              <CheckCircle2 className="h-4 w-4" />
              <AlertDescription>
                Your file has been downloaded successfully.
              </AlertDescription>
            </Alert>
            <div className="text-center text-sm text-muted-foreground">
              This link can no longer be used.
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const fileName = payload?.fileName || 'Unknown file';

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="max-w-md w-full">
        <CardHeader>
          <CardTitle>Secure File Download</CardTitle>
          <CardDescription>
            One-time encrypted download via Telegram
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">File name:</span>
              <span className="font-medium">{fileName}</span>
            </div>
          </div>

          {(phase === 'downloading' || phase === 'decrypting') && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">
                  {phase === 'downloading' ? 'Downloading...' : 'Decrypting...'}
                </span>
                <span className="font-medium">{progress}%</span>
              </div>
              <Progress value={progress} />
            </div>
          )}

          {phase === 'ready' && (
            <Button
              onClick={startDownload}
              className="w-full gap-2"
              size="lg"
            >
              <Download className="h-5 w-5" />
              Download File
            </Button>
          )}

          {(phase === 'downloading' || phase === 'decrypting') && (
            <Button disabled className="w-full gap-2" size="lg">
              <Download className="h-5 w-5 animate-pulse" />
              {phase === 'downloading' ? 'Downloading...' : 'Decrypting...'}
            </Button>
          )}

          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-xs">
              This is a one-time link. After downloading, it will expire and cannot be used again.
              The file will be decrypted locally in your browser.
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    </div>
  );
}

