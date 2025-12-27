import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import Layout from '../Layout';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Alert, AlertDescription } from '../ui/alert';
import { AlertCircle, Download } from 'lucide-react';
import { fetchPublicMeta, fetchPublicContent, requestPowChallenge, submitPow } from '@/lib/api';
import { decryptStream } from '@/lib/cryptoClient';
import { toast } from 'sonner';

function extractErrorMessage(err: unknown, fallback = 'Failed'): string {
  if (!err || typeof err !== 'object') return fallback;
  const e = err as Record<string, unknown>;
  const resp = e['response'] as Record<string, unknown> | undefined;
  if (resp) {
    const data = resp['data'] as Record<string, unknown> | undefined;
    const msg = data?.['error'] ?? resp['statusText'] ?? e['message'];
    return String(msg ?? fallback);
  }
  return String(e['message'] ?? fallback);
}

export default function PublicPage() {
  const { token = '' } = useParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<{ name: string; size?: number; mime?: string; policy?: Record<string, unknown> } | null>(null);
  const [solvingPow, setSolvingPow] = useState(false);
  const [powProgress, setPowProgress] = useState<string>('');

  const keyFromHash = useMemo(() => {
    try {
      const h = window.location.hash || '';
      const m = h.match(/[#&]k=([^&]+)/);
      if (!m) return null;
      const keyB64 = decodeURIComponent(m[1]);
      // Decode base64 to Uint8Array
      const raw = atob(keyB64);
      const key = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i++) key[i] = raw.charCodeAt(i);
      return key;
    } catch { return null; }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const m = await fetchPublicMeta(token);
        setMeta({ name: m.name, size: m.size, mime: m.mime, policy: m.policy });
      } catch (e: unknown) {
        const msg = extractErrorMessage(e, 'Failed to load');
        setError(msg);
      } finally {
        setLoading(false);
      }
    })();
  }, [token]);

  const handleDownload = async () => {
    try {
      const policy = meta?.policy as Record<string, unknown> | undefined;
      const needPow = !!(policy && typeof policy === 'object' && Number(policy['pow_difficulty'] ?? 0));
      if (needPow) {
        setSolvingPow(true);
        setPowProgress('requesting challenge…');
        const ch = await requestPowChallenge();
        const difficulty = Number(policy?.['pow_difficulty'] ?? ch.difficulty ?? 1) || 1;
        const nibbles = Math.floor((difficulty + 3) / 4);
        const prefix = '0'.repeat(nibbles);
        let solution = '';
        let i = 0;
        const enc = new TextEncoder();
        while (true) {
          if (i % 1000 === 0) setPowProgress(`solving… tried ${i}`);
          const data = enc.encode(ch.challenge + i.toString(36));
          const digest = await crypto.subtle.digest('SHA-256', data);
          const hex = Array.from(new Uint8Array(digest)).map(b=>b.toString(16).padStart(2,'0')).join('');
          if (hex.startsWith(prefix)) { solution = i.toString(36); break; }
          i++;
          if (i > 5_000_000) { throw new Error('PoW solve timeout'); }
        }
        setPowProgress('submitting solution…');
        try {
          await submitPow(token, ch.challenge, solution);
        } catch (e: unknown) {
          setSolvingPow(false);
          setPowProgress('');
          setError(extractErrorMessage(e, 'PoW failed'));
          return;
        }
        setSolvingPow(false);
        setPowProgress('');
        // tiny delay to ensure access key is visible
        await new Promise(res=>setTimeout(res, 100));
      }
      // try with up to 3 retries on 403 denied due to propagation
      let blob: Blob | null = null;
      for (let attempt=0; attempt<3; attempt++) {
        try {
          blob = await fetchPublicContent(token);
          break;
        } catch (err: unknown) {
          let status: number | undefined;
          if (err && typeof err === 'object') {
            const resp = (err as Record<string, unknown>)['response'];
            if (resp && typeof resp === 'object') {
              const s = (resp as Record<string, unknown>)['status'];
              if (typeof s === 'number') status = s;
            }
          }
          const code = extractErrorMessage(err, '');
          if (status === 403 && code === 'denied' && attempt < 2) {
            await new Promise(res=>setTimeout(res, 150));
            continue;
          }
          throw err;
        }
      }
      if (!blob) throw new Error('download_failed');

      // Decrypt if we have a key
      let finalBlob = blob;
      let finalName = (meta?.name || 'encrypted.bin').replace(/\s+/g,'_');
      if (keyFromHash) {
        try {
          // Create a fake Response to use decryptStream
          const fakeResp = new Response(blob);
          finalBlob = await decryptStream(fakeResp, keyFromHash);
          // Remove .enc extension if present
          if (finalName.endsWith('.enc')) {
            finalName = finalName.slice(0, -4);
          }
        } catch (e: unknown) {
          console.error('Decryption failed:', e);
          toast.error('Failed to decrypt file: ' + extractErrorMessage(e, 'unknown error'));
          return;
        }
      }

      const a = document.createElement('a');
      a.href = URL.createObjectURL(finalBlob);
      a.download = finalName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
      toast.success('Download started');
    } catch (e: unknown) {
      let status: number | undefined;
      if (e && typeof e === 'object') {
        const resp = (e as Record<string, unknown>)['response'];
        if (resp && typeof resp === 'object') {
          const s = (resp as Record<string, unknown>)['status'];
          if (typeof s === 'number') status = s;
        }
      }
      const msg = extractErrorMessage(e, 'Failed to download');
      if (status === 403 || status === 410) {
        setError(msg);
      } else {
        setError('download_failed');
      }
    }
  };

  if (loading) {
    return (
      <Layout>
        <div className="min-h-[50vh] flex items-center justify-center">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto"></div>
            <p className="mt-4">Loading...</p>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-6">
        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <Card>
          <CardHeader>
            <CardTitle>Public File</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 items-center">
              <div>
                <div className="text-sm text-gray-500 mb-1">Name</div>
                <div>{meta?.name || '-'}</div>
              </div>
              <div>
                <div className="text-sm text-gray-500 mb-1">Size</div>
                <div>{meta?.size ?? '-'}</div>
              </div>
              <div>
                <div className="text-sm text-gray-500 mb-1">MIME</div>
                <div>{meta?.mime || '-'}</div>
              </div>
            </div>
            <div className="mt-4">
              <Button className="gap-2" onClick={handleDownload} disabled={!token}>
                <Download className="h-4 w-4" /> Download encrypted content
              </Button>
              {solvingPow && (
                <div className="text-xs text-gray-500 mt-2">{powProgress}</div>
              )}
              {!keyFromHash && (
                <div className="text-xs text-gray-500 mt-2">⚠️ No decryption key found in URL. File will download encrypted.</div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}
