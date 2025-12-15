import { useState, useEffect } from 'react';
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
import { fetchGranteePubKey, shareFile, type ShareItem, submitMetaTx, type ForwardTyped, listGrants, createPublicLink, listPublicLinks, revokePublicLink, type PublicLinkItem } from '@/lib/api.ts';
import { getErrorMessage } from '@/lib/errors.ts';
import { getOrCreateFileKey } from '@/lib/fileKey.ts';
import { pemToArrayBuffer, arrayBufferToBase64 } from '@/lib/keychain.ts';
import { getOptionalPowHeader } from '@/lib/pow.ts';
import { importKeyFromCid } from '@/lib/importKeyCard.ts';
import { isAxiosError } from 'axios';
import { getAgent } from '@/lib/agent/manager.ts';
import { ensureUnlockedOrThrow } from '@/lib/unlock.ts';
import { signForwardTyped } from '@/lib/signing.ts';
import { NetworkStatus } from '../NetworkStatus';
import type { SignerAgent } from '@/lib/agent';
import type * as React from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';

interface Recipient {
  address: string;
  encryptedKey: string;
}

interface ShareResult {
  grantee: string;
  capId: string;
  status: 'queued' | 'pending' | 'confirmed' | 'revoked' | 'expired' | 'exhausted' | 'duplicate' | 'error';
  error?: string;
}

