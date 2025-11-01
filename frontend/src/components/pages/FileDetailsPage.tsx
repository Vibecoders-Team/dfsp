import { useEffect, useMemo, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
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
import { ArrowLeft, Copy, Share2, CheckCircle2, XCircle, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { fetchMeta, fetchVersions, listGrants, prepareRevoke, submitMetaTx } from '../../lib/api';
import { getErrorMessage } from '../../lib/errors';
import { ensureEOA } from '../../lib/keychain';
import { Alert, AlertDescription } from '../ui/alert';

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
  name?: string;
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

  const [file, setFile] = useState<FileDetailsModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revokeDialogOpen, setRevokeDialogOpen] = useState(false);
  const [selectedCapId, setSelectedCapId] = useState<string | null>(null);

  const load = async () => {
    try {
      setLoading(true);
      setError(null);
      const [m, v, g] = await Promise.all([
        fetchMeta(id),
        fetchVersions(id),
        listGrants(id).catch(() => []),
      ]);

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
        name: undefined,
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

  useEffect(() => {
    if (id) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied to clipboard`);
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

  const handleRevokeAsk = (capId: string) => {
    setSelectedCapId(capId);
    setRevokeDialogOpen(true);
  };

  const confirmRevoke = async () => {
    if (!selectedCapId) return;
    try {
      const prep = await prepareRevoke(selectedCapId); // { requestId, typedData }
      const w = await ensureEOA();
      const sig = await w.signTypedData(prep.typedData.domain as any, prep.typedData.types as any, prep.typedData.message as any);
      await submitMetaTx(prep.requestId, prep.typedData as any, sig);
      toast.success('Revoke submitted');
      setRevokeDialogOpen(false);
      setSelectedCapId(null);
      await load();
    } catch (e) {
      toast.error(getErrorMessage(e, 'Failed to revoke grant'));
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
            <h1>{file.name || file.cid || id}</h1>
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
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>File Information</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-sm text-gray-500 mb-1">File ID</div>
                <div className="flex items-center gap-2">
                  <code className="text-sm bg-gray-100 px-2 py-1 rounded break-all">{file.id}</code>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => copyToClipboard(file.id, 'File ID')}
                  >
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
                  <code className="text-sm bg-gray-100 px-2 py-1 rounded break-all">
                    {truncate(file.cid || '', 44)}
                  </code>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => copyToClipboard(file.cid || '', 'CID')}
                  >
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
                  <code className="text-sm bg-gray-100 px-2 py-1 rounded flex-1 break-all">
                    {file.checksum}
                  </code>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => copyToClipboard(file.checksum || '', 'Checksum')}
                  >
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
                <code className="text-sm bg-gray-100 px-2 py-1 rounded">
                  {truncate(file.owner || '-', 16)}
                </code>
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
                        <code className="text-xs bg-gray-100 px-2 py-1 rounded break-all">
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
    </Layout>
  );
}
