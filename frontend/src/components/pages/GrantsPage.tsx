import { useState, useMemo, useEffect } from 'react';
import { Link } from 'react-router-dom';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { Badge } from '../ui/badge';
import { Download, Share2, RefreshCw, Ban } from 'lucide-react';
import { fetchMyGrants, revokeGrant, type MyGrantItem } from '@/lib/api.ts';
import { getErrorMessage } from '@/lib/errors.ts';
import { Alert, AlertDescription } from '../ui/alert';
import { notify } from '@/lib/toast';
import { Skeleton } from '../ui/skeleton';
import { useConnectionSpeed } from '@/lib/useConnectionSpeed.ts';
import { sanitizeFilename } from '@/lib/sanitize.ts';

export default function GrantsPage() {
  const [role, setRole] = useState<'received' | 'granted'>('received');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'pending' | 'expired' | 'revoked' | 'exhausted'>('all');
  const [grants, setGrants] = useState<MyGrantItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<Set<string>>(new Set());
  const { isSlowConnection, effectiveType } = useConnectionSpeed();
  const disableActions = loading || (isSlowConnection && loading);

  async function load() {
    try {
      setLoading(true);
      setError(null);
      const items = await fetchMyGrants(role);
      setGrants(items);
    } catch (e) {
      setError(getErrorMessage(e, 'Failed to load grants'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role]);

  const filteredGrants = useMemo(() => {
    if (statusFilter === 'all') return grants;
    if (statusFilter === 'active') return grants.filter((g) => g.status === 'confirmed');
    return grants.filter((g) => g.status === statusFilter);
  }, [grants, statusFilter]);

  const formatDate = (iso?: string) => {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  };

  const truncate = (str: string, length: number) => {
    if (!str) return '';
    if (str.length <= length) return str;
    return str.slice(0, length / 2) + '...' + str.slice(-length / 2);
  };

  const getStatusBadge = (status: MyGrantItem['status']) => {
    switch (status) {
      case 'confirmed':
        return <Badge className="bg-green-100 text-green-800">Active</Badge>;
      case 'pending':
        return <Badge>Pending</Badge>;
      case 'expired':
        return <Badge variant="secondary">Expired</Badge>;
      case 'revoked':
        return <Badge variant="destructive">Revoked</Badge>;
      case 'exhausted':
        return <Badge variant="secondary">Exhausted</Badge>;
      default:
        return <Badge>{status}</Badge>;
    }
  };

  const isDownloadable = (g: MyGrantItem) => g.status === 'confirmed' && g.usedDownloads < g.maxDownloads;

  const canRevoke = (g: MyGrantItem) => {
    if (role !== 'granted') return false;
    return g.status === 'confirmed' || g.status === 'pending' || g.status === 'queued';
  };

  const handleRevoke = async (capId: string) => {
    if (revoking.has(capId)) return;
    setRevoking((prev) => new Set(prev).add(capId));
    try {
      await revokeGrant(capId);
      notify.success('Grant revoked', { dedupeId: `revoke-${capId}` });
      setGrants((prev) => prev.map((g) => g.capId === capId ? { ...g, status: 'revoked' } : g));
    } catch (e) {
      notify.error(getErrorMessage(e, 'Failed to revoke grant'), { dedupeId: `revoke-err-${capId}` });
    } finally {
      setRevoking((prev) => {
        const next = new Set(prev);
        next.delete(capId);
        return next;
      });
    }
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1>{role === 'received' ? 'Received Grants' : 'My Shared Grants'}</h1>
          <div className="flex items-center gap-2">
            <Select value={role} onValueChange={(v: 'received' | 'granted') => setRole(v)}>
              <SelectTrigger className="w-40" disabled={disableActions}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="received">Received</SelectItem>
                <SelectItem value="granted">Granted</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={load} className="gap-2" disabled={disableActions}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        </div>
        </div>

        <div className="flex items-center gap-4">
          <Select value={statusFilter} onValueChange={(v: 'all' | 'active' | 'pending' | 'expired' | 'revoked' | 'exhausted') => setStatusFilter(v)}>
            <SelectTrigger className="w-48" disabled={disableActions}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="expired">Expired</SelectItem>
              <SelectItem value="revoked">Revoked</SelectItem>
              <SelectItem value="exhausted">Exhausted</SelectItem>
            </SelectContent>
          </Select>

          <div className="flex-1" />
          <div className="text-sm text-gray-600">{filteredGrants.length} item{filteredGrants.length !== 1 ? 's' : ''}</div>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {loading ? (
          <div className="bg-card rounded-lg border border-border p-6 space-y-4">
            <div className="flex items-center gap-3 text-sm text-foreground">
              <div className="h-5 w-5 border-2 border-muted border-b-transparent rounded-full animate-spin" />
              <div>
                <div>Loading grants…</div>
                {isSlowConnection && (
                  <div className="text-xs text-muted-foreground">Slow connection {effectiveType || '3G/2G'} detected, please wait.</div>
                )}
              </div>
            </div>
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          </div>
        ) : filteredGrants.length === 0 ? (
          <div className="text-center py-12 bg-card rounded-lg border border-border">
            <Share2 className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3>No grants</h3>
            <p className="text-muted-foreground">{role === 'received' ? 'When someone shares a file with you, it will appear here' : 'When you share files, they will appear here'}</p>
          </div>
        ) : (
          <div className="bg-card rounded-lg border border-border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{role === 'received' ? 'Grantor' : 'Grantee'}</TableHead>
                  <TableHead>File</TableHead>
                  <TableHead>Cap ID</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead>Downloads</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredGrants.map((g) => (
                  <TableRow key={g.capId}>
                    <TableCell>
                      <code className="text-xs bg-gray-100 px-2 py-1 rounded">{truncate((role === 'received' ? g.grantor : g.grantee) || '', 12)}</code>
                    </TableCell>
                    <TableCell>
                      <Link to={`/files/${g.fileId}`} className="hover:underline">{sanitizeFilename(g.fileName) || truncate(g.fileId, 14)}</Link>
                    </TableCell>
                    <TableCell>
                      <code className="text-xs bg-gray-100 px-2 py-1 rounded">{truncate(g.capId, 16)}</code>
                    </TableCell>
                    <TableCell>{formatDate(g.expiresAt)}</TableCell>
                    <TableCell>
                      <span className={g.usedDownloads >= g.maxDownloads ? 'text-red-600' : ''}>
                        {g.usedDownloads} / {g.maxDownloads}
                      </span>
                    </TableCell>
                    <TableCell>{getStatusBadge(g.status)}</TableCell>
                    <TableCell className="text-right">
                      {role === 'received' ? (
                        isDownloadable(g) ? (
                          <Link to={`/download/${g.capId}`} className={disableActions ? 'pointer-events-none' : ''}>
                            <Button variant="ghost" size="sm" className="gap-1.5" disabled={disableActions}>
                              <Download className="h-3.5 w-3.5" />
                              Download
                            </Button>
                          </Link>
                        ) : (
                          <Button variant="ghost" size="sm" disabled>
                            —
                          </Button>
                        )
                      ) : canRevoke(g) ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="gap-1.5 text-red-600"
                          onClick={() => handleRevoke(g.capId)}
                          disabled={revoking.has(g.capId) || disableActions}
                        >
                          <Ban className="h-3.5 w-3.5" />
                          {revoking.has(g.capId) ? 'Revoking…' : 'Revoke'}
                        </Button>
                      ) : (
                        <Button variant="ghost" size="sm" disabled>
                          —
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </Layout>
  );
}