const addrRe = /^0x[a-fA-F0-9]{40}$/;
const isAddr = (v: string) => addrRe.test(v.trim());
type ViteEnv = { VITE_CHAIN_ID?: string; VITE_EXPECTED_CHAIN_ID?: string };
const VENV: ViteEnv = (import.meta as unknown as { env: ViteEnv }).env || {};
const EXPECTED_CHAIN_ID = Number(VENV.VITE_CHAIN_ID || VENV.VITE_EXPECTED_CHAIN_ID || 31337);

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

  const [metaTxErrors, setMetaTxErrors] = useState<string[]>([]);
  const [pendingMetaTx, setPendingMetaTx] = useState<ForwardTyped[] | null>(null);
  const [networkHint, setNetworkHint] = useState<string>('');
  const [awaitingMetaTxSign, setAwaitingMetaTxSign] = useState(false);
  const [polling, setPolling] = useState(false);
  const [pollAttempts, setPollAttempts] = useState(0);
  const [expectedChainId] = useState<number | null>(EXPECTED_CHAIN_ID);
  const [currentChainId, setCurrentChainId] = useState<number | null>(null);
  const [debugMode] = useState<boolean>(() => localStorage.getItem('dfsp_debug_meta') === '1');
  const [rawTypedData, setRawTypedData] = useState<ForwardTyped[] | null>(null);
  const [metaSubmitted, setMetaSubmitted] = useState(false);

  const [pubModalOpen, setPubModalOpen] = useState(false);
  const [publicLinks, setPublicLinks] = useState<PublicLinkItem[]>([]);
  const [ttlSec, setTtlSec] = useState<string>('86400');
  const [maxPublicDownloads, setMaxPublicDownloads] = useState<string>('0');
  const [powEnabled, setPowEnabled] = useState<boolean>(false);
  const [powDiff, setPowDiff] = useState<string>('0');
  const [nameOverride, setNameOverride] = useState<string>('');
  const [mimeOverride, setMimeOverride] = useState<string>('');
  const [creatingPublic, setCreatingPublic] = useState(false);

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

      // Ensure unlocked early only for local agent.
      const agent = await getAgent();
      const isLocal = agent.kind === 'local';
      if (isLocal) {
        await ensureUnlockedOrThrow().catch(() => { throw new Error('Unlock cancelled'); });
      } else {
        setNetworkHint('');
        // enforce expected chain for external wallets
        if (expectedChainId != null && 'getChainId' in agent && typeof agent.getChainId === 'function') {
          const cid = await agent.getChainId();
          if (cid !== expectedChainId) {
            if ('switchChain' in agent && typeof agent.switchChain === 'function') {
              try { await agent.switchChain(expectedChainId); }
              catch {
                setNetworkHint(`Wrong network (${cid}). Please switch to ${expectedChainId} in your wallet and retry.`);
                setIsSubmitting(false);
                return;
              }
            } else {
              setNetworkHint(`Wrong network (${cid}). Please switch to ${expectedChainId} in your wallet and retry.`);
              setIsSubmitting(false);
              return;
            }
          }
        }
      }

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
        const detail = isAxiosError(e) ? (e.response?.data && (e.response.data as { detail?: string }).detail) : undefined;
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
        setPendingMetaTx(tdl);
        setRawTypedData(tdl);
        setMetaTxErrors([]);
        if (tdl.length > 0) {
          if (isLocal) {
            try { await ensureUnlockedOrThrow(); } catch { throw new Error('Unlock cancelled'); }
          }
          await Promise.all(
            tdl.map(async (td: ForwardTyped) => {
               const agentNow = await getAgent();
               // Enforce chain for ForwardRequest (external wallets)
              if (agentNow.kind !== 'local' && td.domain?.chainId && 'getChainId' in agentNow && typeof agentNow.getChainId === 'function') {
                const desired = Number(td.domain.chainId);
                const current = await agentNow.getChainId();
                if (current !== desired) {
                  if ('switchChain' in agentNow && typeof agentNow.switchChain === 'function') {
                    try { await agentNow.switchChain(desired); }
                    catch {
                      setNetworkHint(`Wrong network (${current}). Please switch to ${desired} in your wallet and retry.`);
                      throw new Error('Network mismatch for meta-tx');
                    }
                    const after = await agentNow.getChainId();
                    if (after !== desired) { setNetworkHint(`Wrong network (${after}). Please switch to ${desired} in your wallet and retry.`); throw new Error('Network mismatch for meta-tx'); }
                  } else {
                    setNetworkHint(`Wrong network (${current}). Please switch to ${desired} in your wallet and retry.`);
                    throw new Error('Network mismatch for meta-tx');
                  }
                }
              }
              const { signature, typedData } = await signForwardTyped(agentNow as SignerAgent, td, true);
              const reqId = crypto.randomUUID();
              const res = await submitMetaTx(reqId, typedData, signature);
              console.info('MetaTx submitted', { reqId, status: res.status, task: res.task_id });
            })
          );
          setMetaSubmitted(true);
          startPolling();
        }
      } catch (e) {
        console.warn('Grant meta-tx submit failed (initial phase):', e);
        setMetaTxErrors([getErrorMessage(e, 'Meta-tx signing failed')]);
      }

      setResults((resp?.items || []).map((it) => ({ grantee: it.grantee, capId: it.capId, status: it.status as ShareResult['status'] })));
      toast.success(`File shared with ${recipients.length} recipient(s)`);
      // Don't navigate immediately; wait for meta-tx signing completion
      if ((resp?.typedDataList || []).length > 0) {
        setAwaitingMetaTxSign(true);
      } else {
        // If no typed data, we can navigate after short delay
        setTimeout(() => navigate(`/files/${fileId}`), 1500);
      }
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

  const retryMetaTx = async () => {
    if (!pendingMetaTx || pendingMetaTx.length === 0) return;
    try {
      const agent = await getAgent();
      const isLocal = agent.kind === 'local';
      const errs: string[] = [];
      await Promise.all(pendingMetaTx.map(async (td) => {
        try {
          if (isLocal) { await ensureUnlockedOrThrow().catch(() => { throw new Error('Unlock cancelled'); }); }
          const { signature, typedData } = await signForwardTyped(agent as SignerAgent, td, true);
          const reqId = crypto.randomUUID();
          await submitMetaTx(reqId, typedData, signature);
        } catch (e) {
          errs.push(getErrorMessage(e, 'Retry failed'));
        }
      }));
      setMetaTxErrors(errs);
      if (errs.length === 0) toast.success('Meta-transactions submitted');
    } catch (e) {
      toast.error(getErrorMessage(e, 'Retry meta-tx failed'));
    }
  };

  const signPendingMetaTx = async () => {
    if (!pendingMetaTx || pendingMetaTx.length === 0) return;
    const agent = await getAgent();
    const isLocal = agent.kind === 'local';
    const errs: string[] = [];
    try {
      if (isLocal) {
        try { await ensureUnlockedOrThrow(); } catch { throw new Error('Unlock cancelled'); }
      } else {
        setNetworkHint('');
      }
      for (const td of pendingMetaTx) {
        try {
          const { signature, typedData } = await signForwardTyped(agent as SignerAgent, td, true);
          const reqId = crypto.randomUUID();
          await submitMetaTx(reqId, typedData, signature);
        } catch (e) {
          errs.push(getErrorMessage(e, 'Sign/submit failed'));
        }
      }
      setMetaTxErrors(errs);
      if (errs.length === 0) {
        toast.success('Meta-tx submitted');
        setMetaSubmitted(true);
        startPolling();
        setAwaitingMetaTxSign(false);
      }
    } catch (e) {
      errs.push(getErrorMessage(e, 'Sign process failed'));
      setMetaTxErrors(errs);
    }
  };

  const switchNetworkAndSign = async () => {
    if (!pendingMetaTx || pendingMetaTx.length === 0 || expectedChainId == null) return;
    const agent = await getAgent();
    if (agent.kind === 'local') return; // not applicable
    try {
      if (agent.switchChain) {
        await agent.switchChain(expectedChainId);
        setCurrentChainId(expectedChainId);
        setNetworkHint('');
      }
      await signPendingMetaTx();
    } catch (e) {
      toast.error(getErrorMessage(e, 'Failed to switch network'));
    }
  };

  function startPolling() {
    if (polling) return;
    setPolling(true);
    setPollAttempts(0);
    pollOnce();
  }
  async function pollOnce() {
    try {
      setPollAttempts(p => p + 1);
      const gr = await listGrants(fileId);
      // update statuses in results
      setResults(prev => prev.map(r => {
        const found = gr.find(g => g.capId === r.capId);
        return found ? { ...r, status: found.status as typeof r.status } : r;
      }));
      const allConfirmedOrTerminal = gr.length > 0 && gr.every(g => ['confirmed','revoked','expired','exhausted'].includes(g.status));
      if (allConfirmedOrTerminal) {
        toast.success('Grants finalized');
        setTimeout(() => navigate(`/files/${fileId}`), 1200);
        setPolling(false);
        return;
      }
    } catch {
      // ignore transient errors
    }
    if (pollAttempts < 20) {
      setTimeout(pollOnce, 3000);
    } else {
      toast.message('Polling timeout');
      setPolling(false);
      // allow manual navigation
    }
  }

  useEffect(()=>{
    const onLogout = () => {
      setPolling(false);
      setResults([]);
      setPendingMetaTx(null);
    };
    window.addEventListener('dfsp:logout', onLogout);
    return ()=> window.removeEventListener('dfsp:logout', onLogout);
  },[]);

  useEffect(() => { (async () => { try { const items = await listPublicLinks(fileId); setPublicLinks(items); } catch { void 0; } })(); }, [fileId]);

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
                    <Badge variant={result.status === 'queued' ? 'default' : result.status === 'confirmed' ? 'secondary' : 'outline'}>{result.status}</Badge>
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
          <div className="ml-auto">
            <Button variant="outline" size="sm" onClick={()=>setPubModalOpen(true)}>Share public link</Button>
          </div>
        </div>

        <Alert>
          <Info className="h-4 w-4" />
          <AlertDescription>
            Sharing requires a published RSA public key. Recipients must be registered on the platform.
          </AlertDescription>
        </Alert>

        <NetworkStatus />

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

        <form onSubmit={e => { e.preventDefault(); handleShare(); }}>
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
                 <Button type="button" onClick={addRecipient} disabled={isSubmitting} className="gap-2">
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
                       <Button type="button" variant="ghost" size="sm" onClick={() => removeRecipient(recipient.address)} disabled={isSubmitting}>
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

         <Card>
           <CardHeader>
             <CardTitle>Public Links</CardTitle>
             <CardDescription>Active public links for this file</CardDescription>
           </CardHeader>
           <CardContent>
             {publicLinks.length === 0 ? (
               <div className="text-center py-8 text-gray-500">No public links</div>
             ) : (
               <div className="space-y-3">
                 {publicLinks.map(pl=> (
                   <div key={pl.token} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                     <div className="flex-1">
                       <div className="text-sm break-all">Token: <code className="bg-gray-100 px-1 py-0.5 rounded">{pl.token}</code></div>
                       <div className="text-xs text-gray-500">Expires: {pl.expires_at || '-'}</div>
                       <div className="text-xs text-gray-500">
                         Downloads: {pl.downloads_count ?? 0}
                         {pl.policy?.max_downloads && pl.policy.max_downloads > 0
                           ? ` / ${pl.policy.max_downloads} (${Math.max(0, pl.policy.max_downloads - (pl.downloads_count ?? 0))} left)`
                           : ' / ∞ (unlimited)'}
                       </div>
                     </div>
                     <div className="flex gap-2">
                       <Button type="button" variant="outline" size="sm" onClick={() => {
                         const _IM = (import.meta as unknown) as { env?: Record<string,string> };
                         const origin = _IM.env?.VITE_PUBLIC_ORIGIN || window.location.origin;
                         const pubUrl = origin.replace(/\/$/, '') + `/public/${pl.token}`;
                         const K_file = getOrCreateFileKey(fileId);
                         const keyB64 = btoa(String.fromCharCode(...K_file));
                         const full = pubUrl + `#k=${encodeURIComponent(keyB64)}`;
                         navigator.clipboard.writeText(full);
                         toast.success('Public link copied');
                       }}>Copy</Button>
                       <Button type="button" variant="ghost" size="sm" onClick={async()=>{ try { await revokePublicLink(pl.token); toast.success('Revoked'); const items = await listPublicLinks(fileId); setPublicLinks(items); } catch(e){ toast.error(getErrorMessage(e,'Failed to revoke')); } }}>Revoke</Button>
                     </div>
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

         {metaTxErrors.length > 0 && (
           <Alert variant="destructive">
             <AlertCircle className="h-4 w-4" />
             <AlertDescription>
               <div className="space-y-2">
                 {metaTxErrors.map((e,i)=>(<div key={i} className="text-xs break-all">{e}</div>))}
                 <Button type="button" size="sm" variant="outline" onClick={retryMetaTx}>Retry Meta-tx</Button>
               </div>
             </AlertDescription>
           </Alert>
         )}

         {networkHint && (
           <Alert>
             <AlertCircle className="h-4 w-4" />
             <AlertDescription className="text-xs">{networkHint}</AlertDescription>
           </Alert>
         )}

         {awaitingMetaTxSign && !networkHint && (
           <Alert>
             <AlertCircle className="h-4 w-4" />
             <AlertDescription className="text-xs flex flex-col gap-2">
               Meta-transaction needs signing.
               <Button type="button" size="sm" variant="outline" onClick={signPendingMetaTx}>Sign & Submit Meta-tx</Button>
             </AlertDescription>
           </Alert>
         )}
         {awaitingMetaTxSign && networkHint && (
           <Alert variant="destructive">
             <AlertCircle className="h-4 w-4" />
             <AlertDescription className="text-xs flex flex-col gap-2">
               {networkHint}
               <div className="flex flex-wrap gap-2">
                 <Button type="button" size="sm" variant="outline" onClick={signPendingMetaTx}>Retry Sign & Submit</Button>
                 <Button type="button" size="sm" onClick={switchNetworkAndSign}>
                   Switch to {expectedChainId ?? '?'} & Sign
                 </Button>
               </div>
             </AlertDescription>
           </Alert>
         )}

         {results.length>0 && polling && (
           <Alert>
             <AlertCircle className="h-4 w-4" />
             <AlertDescription className="text-xs">Polling grant statuses... attempt {pollAttempts}/20</AlertDescription>
           </Alert>
         )}

         {debugMode && rawTypedData && (
           <Card>
             <CardHeader>
               <CardTitle>Debug: TypedDataList</CardTitle>
               <CardDescription>Chain insight and raw payloads</CardDescription>
             </CardHeader>
             <CardContent className="space-y-2 text-xs max-h-64 overflow-auto font-mono">
               <div>expectedChainId: {expectedChainId ?? 'n/a'} | currentChainId: {currentChainId ?? 'n/a'} | metaSubmitted: {String(metaSubmitted)}</div>
               {rawTypedData.map((td, i) => (
                 <pre key={i}>{JSON.stringify(td, null, 2)}</pre>
               ))}
             </CardContent>
           </Card>
         )}

         <div className="flex gap-3 justify-end">
           <Button type="button" variant="outline" onClick={() => navigate(`/files/${fileId}`)} disabled={isSubmitting}>
             Cancel
           </Button>
           <Button type="submit" disabled={isSubmitting || recipients.length === 0}>
             {isSubmitting ? 'Sharing...' : 'Share File'}
           </Button>
         </div>
         </form>
      </div>

      <Dialog open={pubModalOpen} onOpenChange={setPubModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Share public link</DialogTitle>
          </DialogHeader>
          <form onSubmit={async (e) => {
            e.preventDefault();
            try {
              setCreatingPublic(true);
              const payload = {
                ttl_sec: ttlSec? Number(ttlSec): undefined,
                max_downloads: maxPublicDownloads? Number(maxPublicDownloads): undefined,
                pow: powEnabled? { enabled: true, difficulty: powDiff? Number(powDiff): undefined }: undefined,
                name_override: nameOverride || undefined,
                mime_override: mimeOverride || undefined,
              };
              const resp = await createPublicLink(fileId, payload);
              const _IM = (import.meta as unknown) as { env?: Record<string,string> };
              const origin = _IM.env?.VITE_PUBLIC_ORIGIN || window.location.origin;
              const pubUrl = origin.replace(/\/$/, '') + `/public/${resp.token}`;
              const K_file = getOrCreateFileKey(fileId);
              const keyB64 = btoa(String.fromCharCode(...K_file));
              const full = pubUrl + `#k=${encodeURIComponent(keyB64)}`;
              navigator.clipboard.writeText(full);
              toast.success('Public link created & copied');
              setPubModalOpen(false);
              const items = await listPublicLinks(fileId); setPublicLinks(items);
            } catch (e) {
              toast.error(getErrorMessage(e, 'Failed to create public link'));
            } finally {
              setCreatingPublic(false);
            }
          }}>
          <div className="grid gap-3 py-2">
            <div className="grid gap-1">
              <Label>TTL (seconds)</Label>
              <Input value={ttlSec} onChange={e=>setTtlSec(e.target.value)} placeholder="86400" />
            </div>
            <div className="grid gap-1">
              <Label>Max downloads (0 for unlimited)</Label>
              <Input value={maxPublicDownloads} onChange={e=>setMaxPublicDownloads(e.target.value)} placeholder="0" />
            </div>
            <div className="flex items-center gap-2">
              <input id="powEnabled" type="checkbox" checked={powEnabled} onChange={e=>setPowEnabled(e.target.checked)} />
              <Label htmlFor="powEnabled">Enable PoW</Label>
              <Input className="ml-2 w-24" value={powDiff} onChange={e=>setPowDiff(e.target.value)} placeholder="difficulty" disabled={!powEnabled} />
            </div>
            <div className="grid gap-1">
              <Label>Name override</Label>
              <Input value={nameOverride} onChange={e=>setNameOverride(e.target.value)} placeholder="" />
            </div>
            <div className="grid gap-1">
              <Label>MIME override</Label>
              <Input value={mimeOverride} onChange={e=>setMimeOverride(e.target.value)} placeholder="" />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={()=>setPubModalOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={creatingPublic}>{creatingPublic? 'Creating…' : 'Create & Copy'}</Button>
          </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}
