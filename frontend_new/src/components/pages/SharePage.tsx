import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import Layout from '../Layout';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Alert, AlertDescription } from '../ui/alert';
import { Badge } from '../ui/badge';
import { ArrowLeft, X, Plus, AlertCircle, CheckCircle2, Info } from 'lucide-react';
import { toast } from 'sonner';
import { fetchGranteePubKey, shareFile, type ShareItem, submitMetaTx, type ForwardTyped } from '../../lib/api';
import { getErrorMessage } from '../../lib/errors';
import { getOrCreateFileKey } from '../../lib/fileKey';
import { pemToArrayBuffer, arrayBufferToBase64, ensureEOA } from '../../lib/keychain';
import { getOptionalPowHeader } from '../../lib/pow';
import { importKeyFromCid } from '../../lib/importKeyCard';
import { isAxiosError } from 'axios';

interface Recipient {
  address: string;
  encryptedKey: string;
}

interface ShareResult {
  grantee: string;
  capId: string;
  status: 'queued' | 'duplicate' | 'error';
  error?: string;
}

const addrRe = /^0x[a-fA-F0-9]{40}$/;
const isAddr = (v: string) => addrRe.test(v.trim());

export default function SharePage() {
  const { id: fileId = '' } = useParams();
  const navigate = useNavigate();
  const [recipientInput, setRecipientInput] = useState('');
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [ttlDays, setTtlDays] = useState('7');
  const [maxDownloads, setMaxDownloads] = useState('3');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [results, setResults] = useState<ShareResult[]>([]);

  // When a grantee key is missing, prompt to import by CID/URL
  const [needPemFor, setNeedPemFor] = useState<string | null>(null);
  const [cidInput, setCidInput] = useState('');

  const validateAddress = (address: string): boolean => isAddr(address);

  const addRecipient = () => {
    const address = recipientInput.trim();
    if (!address) return;
    if (!validateAddress(address)) {
      setError('Invalid Ethereum address format');
      return;
    }
    if (recipients.some((r) => r.address.toLowerCase() === address.toLowerCase())) {
      setError('Address already added');
      return;
    }
    setRecipients([...recipients, { address, encryptedKey: '' }]);
    setRecipientInput('');
    setError('');
  };

  const removeRecipient = (address: string) => {
    setRecipients(recipients.filter((r) => r.address !== address));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addRecipient();
    }
  };

  const validateForm = (): string | null => {
    if (recipients.length === 0) return 'Add at least one recipient';
    const ttl = parseInt(ttlDays);
    if (isNaN(ttl) || ttl < 1 || ttl > 365) return 'TTL must be between 1 and 365 days';
    const maxDl = parseInt(maxDownloads);
    if (isNaN(maxDl) || maxDl < 1 || maxDl > 1000) return 'Max downloads must be between 1 and 1000';
    return null;
  };

  async function performShare() {
    try {
      setIsSubmitting(true);
      setError('');

      const ttl = parseInt(ttlDays);
      const maxDl = parseInt(maxDownloads);

      // 1) Local file symmetric key (persisted per fileId)
      const K_file = getOrCreateFileKey(fileId);
      const K_arraybuf: ArrayBuffer = (() => {
        const ab = new ArrayBuffer(K_file.byteLength);
        new Uint8Array(ab).set(K_file);
        return ab;
      })();

      // 2) Build encK_map via RSA-OAEP for each recipient
      const encK_map: Record<string, string> = {};
      for (const r of recipients) {
        const a = r.address;
        try {
          const pem = await fetchGranteePubKey(a);
          const spki = pemToArrayBuffer(pem);
          const publicKey = await crypto.subtle.importKey(
            'spki',
            spki,
            { name: 'RSA-OAEP', hash: 'SHA-256' },
            false,
            ['encrypt']
          );
          const ct = await crypto.subtle.encrypt({ name: 'RSA-OAEP' }, publicKey, K_arraybuf);
          encK_map[a] = arrayBufferToBase64(ct);
        } catch (e: unknown) {
          if (e instanceof Error && e.message === 'PUBLIC_PEM_NOT_FOUND') {
            setNeedPemFor(a);
            setIsSubmitting(false);
            return;
          }
          throw e instanceof Error ? e : new Error('Failed to encrypt key');
        }
      }

      // 3) PoW header (opt-in), with retry on 429 pow_* detail
      let powHeader = await getOptionalPowHeader();
      let resp: { items: ShareItem[]; typedDataList?: ForwardTyped[] } | null = null;
      try {
        resp = (await shareFile(
          fileId,
          {
            users: recipients.map((r) => r.address),
            ttl_days: ttl,
            max_dl: maxDl,
            encK_map,
            request_id: crypto.randomUUID(),
          },
          powHeader
        )) as { items: ShareItem[]; typedDataList?: ForwardTyped[] };
      } catch (e: unknown) {
        const detail = isAxiosError(e) ? ((e.response?.data as any)?.detail as string | undefined) : undefined;
        if (isAxiosError(e) && e.response?.status === 429 && detail && detail.startsWith('pow_')) {
          powHeader = await getOptionalPowHeader(true);
          resp = (await shareFile(
            fileId,
            {
              users: recipients.map((r) => r.address),
              ttl_days: ttl,
              max_dl: maxDl,
              encK_map,
              request_id: crypto.randomUUID(),
            },
            powHeader
          )) as { items: ShareItem[]; typedDataList?: ForwardTyped[] };
        } else {
          throw e instanceof Error ? e : new Error('Share failed');
        }
      }

      // 4) Submit meta-tx for each typedData if present (non-blocking)
      try {
        const tdl = (resp?.typedDataList || []) as ForwardTyped[];
        if (tdl.length > 0) {
          const w = await ensureEOA();
          await Promise.all(
            tdl.map(async (td: ForwardTyped) => {
              const sig = await w.signTypedData(td.domain, td.types, td.message);
              const reqId = crypto.randomUUID();
              await submitMetaTx(reqId, td, sig);
            })
          );
        }
      } catch (e) {
        console.warn('Grant meta-tx submit failed:', e);
      }

      setResults((resp?.items || []).map((it) => ({ grantee: it.grantee, capId: it.capId, status: it.status })));
      toast.success(`File shared with ${recipients.length} recipient(s)`);
      setTimeout(() => navigate(`/files/${fileId}`), 1500);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to share file'));
    } finally {
      setIsSubmitting(false);
    }
  }

  const handleShare = async () => {
    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }
    await performShare();
  };

  async function doImportCid() {
    if (!needPemFor) return;
    try {
      if (!cidInput.trim()) throw new Error('Provide CID or URL');
      await importKeyFromCid(cidInput);
      setCidInput('');
      setNeedPemFor(null);
      setError('');
      await performShare();
    } catch (e) {
      setError(getErrorMessage(e, 'Failed to import public key'));
    }
  }

  const updateEncryptedKey = (address: string, key: string) => {
    setRecipients(recipients.map((r) => (r.address === address ? { ...r, encryptedKey: key } : r)));
  };

  const truncate = (str: string, length: number) => {
    if (str.length <= length) return str;
    return str.slice(0, length / 2) + '...' + str.slice(-length / 2);
  };

  if (results.length > 0) {
    return (
      <Layout>
        <div className="max-w-2xl mx-auto space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CheckCircle2 className="h-6 w-6 text-green-600" />
                File Shared Successfully
              </CardTitle>
              <CardDescription>
                Grants have been created for the following recipients
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {results.map((result, idx) => (
                  <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div>
                      <code className="text-sm">{truncate(result.grantee, 16)}</code>
                      <div className="text-xs text-gray-500 mt-1">Cap ID: {result.capId}</div>
                    </div>
                    <Badge variant={result.status === 'queued' ? 'default' : 'secondary'}>{result.status}</Badge>
                  </div>
                ))}
              </div>
              <div className="mt-6 flex justify-center">
                <Link to={`/files/${fileId}`}>
                  <Button>View File Details</Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate(`/files/${fileId}`)} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          <h1>Share File</h1>
        </div>

        <Alert>
          <Info className="h-4 w-4" />
          <AlertDescription>
            Sharing requires a published RSA public key. Recipients must be registered on the platform.
          </AlertDescription>
        </Alert>

        {needPemFor && (
          <Card>
            <CardHeader>
              <CardTitle>Public key required</CardTitle>
              <CardDescription>
                We couldn't find a public RSA key for {truncate(needPemFor, 16)}. Paste a CID or URL to their key card.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2">
                <Input placeholder="CID or https://.../ipfs/<cid>" value={cidInput} onChange={(e) => setCidInput(e.target.value)} />
                <Button onClick={doImportCid}>Import</Button>
              </div>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Recipients</CardTitle>
            <CardDescription>Add Ethereum addresses of users you want to share with</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="recipient">Ethereum Address</Label>
              <div className="flex gap-2">
                <Input id="recipient" placeholder="0x..." value={recipientInput} onChange={(e) => setRecipientInput(e.target.value)} onKeyDown={handleKeyDown} disabled={isSubmitting} />
                <Button onClick={addRecipient} disabled={isSubmitting} className="gap-2">
                  <Plus className="h-4 w-4" />
                  Add
                </Button>
              </div>
            </div>

            {recipients.length > 0 && (
              <div className="space-y-2">
                <Label>Added Recipients ({recipients.length})</Label>
                <div className="space-y-2">
                  {recipients.map((recipient) => (
                    <div key={recipient.address} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                      <code className="text-sm">{truncate(recipient.address, 16)}</code>
                      <Button variant="ghost" size="sm" onClick={() => removeRecipient(recipient.address)} disabled={isSubmitting}>
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Access Settings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="ttl">TTL (days)</Label>
                <Input id="ttl" type="number" min="1" max="365" value={ttlDays} onChange={(e) => setTtlDays(e.target.value)} disabled={isSubmitting} />
                <p className="text-xs text-gray-500">Time until access expires</p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="maxDownloads">Max Downloads</Label>
                <Input id="maxDownloads" type="number" min="1" max="1000" value={maxDownloads} onChange={(e) => setMaxDownloads(e.target.value)} disabled={isSubmitting} />
                <p className="text-xs text-gray-500">Maximum download count</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Encrypted Keys</CardTitle>
            <CardDescription>Keys are generated and encrypted for each recipient</CardDescription>
          </CardHeader>
          <CardContent>
            {recipients.length === 0 ? (
              <div className="text-center py-8 text-gray-500">Add recipients to see their encrypted keys</div>
            ) : (
              <div className="space-y-4">
                {recipients.map((recipient) => (
                  <div key={recipient.address} className="space-y-2">
                    <Label className="text-xs">{truncate(recipient.address, 16)}</Label>
                    <Textarea value={recipient.encryptedKey} onChange={(e) => updateEncryptedKey(recipient.address, e.target.value)} disabled className="font-mono text-xs" rows={2} />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="flex gap-3 justify-end">
          <Button variant="outline" onClick={() => navigate(`/files/${fileId}`)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button onClick={handleShare} disabled={isSubmitting || recipients.length === 0}>
            {isSubmitting ? 'Sharing...' : 'Share File'}
          </Button>
        </div>
      </div>
    </Layout>
  );
}
