import { useState, useMemo, useEffect, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import Layout from '../Layout';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';
// import { TableVirtuoso } from 'react-virtuoso'; // Временно отключено для тестирования
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { Skeleton } from '../ui/skeleton';
import { Alert, AlertDescription } from '../ui/alert';
import { Upload, Search, Eye, Share2, CheckCircle2, AlertCircle, Download, RefreshCw } from 'lucide-react';
import { fetchMyFiles, type FileListItem } from '@/lib/api.ts';
import { getErrorMessage } from '@/lib/errors.ts';
import { notify } from '@/lib/toast';
import { getFileKey } from '@/lib/fileKey.ts';
import { decryptStream } from '@/lib/cryptoClient.ts';
import { sanitizeFilename, parseContentDisposition } from '@/lib/sanitize.ts';
import { useConnectionSpeed } from '@/lib/useConnectionSpeed.ts';

interface FileItem {
  id: string;
  name: string;
  size: number;
  cid: string;
  checksum: string;
  created: Date;
  mimeType: string;
  safeName: string;
}

export default function FilesPage() {
  const location = useLocation();
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('date-desc');
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<FileItem[]>([]);
  const { isSlowConnection, effectiveType } = useConnectionSpeed();
  const isFirstLoadRef = useRef(true);

  // Debug: track mount/unmount
  useEffect(() => {
    console.log('[FilesPage] MOUNTED');
    return () => console.log('[FilesPage] UNMOUNTED');
  }, []);

  // Load files from API
  const loadFiles = async (isRefresh = false) => {
    try {
      if (isRefresh) {
        setIsRefreshing(true);
      } else {
        setIsLoading(true);
      }
      setError(null);
      console.log('[FilesPage] Loading files...');
      const data = await fetchMyFiles();
      console.log('[FilesPage] Loaded files:', data.length);

      // Convert API data to UI format (safe date parsing)
      const converted: FileItem[] = data.map((f: FileListItem) => {
        const d = f.created_at ? new Date(f.created_at) : new Date(0);
        const created = isNaN(d.getTime()) ? new Date(0) : d;
        const safeName = sanitizeFilename(f.name);
        return {
          id: f.id,
          name: f.name,
          size: f.size ?? 0,
          cid: f.cid,
          checksum: f.checksum,
          created,
          mimeType: f.mime,
          safeName,
        };
      });
      console.log('[FilesPage] Converted files:', converted.map(f => ({ id: f.id.slice(0, 10), name: f.name })));
      setFiles(converted);
      console.log('[FilesPage] State updated with', converted.length, 'files');
    } catch (e) {
      console.error('[FilesPage] Failed to load files:', e);
      setError(getErrorMessage(e, 'Failed to load files'));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    console.log('[FilesPage] useEffect triggered, location.key:', location.key, 'isFirstLoad:', isFirstLoadRef.current);
    // При первой загрузке - полный loading, при последующих - refresh
    loadFiles(!isFirstLoadRef.current);
    isFirstLoadRef.current = false;
  }, [location.key]);

  // Log files state changes
  useEffect(() => {
    console.log('[FilesPage] files state changed:', files.length, 'files:', files.map(f => f.id.slice(0, 10)));
  }, [files]);

  const filteredFiles = useMemo(() => {
    console.log('[FilesPage] Recalculating filteredFiles, input files.length:', files.length);
    let filtered = [...files];

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (file) =>
          file.name.toLowerCase().includes(query) ||
          file.id.toLowerCase().includes(query) ||
          file.cid.toLowerCase().includes(query)
      );
    }

    filtered.sort((a, b) => {
      const at = !isNaN(a.created.getTime()) ? a.created.getTime() : 0;
      const bt = !isNaN(b.created.getTime()) ? b.created.getTime() : 0;
      switch (sortBy) {
        case 'date-desc':
          return bt - at;
        case 'date-asc':
          return at - bt;
        case 'name-asc':
          return a.name.localeCompare(b.name);
        case 'name-desc':
          return b.name.localeCompare(a.name);
        case 'size-desc':
          return (b.size || 0) - (a.size || 0);
        case 'size-asc':
          return (a.size || 0) - (b.size || 0);
        default:
          return 0;
      }
    });

    console.log('[FilesPage] Final filtered files:', filtered.length, 'IDs:', filtered.map(f => f.id.slice(0, 10)));
    return filtered;
  }, [files, searchQuery, sortBy]);

  const formatSize = (bytes: number) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.min(sizes.length - 1, Math.floor(Math.log(bytes) / Math.log(k)));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (date: Date) => {
    if (isNaN(date.getTime())) return '-';
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  const truncate = (str: string, length: number) => {
    if (!str) return '';
    if (str.length <= length) return str;
    return str.slice(0, Math.floor(length / 2)) + '...' + str.slice(-Math.floor(length / 2));
  };

  const copyValue = (value: string, label: string) => {
    if (!value) return;
    navigator.clipboard.writeText(value);
    notify.success(`${label} copied to clipboard`, { dedupeId: `copy-${label}-${value}` });
  };

  const handleDownloadOwn = async (file: FileItem) => {
    try {
      const gw =
        (import.meta as unknown as { env?: { VITE_IPFS_PUBLIC_GATEWAY?: string } }).env?.VITE_IPFS_PUBLIC_GATEWAY
        ?? 'https://ipfs.dfsp.app';
      const path = file.cid ? `/ipfs/${file.cid}` : '';
      if (!path) throw new Error('CID missing');
      const url = gw.replace(/\/+$/, '') + path;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Failed: ${res.status}`);

      // Try to get filename from Content-Disposition header
      const contentDisposition = res.headers.get('Content-Disposition');
      const headerFilename = parseContentDisposition(contentDisposition);
      const finalFilename = headerFilename || file.name;

      // Попробуем расшифровать, если есть K_file
      const k = getFileKey(file.id);
      let blob: Blob;
      if (k) {
        try {
          blob = await decryptStream(res, k);
        } catch (e) {
          console.warn('Owner decrypt failed, fallback to raw:', e);
          blob = await res.blob();
        }
      } else {
        blob = await res.blob();
      }

      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = sanitizeFilename(finalFilename) || file.id;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
      notify.success('Download started', { dedupeId: `dl-${file.id}` });
    } catch (e) {
      notify.error(getErrorMessage(e, 'Download failed'), { dedupeId: `dl-err-${file.id}` });
    }
  };

  if (isLoading) {
    return (
      <Layout>
        <div className="space-y-6">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-12 w-full" />
          {isSlowConnection && (
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <div className="h-4 w-4 border-2 border-gray-300 border-b-transparent rounded-full animate-spin" />
              <span>Slow connection {effectiveType || '3G/2G'} — loading may take a bit longer</span>
            </div>
          )}
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1>My Files</h1>
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="gap-2"
              onClick={() => loadFiles(true)}
              disabled={isRefreshing}
            >
              <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Link to="/upload" className={isLoading && isSlowConnection ? 'pointer-events-none' : ''}>
              <Button className="gap-2" disabled={isLoading && isSlowConnection}>
                <Upload className="h-4 w-4" />
                Upload File
              </Button>
            </Link>
          </div>
        </div>

        <div className="flex gap-4 items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              placeholder="Search by name, ID, or CID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
              aria-label="Search files"
            />
          </div>
          <Select value={sortBy} onValueChange={setSortBy}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="date-desc">Date (Newest)</SelectItem>
              <SelectItem value="date-asc">Date (Oldest)</SelectItem>
              <SelectItem value="name-asc">Name (A-Z)</SelectItem>
              <SelectItem value="name-desc">Name (Z-A)</SelectItem>
              <SelectItem value="size-desc">Size (Largest)</SelectItem>
              <SelectItem value="size-asc">Size (Smallest)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* render */}

        {filteredFiles.length === 0 && !isLoading ? (
          <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
            <Upload className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3>No files yet</h3>
            <p className="text-gray-600 mb-6">Upload your first file to get started</p>
            <Link to="/upload">
              <Button>Upload File</Button>
            </Link>
          </div>
        ) : filteredFiles.length > 0 ? (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <div style={{ maxHeight: '70vh', overflow: 'auto' }}>
              <Table className="border-collapse" aria-label="Files table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Size</TableHead>
                    <TableHead>CID</TableHead>
                    <TableHead>Checksum</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredFiles.map((file) => (
                    <TableRow key={file.id}>
                      <TableCell>
                        <div className="max-w-xs">
                          <div className="truncate">{file.safeName}</div>
                          <div className="text-xs text-gray-500">{file.mimeType}</div>
                        </div>
                      </TableCell>
                      <TableCell>{formatSize(file.size)}</TableCell>
                      <TableCell>
                        <button type="button" onClick={()=>copyValue(file.cid,'CID')} className="group" aria-label="Copy CID">
                          <code className="text-xs bg-gray-100 px-2 py-1 rounded inline-flex items-center gap-1">
                            {truncate(file.cid, 16)}
                          </code>
                        </button>
                      </TableCell>
                      <TableCell>
                        <button type="button" onClick={()=>copyValue(file.checksum,'Checksum')} className="group" aria-label="Copy checksum">
                          <code className="text-xs bg-gray-100 px-2 py-1 rounded inline-flex items-center gap-1">
                            {truncate(file.checksum, 20)}
                          </code>
                        </button>
                      </TableCell>
                      <TableCell>{formatDate(file.created)}</TableCell>
                      <TableCell>
                        <div className="flex items-center justify-end gap-2">
                          <Link to={`/files/${file.id}`} className={isLoading && isSlowConnection ? 'pointer-events-none' : ''}>
                            <Button variant="ghost" size="sm" className="gap-1.5" disabled={isLoading && isSlowConnection} aria-label={`View ${file.safeName}`}>
                              <Eye className="h-3.5 w-3.5" />
                              View
                            </Button>
                          </Link>
                          <Link to={`/files/${file.id}/share`} className={isLoading && isSlowConnection ? 'pointer-events-none' : ''}>
                            <Button variant="ghost" size="sm" className="gap-1.5" disabled={isLoading && isSlowConnection} aria-label={`Share ${file.safeName}`}>
                              <Share2 className="h-3.5 w-3.5" />
                              Share
                            </Button>
                          </Link>
                          <Link to={`/verify/${file.id}`} className={isLoading && isSlowConnection ? 'pointer-events-none' : ''}>
                            <Button variant="ghost" size="sm" className="gap-1.5" disabled={isLoading && isSlowConnection} aria-label={`Verify ${file.safeName}`}>
                              <CheckCircle2 className="h-3.5 w-3.5" />
                              Verify
                            </Button>
                          </Link>
                          <Button variant="ghost" size="sm" className="gap-1.5" onClick={()=>handleDownloadOwn(file)} disabled={isLoading && isSlowConnection} aria-label={`Download ${file.safeName}`}>
                            <Download className="h-3.5 w-3.5" />
                            Download
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        ) : null}
      </div>
    </Layout>
  );
}
