import { useState, useMemo, useEffect } from 'react';
import { Link } from 'react-router-dom';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { Skeleton } from '../ui/skeleton';
import { Alert, AlertDescription } from '../ui/alert';
import { Upload, Search, Eye, Share2, CheckCircle2, AlertCircle, Download } from 'lucide-react';
import { fetchMyFiles, type FileListItem } from '../../lib/api';
import { getErrorMessage } from '../../lib/errors';
import { toast } from 'sonner';
import { getFileKey } from '../../lib/fileKey';
import { decryptStream } from '../../lib/cryptoClient';

interface FileItem {
  id: string;
  name: string;
  size: number;
  cid: string;
  checksum: string;
  created: Date;
  mimeType: string;
}

export default function FilesPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('date-desc');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<FileItem[]>([]);

  // Load files from API
  useEffect(() => {
    async function loadFiles() {
      try {
        setIsLoading(true);
        setError(null);
        const data = await fetchMyFiles();

        // Convert API data to UI format (safe date parsing)
        const converted: FileItem[] = data.map((f: FileListItem) => {
          const d = f.created_at ? new Date(f.created_at) : new Date(0);
          const created = isNaN(d.getTime()) ? new Date(0) : d;
          return {
            id: f.id,
            name: f.name,
            size: typeof f.size === 'number' ? f.size : 0,
            cid: f.cid,
            checksum: f.checksum,
            created,
            mimeType: f.mime,
          };
        });
        setFiles(converted);
      } catch (e) {
        setError(getErrorMessage(e, 'Failed to load files'));
      } finally {
        setIsLoading(false);
      }
    }

    loadFiles();
  }, []);

  const filteredFiles = useMemo(() => {
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
      const at = a.created instanceof Date && !isNaN(a.created.getTime()) ? a.created.getTime() : 0;
      const bt = b.created instanceof Date && !isNaN(b.created.getTime()) ? b.created.getTime() : 0;
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
    if (!(date instanceof Date) || isNaN(date.getTime())) return '-';
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
    toast.success(`${label} copied to clipboard`);
  };

  const handleDownloadOwn = async (file: FileItem) => {
    try {
      const gw = (import.meta as unknown as { env?: { VITE_IPFS_PUBLIC_GATEWAY?: string } }).env?.VITE_IPFS_PUBLIC_GATEWAY ?? 'http://localhost:8080';
      const path = file.cid ? `/ipfs/${file.cid}` : '';
      if (!path) throw new Error('CID missing');
      const url = gw.replace(/\/+$/, '') + path;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Failed: ${res.status}`);

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
      a.download = file.name || file.id;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
      toast.success('Download started');
    } catch (e) {
      toast.error(getErrorMessage(e, 'Download failed'));
    }
  };

  if (isLoading) {
    return (
      <Layout>
        <div className="space-y-6">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-12 w-full" />
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
          <Link to="/upload">
            <Button className="gap-2">
              <Upload className="h-4 w-4" />
              Upload File
            </Button>
          </Link>
        </div>

        <div className="flex gap-4 items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              placeholder="Search by name, ID, or CID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
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

        {filteredFiles.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
            <Upload className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3>No files yet</h3>
            <p className="text-gray-600 mb-6">Upload your first file to get started</p>
            <Link to="/upload">
              <Button>Upload File</Button>
            </Link>
          </div>
        ) : (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <Table>
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
                        <div className="truncate">{file.name}</div>
                        <div className="text-xs text-gray-500">{file.mimeType}</div>
                      </div>
                    </TableCell>
                    <TableCell>{formatSize(file.size)}</TableCell>
                    <TableCell>
                      <button type="button" onClick={()=>copyValue(file.cid,'CID')} className="group">
                        <code className="text-xs bg-gray-100 px-2 py-1 rounded inline-flex items-center gap-1">
                          {truncate(file.cid, 16)}
                        </code>
                      </button>
                    </TableCell>
                    <TableCell>
                      <button type="button" onClick={()=>copyValue(file.checksum,'Checksum')} className="group">
                        <code className="text-xs bg-gray-100 px-2 py-1 rounded inline-flex items-center gap-1">
                          {truncate(file.checksum, 20)}
                        </code>
                      </button>
                    </TableCell>
                    <TableCell>{formatDate(file.created)}</TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-2">
                        <Link to={`/files/${file.id}`}>
                          <Button variant="ghost" size="sm" className="gap-1.5">
                            <Eye className="h-3.5 w-3.5" />
                            View
                          </Button>
                        </Link>
                        <Link to={`/files/${file.id}/share`}>
                          <Button variant="ghost" size="sm" className="gap-1.5">
                            <Share2 className="h-3.5 w-3.5" />
                            Share
                          </Button>
                        </Link>
                        <Link to={`/verify/${file.id}`}>
                          <Button variant="ghost" size="sm" className="gap-1.5">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            Verify
                          </Button>
                        </Link>
                        <Button variant="ghost" size="sm" className="gap-1.5" onClick={()=>handleDownloadOwn(file)}>
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
        )}
      </div>
    </Layout>
  );
}
