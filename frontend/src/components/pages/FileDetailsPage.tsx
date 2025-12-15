import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate, useSearchParams } from 'react-router-dom';
import Layout from '../Layout';
import { Button } from '../ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';
import { Badge } from '../ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../ui/alert-dialog';
import { ArrowLeft, Copy, Share2, CheckCircle2, XCircle, AlertCircle, Download, Edit2 } from 'lucide-react';
import { notify } from '@/lib/toast';
import { fetchMeta, fetchVersions, listGrants, prepareRevoke, submitMetaTx, type ForwardTyped, fetchMyFiles, createPublicLink, listPublicLinks, revokePublicLink, type PublicLinkItem, renameFile } from '@/lib/api.ts';
import { getErrorMessage } from '@/lib/errors.ts';
import { getAgent } from '@/lib/agent/manager';
import { ensureUnlockedOrThrow } from '@/lib/unlock';
import { Alert, AlertDescription } from '../ui/alert';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { sanitizeFilename, parseContentDisposition } from '@/lib/sanitize.ts';

interface VersionRow {
  cid: string;
  checksum: string;
  created: Date;
}

interface GrantRow {
  grantee: string;
  capId: string;
  expiresAt?: Date;
  maxDownloads: number;
  usedDownloads: number;
  status: 'queued' | 'pending' | 'confirmed' | 'revoked' | 'expired' | 'exhausted';
}

interface FileDetailsModel {
  id: string;
  name?: string; // теперь используем
  size?: number;
  created?: Date;
  owner?: string;
  cid?: string;
  checksum?: string;
  mimeType?: string;
  versions: VersionRow[];
  grants: GrantRow[];
}

