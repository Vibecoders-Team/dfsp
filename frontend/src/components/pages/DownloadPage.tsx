import { useState, useEffect, useMemo, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import Layout from '../Layout';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Alert, AlertDescription } from '../ui/alert';
import { Progress } from '../ui/progress';
import { ArrowLeft, Download, Key, AlertCircle, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
import { fetchDownload, fetchGrantByCapId, submitMetaTx, type ForwardTyped } from '@/lib/api';
import { ensureRSA } from '@/lib/keychain';
import { getErrorMessage } from '@/lib/errors';
import { getOptionalPowHeader } from '@/lib/pow';
import { isAxiosError } from 'axios';
import { getAgent } from '@/lib/agent/manager';
import { ensureUnlockedOrThrow } from '@/lib/unlock';
import { decryptStream } from '@/lib/cryptoClient';

const IPFS_GATEWAY =
  ((import.meta as unknown as { env?: { VITE_IPFS_PUBLIC_GATEWAY?: string } }).env?.VITE_IPFS_PUBLIC_GATEWAY)
  ?? 'https://ipfs.dfsp.app';

function b64ToU8(b64: string): Uint8Array {
  const bin = atob(b64);
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return u8;
}

export default function DownloadPage() {
  const { capId = '' } = useParams();
  const navigate = useNavigate();
  const [phase, setPhase] = useState<'idle'|'pow'|'fetch'|'decrypt'|'download'|'saving'|'done'|'error'|'need_keys'>('idle');
  const [err, setErr] = useState('');
  const [progress, setProgress] = useState(0);
  const [powProgress, setPowProgress] = useState(0);
  const [grantInfo, setGrantInfo] = useState<{ status?: string } | null>(null);
  const pollingRef = useRef<number | null>(null);

  // require RSA private key
  useEffect(() => {
    (async () => {
      try {
        await ensureRSA();
        setPhase('idle');
      } catch {
        setPhase('need_keys');
      }
    })();
  }, []);

  // poll grant status
  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const g = await fetchGrantByCapId(capId);
        if (!cancelled) setGrantInfo(g);
      } catch { /* ignore polling errors */ }
      finally {
        if (!cancelled) {
          const s = grantInfo?.status;
          const terminal = s === 'revoked' || s === 'expired' || s === 'exhausted';
          pollingRef.current = window.setTimeout(poll, terminal ? 8000 : 3000);
        }
      }
    }
    if (capId) poll();
    return () => {
      cancelled = true;
      if (pollingRef.current) window.clearTimeout(pollingRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capId]);

  const humanGrant = useMemo(() => {
    if (!err) return '';
    if (/403/.test(err) || /forbidden/i.test(err)) {
      const s = grantInfo?.status;
      if (s === 'revoked') return 'Access revoked by the owner.';
      if (s === 'expired') return 'Grant has expired.';
      if (s === 'exhausted') return 'Download limit exceeded.';
      return 'Access forbidden.';
    }
    if (/429/.test(err)) return 'PoW required or quota exceeded. Try again.';
    return '';
  }, [err, grantInfo]);

  async function startDownload() {
    try {
      setErr('');
      setProgress(0);
      setPhase('pow');
      setPowProgress(0);

      // Simulate PoW progress UI while computing in background
      let done = false;
      const ticker = window.setInterval(() => {
        setPowProgress((p) => (p < 95 ? p + 5 : p));
        if (done) window.clearInterval(ticker);
      }, 150);

      let powHeader = await getOptionalPowHeader();
      done = true;
      setPowProgress(100);

      setPhase('fetch');
      let encK: string; let ipfsPath: string; let requestId: string | undefined; let typedData: ForwardTyped | undefined; let fileName: string | undefined;
      try {
        const res = await fetchDownload(capId, powHeader);
        encK = res.encK; ipfsPath = res.ipfsPath; requestId = res.requestId; typedData = res.typedData as unknown as ForwardTyped | undefined; fileName = res.fileName;
      } catch (e) {
        if (isAxiosError(e) && e.response?.status === 429) {
          const detail = e.response?.data && (e.response.data as { detail?: string }).detail;
          if (detail && detail.startsWith('pow_')) {
            powHeader = await getOptionalPowHeader(true);
            const res2 = await fetchDownload(capId, powHeader);
            encK = res2.encK; ipfsPath = res2.ipfsPath; requestId = res2.requestId; typedData = res2.typedData as unknown as ForwardTyped | undefined;
          } else {
            throw e;
          }
        } else {
          throw e;
        }
      }

      // submit meta-tx (useOnce)
      if (requestId && typedData) {
        (async () => {
          try {
            const agent = await getAgent();
            const sign = async (): Promise<string> => {
              try {
                return await agent.signTypedData(
                  typedData.domain,
                  typedData.types,
                  typedData.message
                );
              } catch (e: unknown) {
                const emsg = (e as { message?: string; code?: string }) || {};
                if (String(emsg.message || '').includes('EOA locked') || emsg.code === 'EOA_LOCKED') {
                  try { await ensureUnlockedOrThrow(); } catch { /* no-op */ }
                  return await agent.signTypedData(
                    typedData.domain,
                    typedData.types,
                    typedData.message
                  );
                }
                throw e;
              }
            };
            const sig = await sign();
            await submitMetaTx(requestId, typedData, sig);
          } catch {
            // non-blocking meta-tx failure
          }
        })();
      }

      setPhase('decrypt');
      // decrypt symmetric key with RSA private key
      const { privateKey } = await ensureRSA();
      const encBytes = b64ToU8(encK).buffer as ArrayBuffer;
      let K_file: Uint8Array | null = null;
      try {
        const plain = await crypto.subtle.decrypt({ name: 'RSA-OAEP' }, privateKey as CryptoKey, encBytes);
        K_file = new Uint8Array(plain);
      } catch (e) {
        console.warn('Failed to decrypt encK, will download encrypted blob:', e);
      }

      setPhase('download');
      const base = IPFS_GATEWAY.replace(/\/+$/, '');
      const path = ipfsPath.startsWith('/') ? ipfsPath : `/${ipfsPath}`;
      const url = `${base}${path}`;
      const resp = await fetch(url);
      if (!resp.ok || !resp.body) throw new Error(`Download failed: ${resp.status} ${resp.statusText}`);

      let blob: Blob;
      if (K_file) {
        try {
          blob = await decryptStream(resp.clone(), K_file, (done, total) => {
            if (total > 0) setProgress(Math.round((done/total)*100));
          });
        } catch (e) {
          console.warn('Decrypt stream failed, fallback to raw blob:', e);
          blob = await resp.blob();
        }
      } else {
        blob = await resp.blob();
      }

      setPhase('saving');
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = fileName || 'downloaded-file';
      a.click();
      URL.revokeObjectURL(a.href);

      setProgress(100);
      setPhase('done');
      toast.success('Download complete');
    } catch (e) {
      setErr(getErrorMessage(e, 'Download failed'));
      setPhase('error');
      setProgress(0);
    }
  }

  if (phase === 'need_keys') {
    return (
      <Layout>
        <div className="max-w-2xl mx-auto">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              You need to restore your RSA private key before you can download files.
            </AlertDescription>
          </Alert>
          <div className="mt-6 text-center">
            <Link to="/settings/keys">
              <Button className="gap-2">
                <Key className="h-4 w-4" />
                Restore Keys in Settings
              </Button>
            </Link>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate('/grants')} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            Back to Grants
          </Button>
          <h1>Download File</h1>
        </div>

        {err && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              {err}
              {humanGrant && <div className="mt-1 text-sm text-gray-700">{humanGrant}</div>}
            </AlertDescription>
          </Alert>
        )}

        {phase === 'pow' && (
          <Card>
            <CardHeader>
              <CardTitle>Proof of Work</CardTitle>
              <CardDescription>Computing proof of work challenge...</CardDescription>
            </CardHeader>
            <CardContent>
              <Progress value={powProgress} className="mb-2" />
              <div className="text-sm text-gray-600">{powProgress}%</div>
            </CardContent>
          </Card>
        )}

        {(phase === 'download' || phase === 'saving') && (
          <Card>
            <CardHeader>
              <CardTitle>Downloading</CardTitle>
              <CardDescription>{phase === 'saving' ? 'Saving...' : 'Downloading and decrypting file...'}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Progress value={progress} />
              <div className="text-sm text-gray-600">{Math.round(progress)}% complete</div>
            </CardContent>
          </Card>
        )}

        {phase === 'done' && (
          <Alert>
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            <AlertDescription className="text-green-800">
              File downloaded successfully
            </AlertDescription>
          </Alert>
        )}

        <div className="flex gap-3 justify-end">
          <Button onClick={startDownload} disabled={phase !== 'idle' && phase !== 'done'} className="gap-2">
            <Download className="h-4 w-4" />
            {phase === 'done' ? 'Download again' : 'Start Download'}
          </Button>
        </div>
      </div>
    </Layout>
  );
}
