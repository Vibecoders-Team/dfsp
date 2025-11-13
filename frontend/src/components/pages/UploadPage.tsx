import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../Layout';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Alert, AlertDescription } from '../ui/alert';
import { Progress } from '../ui/progress';
import { Upload, File, X, AlertCircle, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
import { getErrorMessage } from '../../lib/errors';
import { encryptFile, keccak } from '../../lib/cryptoClient';
import { storeEncrypted } from '../../lib/api';
import { getOrCreateFileKey, renameFileKey } from '../../lib/fileKey';

type UploadState = 'empty' | 'encrypting' | 'uploading' | 'registering' | 'done' | 'error';

interface UploadedFile {
  file: File;
  name: string;
  size: number;
  mimeType: string;
  description?: string;
}

export default function UploadPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<UploadState>('empty');
  const [uploadedFile, setUploadedFile] = useState<UploadedFile | null>(null);
  const [description, setDescription] = useState('');
  const [progress, setProgress] = useState(0);
  const [uploadSpeed, setUploadSpeed] = useState(0);
  const [error, setError] = useState('');
  const [isDragging, setIsDragging] = useState(false);

  const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100MB

  const handleFileSelect = (file: File) => {
    if (file.size > MAX_FILE_SIZE) {
      setError(`File size exceeds the maximum limit of ${formatBytes(MAX_FILE_SIZE)}`);
      setState('error');
      return;
    }

    setUploadedFile({
      file,
      name: file.name,
      size: file.size,
      mimeType: file.type || 'application/octet-stream',
      description: ''
    });
    setState('empty');
    setError('');
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleSubmit = async () => {
    if (!uploadedFile) return;

    try {
      setError('');
      setState('encrypting');
      setProgress(0);

      // Вычисляем idHex (sha256 plaintext) и checksum (keccak plaintext) до шифрования
      const buf = await uploadedFile.file.arrayBuffer();
      const sha = await crypto.subtle.digest('SHA-256', buf);
      const idHex = '0x' + Array.from(new Uint8Array(sha)).map(b=>b.toString(16).padStart(2,'0')).join('');
      const kch = (await keccak(new Uint8Array(buf))).replace(/^0x/, '');

      // Генерируем/получаем K_file, привязывая к idHex
      const K_file = getOrCreateFileKey(idHex);

      // Шифруем исходный файл
      const enc = await encryptFile(uploadedFile.file, K_file, 64*1024, (done, total) => setProgress(Math.round((done/total)*100)));

      setState('uploading');
      setProgress(0);

      const start = performance.now();
      const res = await storeEncrypted(enc.blob, { idHex, checksum: kch, plainSize: uploadedFile.size, filename: uploadedFile.name + '.enc' });
      const elapsedMs = performance.now() - start;
      // Если бэкенд изменил id (например, коллизия персонифицирована), перенесём ключ
      if (res.id_hex && res.id_hex !== idHex) {
        renameFileKey(idHex, res.id_hex);
      }

      setProgress(100);
      const speed = uploadedFile.size / (elapsedMs / 1000);
      setUploadSpeed(speed);

      setState('done');
      toast.success('File uploaded successfully!', { description: `File ID: ${res.id_hex.slice(0,10)}...` });

      setTimeout(() => { navigate('/files'); }, 1500);
    } catch (err) {
      setState('error');
      const errorMsg = getErrorMessage(err, 'Upload failed');
      setError(errorMsg);
      toast.error('Upload failed', { description: errorMsg });
    }
  };

  const removeFile = () => {
    setUploadedFile(null);
    setState('empty');
    setError('');
    setProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const formatSpeed = (bytesPerSecond: number) => {
    return formatBytes(bytesPerSecond) + '/s';
  };

  const isProcessing = state === 'encrypting' || state === 'uploading' || state === 'registering';

  return (
    <Layout>
      <div className="max-w-2xl mx-auto space-y-6">
        <div>
          <h1>Upload File</h1>
          <p className="text-gray-600">
            Encrypt and upload your file to IPFS
          </p>
        </div>

        {state === 'empty' && !uploadedFile && (
          <Card>
            <CardContent className="pt-6">
              <div
                className={`border-2 border-dashed rounded-lg p-12 text-center transition-colors ${
                  isDragging
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-300 hover:border-gray-400'
                }`}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
              >
                <Upload className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600 mb-4">
                  Drag and drop your file here, or click to browse
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  onChange={handleInputChange}
                  className="hidden"
                  id="file-input"
                />
                <Button
                  onClick={() => fileInputRef.current?.click()}
                  variant="outline"
                >
                  Choose File
                </Button>
                <p className="text-xs text-gray-500 mt-4">
                  Maximum file size: {formatBytes(MAX_FILE_SIZE)}
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {uploadedFile && (
          <Card>
            <CardHeader>
              <CardTitle>File Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div className="flex items-center gap-3">
                  <File className="h-8 w-8 text-blue-600" />
                  <div>
                    <div>{uploadedFile.name}</div>
                    <div className="text-sm text-gray-500">
                      {formatBytes(uploadedFile.size)}
                    </div>
                  </div>
                </div>
                {!isProcessing && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={removeFile}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>File Name</Label>
                  <Input
                    value={uploadedFile.name}
                    disabled
                  />
                </div>

                <div className="space-y-2">
                  <Label>Size</Label>
                  <Input
                    value={formatBytes(uploadedFile.size)}
                    disabled
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label>MIME Type</Label>
                <Input
                  value={uploadedFile.mimeType}
                  disabled
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description (Optional)</Label>
                <Textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={isProcessing}
                  placeholder="Add a description for this file..."
                  rows={3}
                />
              </div>
            </CardContent>
          </Card>
        )}

        {state === 'encrypting' && (
          <Card>
            <CardHeader>
              <CardTitle>Encrypting</CardTitle>
              <CardDescription>Encrypting file before upload...</CardDescription>
            </CardHeader>
            <CardContent>
              <Progress value={0} className="mb-2" />
              <div className="text-sm text-gray-600">0%</div>
            </CardContent>
          </Card>
        )}

        {state === 'uploading' && (
          <Card>
            <CardHeader>
              <CardTitle>Uploading to IPFS</CardTitle>
              <CardDescription>Uploading encrypted file using multiple streams...</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Progress value={progress} />
              <div className="flex justify-between text-sm text-gray-600">
                <span>{Math.round(progress)}% complete</span>
                <span>{formatSpeed(uploadSpeed)}</span>
              </div>
            </CardContent>
          </Card>
        )}

        {state === 'registering' && (
          <Card>
            <CardHeader>
              <CardTitle>Registering On-Chain</CardTitle>
              <CardDescription>Submitting metadata transaction...</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-gray-900"></div>
                <span className="text-sm text-gray-600">Waiting for confirmation...</span>
              </div>
            </CardContent>
          </Card>
        )}

        {state === 'done' && (
          <Alert>
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            <AlertDescription className="text-green-800">
              File successfully uploaded and registered on chain! Redirecting...
            </AlertDescription>
          </Alert>
        )}

        {state === 'error' && error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {uploadedFile && state !== 'done' && (
          <div className="flex gap-3 justify-end">
            <Button
              variant="outline"
              onClick={() => navigate('/files')}
              disabled={isProcessing}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={isProcessing || !uploadedFile}
              className="gap-2"
            >
              {isProcessing ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                  Processing...
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4" />
                  Upload & Register
                </>
              )}
            </Button>
          </div>
        )}
      </div>
    </Layout>
  );
}