export default function FileDetailsPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [file, setFile] = useState<FileDetailsModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revokeDialogOpen, setRevokeDialogOpen] = useState(false);
  const [selectedCapId, setSelectedCapId] = useState<string | null>(null);
  const [intentAutoOpened, setIntentAutoOpened] = useState(false);
  const [pubModalOpen, setPubModalOpen] = useState(false);
  const [publicLinks, setPublicLinks] = useState<PublicLinkItem[]>([]);
  const [ttlSec, setTtlSec] = useState<string>('86400');
  const [maxDownloads, setMaxDownloads] = useState<string>('0');
  const [powEnabled, setPowEnabled] = useState<boolean>(false);
  const [powDiff, setPowDiff] = useState<string>('0');
  const [nameOverride, setNameOverride] = useState<string>('');
  const [mimeOverride, setMimeOverride] = useState<string>('');
  const [creating, setCreating] = useState(false);
  const intentId = searchParams.get('intent');
  const revokeCapParam = searchParams.get('revoke');

  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [extensionWarning, setExtensionWarning] = useState(false);
  const [renaming, setRenaming] = useState(false);

  useEffect(() => {
    const onLogout = () => {
      setFile(null);
      setError(null);
      setLoading(false);
    };
    window.addEventListener('dfsp:logout', onLogout);
    return () => window.removeEventListener('dfsp:logout', onLogout);
  }, []);

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    notify.success(`${label} copied to clipboard`, { dedupeId: `copy-${label}-${text}` });
  };

  const formatSize = (bytes?: number) => {
    if (!bytes) return '-';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.min(sizes.length - 1, Math.floor(Math.log(bytes) / Math.log(k)));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (date?: Date) => {
    if (!date || isNaN(date.getTime())) return '-';
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const truncate = (str: string, length: number) => {
    if (!str) return '';
    if (str.length <= length) return str;
    return str.slice(0, Math.floor(length / 2)) + '...' + str.slice(-Math.floor(length / 2));
  };

  const handleDownload = async () => {
    try {
      if (!file?.cid) throw new Error('CID missing');
      const gw =
        ((import.meta as unknown as { env?: { VITE_IPFS_PUBLIC_GATEWAY?: string } }).env?.VITE_IPFS_PUBLIC_GATEWAY)
        ?? 'https://ipfs.dfsp.app';
      const url = gw.replace(/\/+$/, '') + `/ipfs/${file.cid}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Failed: ${res.status}`);

      // Try to get filename from Content-Disposition header
      const contentDisposition = res.headers.get('Content-Disposition');
      const headerFilename = parseContentDisposition(contentDisposition);
      const finalFilename = headerFilename || file.name;

      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = sanitizeFilename(finalFilename) || file.id;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
      notify.success('Download started', { dedupeId: `download-${file?.id ?? 'unknown'}` });
    } catch (e) {
      notify.error(getErrorMessage(e, 'Download failed'), { dedupeId: `download-err-${file?.id ?? 'unknown'}` });
    }
  };

  const handleRevokeAsk = (capId: string) => {
    setSelectedCapId(capId);
    setRevokeDialogOpen(true);
  };

  const handleRenameOpen = () => {
    setNewName(file?.name || '');
    setExtensionWarning(false);
    setRenameDialogOpen(true);
  };

  const getFileExtension = (filename: string) => {
    const parts = filename.split('.');
    return parts.length > 1 ? parts[parts.length - 1] : '';
  };

  const handleRename = async () => {
    if (!newName.trim()) {
      notify.error('File name cannot be empty', { dedupeId: 'rename-empty' });
      return;
    }

    // Check if extension was removed
    const oldExt = getFileExtension(file?.name || '');
    const newExt = getFileExtension(newName);
    if (oldExt && oldExt !== newExt && !extensionWarning) {
      setExtensionWarning(true);
      return;
    }

    const oldName = file?.name;
    try {
      setRenaming(true);

      // Optimistic update
      if (file) {
        setFile({ ...file, name: newName });
      }

      await renameFile(id, newName);
      notify.success('File renamed successfully', { dedupeId: `rename-${file?.id}` });
      setRenameDialogOpen(false);
      setExtensionWarning(false);

      // Reload to confirm server state
      await load();
    } catch (e) {
      // Rollback on error
      if (file && oldName !== undefined) {
        setFile({ ...file, name: oldName });
      }
      notify.error(getErrorMessage(e, 'Failed to rename file'), { dedupeId: 'rename-error' });
    } finally {
      setRenaming(false);
    }
  };

  const confirmRevoke = async () => {
    if (!selectedCapId) return;
    try {
      const prep = await prepareRevoke(selectedCapId); // { requestId, typedData }
      const agent = await getAgent();
      if (agent.kind === 'local') {
        try { await ensureUnlockedOrThrow(); } catch { throw new Error('Unlock cancelled'); }
      }
      const sig = await agent.signTypedData((prep.typedData as ForwardTyped).domain, (prep.typedData as ForwardTyped).types, (prep.typedData as ForwardTyped).message);
      await submitMetaTx(prep.requestId, prep.typedData as ForwardTyped, sig);
      notify.success('Revoke submitted', { dedupeId: `revoke-${selectedCapId}` });
      setRevokeDialogOpen(false);
      setSelectedCapId(null);
      await load();
    } catch (e) {
      notify.error(getErrorMessage(e, 'Failed to revoke grant'), { dedupeId: 'revoke-error' });
    }
  };

  const statusBadge = (status: GrantRow['status']) => {
    switch (status) {
      case 'confirmed':
        return <Badge className="bg-green-100 text-green-800">Active</Badge>;
      case 'expired':
        return <Badge variant="secondary">Expired</Badge>;
      case 'revoked':
        return <Badge variant="destructive">Revoked</Badge>;
      case 'pending':
        return <Badge>Pending</Badge>;
      case 'exhausted':
        return <Badge variant="secondary">Exhausted</Badge>;
      default:
        return <Badge>{status}</Badge>;
    }
  };

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const [m, v, g, allFiles] = await Promise.all([
        fetchMeta(id),
        fetchVersions(id),
        listGrants(id).catch(() => []),
        fetchMyFiles().catch(() => []),
      ]);
      const found = Array.isArray(allFiles) ? allFiles.find(f=>f.id===id) : undefined;
      const versions: VersionRow[] = (v.versions || []).map((it) => ({
        cid: it.cid || '',
        checksum: (it.checksum && (it.checksum.startsWith('0x') ? it.checksum : '0x' + it.checksum)) || '',
        created: new Date((it.createdAt || 0) * 1000),
      }));
      const grants: GrantRow[] = (g || []).map((gr) => ({
        grantee: gr.grantee,
        capId: gr.capId,
        expiresAt: gr.expiresAt ? new Date(gr.expiresAt) : undefined,
        maxDownloads: gr.maxDownloads,
        usedDownloads: gr.usedDownloads,
        status: gr.status,
      }));
      setFile({
        id,
        name: found?.name,
        size: m.size,
        created: m.createdAt ? new Date(m.createdAt * 1000) : undefined,
        owner: m.owner,
        cid: m.cid,
        checksum: m.checksum,
        mimeType: m.mime,
        versions,
        grants,
      });
    } catch (e) {
      setError(getErrorMessage(e, 'Failed to load file details'));
    } finally {
      setLoading(false);
    }
  };

  const loadPublicLinks = async () => {
    try { const items = await listPublicLinks(file!.id); setPublicLinks(items); } catch {/* ignore */}
  };

  useEffect(() => {
    if (id) { load(); loadPublicLinks(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (!revokeCapParam || !file || intentAutoOpened) return;
    const exists = file.grants.some((g) => g.capId === revokeCapParam);
    if (exists) {
      setIntentAutoOpened(true);
      handleRevokeAsk(revokeCapParam);
    }
  }, [revokeCapParam, file, intentAutoOpened]);

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

  if (error) {
    return (
      <Layout>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </Layout>
    );
  }

  if (!file) return null;

  return (
    <Layout>
      <div className="space-y-6">
        {intentId && (
          <div className="rounded border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
            Открыто из intent {truncate(intentId, 16)}.{" "}
            {revokeCapParam ? `Запрос на revoke ${truncate(revokeCapParam, 18)}.` : "Продолжайте действие."}
          </div>
        )}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/files')}
              className="gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Files
            </Button>
            <div className="flex items-center gap-2">
              <h1>{sanitizeFilename(file.name) || file.id}</h1>
              <Button variant="ghost" size="sm" onClick={handleRenameOpen} className="gap-1">
                <Edit2 className="h-3.5 w-3.5" />
                Rename
              </Button>
            </div>
          </div>
          <div className="flex gap-2">
            <Link to={`/verify/${file.id}`}>
              <Button variant="outline" className="gap-2">
                <CheckCircle2 className="h-4 w-4" />
                Verify
              </Button>
            </Link>
            <Link to={`/files/${file.id}/share`}>
              <Button className="gap-2">
                <Share2 className="h-4 w-4" />
                Share
              </Button>
            </Link>
            <Button variant="secondary" className="gap-2" onClick={handleDownload}>
              <Download className="h-4 w-4" />
              Download
            </Button>
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>File Information</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 items-center">
              <div>
                <div className="text-sm text-gray-500 mb-1">File ID</div>
                <div className="flex items-center gap-2">
                  <code className="text-sm bg-gray-100 px-2 py-1 rounded whitespace-nowrap">{file.id}</code>
                  <Button variant="ghost" size="sm" onClick={() => copyToClipboard(file.id, 'File ID')}>
                    <Copy className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>

              <div>
                <div className="text-sm text-gray-500 mb-1">Size</div>
                <div>{formatSize(file.size)}</div>
              </div>

              <div>
                <div className="text-sm text-gray-500 mb-1">CID</div>
                <div className="flex items-center gap-2">
                  <code className="text-sm bg-gray-100 px-2 py-1 rounded whitespace-nowrap">{file.cid || ''}</code>
                  <Button variant="ghost" size="sm" onClick={() => copyToClipboard(file.cid || '', 'CID')}>
                    <Copy className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>

              <div>
                <div className="text-sm text-gray-500 mb-1">Created</div>
                <div>{formatDate(file.created)}</div>
              </div>

              <div className="col-span-2">
                <div className="text-sm text-gray-500 mb-1">Checksum</div>
                <div className="flex items-center gap-2">
                  <code className="text-sm bg-gray-100 px-2 py-1 rounded whitespace-nowrap">{file.checksum}</code>
                  <Button variant="ghost" size="sm" onClick={() => copyToClipboard(file.checksum || '', 'Checksum')}>
                    <Copy className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>

              <div>
                <div className="text-sm text-gray-500 mb-1">MIME Type</div>
                <div className="text-sm">{file.mimeType || '-'}</div>
              </div>

              <div>
                <div className="text-sm text-gray-500 mb-1">Owner</div>
                <div className="flex items-center gap-2">
                  <code className="text-sm bg-gray-100 px-2 py-1 rounded whitespace-nowrap">{truncate(file.owner || '-', 16)}</code>
                  <Button variant="ghost" size="sm" onClick={() => copyToClipboard(file.owner || '', 'Owner address')}>
                    <Copy className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Versions</CardTitle>
          </CardHeader>
          <CardContent>
            {file.versions.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                No versions yet
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Created</TableHead>
                    <TableHead>CID</TableHead>
                    <TableHead>Checksum</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {file.versions.map((version, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{formatDate(version.created)}</TableCell>
                      <TableCell>
                        <code className="text-xs bg-gray-100 px-2 py-1 rounded">
                          {truncate(version.cid, 32)}
                        </code>
                      </TableCell>
                      <TableCell>
                        <code className="text-xs bg-gray-100 px-2 py-1 rounded">
                          {truncate(version.checksum, 44)}
                        </code>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Grants</CardTitle>
          </CardHeader>
          <CardContent>
            {file.grants.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                No grants yet. Share this file to create grants.
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Grantee</TableHead>
                    <TableHead>Cap ID</TableHead>
                    <TableHead>Expires</TableHead>
                    <TableHead>Downloads</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {file.grants.map((grant) => (
                    <TableRow key={grant.capId}>
                      <TableCell>
                        <code className="text-xs bg-gray-100 px-2 py-1 rounded">
                          {truncate(grant.grantee, 12)}
                        </code>
                      </TableCell>
                      <TableCell>
                        <code className="text-xs bg-gray-100 px-2 py-1 rounded break-all">
                          {grant.capId}
                        </code>
                      </TableCell>
                      <TableCell>{grant.expiresAt ? formatDate(grant.expiresAt) : '-'}</TableCell>
                      <TableCell>
                        {grant.usedDownloads} / {grant.maxDownloads}
                      </TableCell>
                      <TableCell>{statusBadge(grant.status)}</TableCell>
                      <TableCell className="text-right">
                        {(grant.status === 'confirmed' || grant.status === 'pending') && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleRevokeAsk(grant.capId)}
                            className="gap-1.5 text-red-600 hover:text-red-700"
                          >
                            <XCircle className="h-3.5 w-3.5" />
                            Revoke
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Public Links</CardTitle>
          </CardHeader>
          <CardContent>
            {publicLinks.length === 0 ? (
              <div className="text-center py-8 text-gray-500">No public links</div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Token</TableHead>
                    <TableHead>Expires</TableHead>
                    <TableHead>Policy</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {publicLinks.map((pl) => (
                    <TableRow key={pl.token}>
                      <TableCell>
                        <code className="text-xs bg-gray-100 px-2 py-1 rounded break-all">{pl.token}</code>
                      </TableCell>
                      <TableCell>{pl.expires_at ? formatDate(new Date(pl.expires_at)) : '-'}</TableCell>
                      <TableCell>
                        <code className="text-xs bg-gray-100 px-2 py-1 rounded">
                          {JSON.stringify(pl.policy || {})}
                        </code>
                      </TableCell>
                      <TableCell className="text-right flex gap-2 justify-end">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            const _IM = (import.meta as unknown) as { env?: Record<string,string> };
                            const origin = _IM.env?.VITE_PUBLIC_ORIGIN || window.location.origin;
                            const pubUrl = origin.replace(/\/$/, '') + `/public/${pl.token}`;
                            copyToClipboard(pubUrl + (nameOverride ? `#k=${encodeURIComponent(nameOverride)}` : ''), 'Public link');
                          }}
                          className="gap-1.5"
                        >
                          <Copy className="h-3.5 w-3.5" /> Copy
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={async () => { try { await revokePublicLink(pl.token); notify.success('Revoked', { dedupeId: `pub-revoke-${pl.token}` }); await loadPublicLinks(); } catch(e){ notify.error(getErrorMessage(e,'Failed to revoke link'), { dedupeId: 'pub-revoke-err' }); } }}
                          className="gap-1.5 text-red-600 hover:text-red-700"
                        >
                          <XCircle className="h-3.5 w-3.5" /> Revoke
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <AlertDialog open={revokeDialogOpen} onOpenChange={setRevokeDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke Grant</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to revoke access for the selected grant?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmRevoke} className="bg-red-600 hover:bg-red-700">
              Revoke Access
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={pubModalOpen} onOpenChange={setPubModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Share public link</DialogTitle>
          </DialogHeader>
          <form onSubmit={async (e) => { e.preventDefault(); try {
            setCreating(true);
            const payload = {
              ttl_sec: ttlSec? Number(ttlSec): undefined,
              max_downloads: maxDownloads? Number(maxDownloads): undefined,
              pow: powEnabled? { enabled: true, difficulty: powDiff? Number(powDiff): undefined }: undefined,
              name_override: nameOverride || undefined,
              mime_override: mimeOverride || undefined,
            };
            const resp = await createPublicLink(file.id, payload);
            const origin = (import.meta as unknown) as { env?: Record<string,string> };
            const pubUrl = origin.env?.VITE_PUBLIC_ORIGIN.replace(/\/$/, '') + `/public/${resp.token}`;
            copyToClipboard(pubUrl + (nameOverride? `#k=${encodeURIComponent(nameOverride)}`: ''), 'Public link');
            notify.success('Public link created', { dedupeId: 'pub-created' });
            setPubModalOpen(false);
            await loadPublicLinks();
          } catch (err) { notify.error(getErrorMessage(err, 'Failed to create public link'), { dedupeId: 'pub-create-err' }); } finally { setCreating(false); } }}>
          <div className="grid gap-3 py-2">
            <div className="grid gap-1">
              <Label>TTL (seconds)</Label>
              <Input value={ttlSec} onChange={e=>setTtlSec(e.target.value)} placeholder="86400" />
            </div>
            <div className="grid gap-1">
              <Label>Max downloads (0 for unlimited)</Label>
              <Input value={maxDownloads} onChange={e=>setMaxDownloads(e.target.value)} placeholder="0" />
            </div>
            <div className="flex items-center gap-2">
              <input id="powEnabled" type="checkbox" checked={powEnabled} onChange={e=>setPowEnabled(e.target.checked)} />
              <Label htmlFor="powEnabled">Enable PoW</Label>
              <Input className="ml-2 w-24" value={powDiff} onChange={e=>setPowDiff(e.target.value)} placeholder="difficulty" />
            </div>
            <div className="grid gap-1">
              <Label>Name override</Label>
              <Input value={nameOverride} onChange={e=>setNameOverride(e.target.value)} placeholder={sanitizeFilename(file.name) || ''} />
            </div>
            <div className="grid gap-1">
              <Label>MIME override</Label>
              <Input value={mimeOverride} onChange={e=>setMimeOverride(e.target.value)} placeholder={file.mimeType || ''} />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={()=>setPubModalOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={creating}>{creating? 'Creating…' : 'Create & Copy'}</Button>
          </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={renameDialogOpen} onOpenChange={setRenameDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename File</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-1">
              <Label htmlFor="newName">New name</Label>
              <Input
                id="newName"
                value={newName}
                onChange={e => {
                  setNewName(e.target.value);
                  setExtensionWarning(false);
                }}
                placeholder="Enter new file name"
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    handleRename();
                  }
                }}
              />
            </div>
            {extensionWarning && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  Warning: You are removing or changing the file extension. Click Rename again to confirm.
                </AlertDescription>
              </Alert>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => {
              setRenameDialogOpen(false);
              setExtensionWarning(false);
            }}>
              Cancel
            </Button>
            <Button onClick={handleRename} disabled={renaming || !newName.trim()}>
              {renaming ? 'Renaming...' : 'Rename'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}
