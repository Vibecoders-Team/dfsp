import { useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Layout from '../Layout';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../ui/card';
import { Alert, AlertDescription } from '../ui/alert';
import { Badge } from '../ui/badge';
import { ArrowLeft, CheckCircle2, XCircle, AlertCircle, Upload } from 'lucide-react';
import { fetchMeta } from '@/lib/api.ts';
import { getErrorMessage } from '@/lib/errors.ts';
import type * as React from "react";
import { sanitizeFilename, safeText } from '@/lib/sanitize.ts';

type VerifyState = 'idle' | 'loading' | 'match' | 'mismatch' | 'not_found' | 'error';

interface OnChainData {
  cid?: string;
  checksum?: string;
  fileId: string;
  name?: string;
  size?: number;
  createdAt?: number;
  mime?: string;
}

interface LocalCheckData {
  checksumSha256: string;
  checksumKeccak: string;
  fileName: string;
  size: number;
}

function ab2u8(buf: ArrayBuffer) {
  return new Uint8Array(buf);
}

async function sha256Hex(buf: ArrayBuffer): Promise<string> {
  const hash = await crypto.subtle.digest('SHA-256', buf);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

async function keccakHex(buf: ArrayBuffer): Promise<string> {
  const { keccak256 } = await import('ethers');
  const hex = keccak256(ab2u8(buf)); // "0x..."
  return hex.slice(2);
}

export default function VerifyPage() {
  const { fileId } = useParams();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<VerifyState>('idle');
  const [onChainData, setOnChainData] = useState<OnChainData | null>(null);
  const [localCheckData, setLocalCheckData] = useState<LocalCheckData | null>(null);
  const [error, setError] = useState('');
  const [isCalculating, setIsCalculating] = useState(false);
  const [showMismatchDetails, setShowMismatchDetails] = useState(false);

  const checkOnChain = async () => {
    setState('loading');
    setError('');

    try {
      if (!fileId) throw new Error('Missing fileId');
      const meta = await fetchMeta(fileId);
      const oc: OnChainData = {
        fileId,
        cid: meta.cid || undefined,
        checksum: meta.checksum || undefined,
        name: meta.name || undefined,
        size: meta.size || undefined,
        createdAt: meta.createdAt || undefined,
        mime: meta.mime || undefined,
      };
      setOnChainData(oc);

      // If we have local data, compare keccak with on-chain checksum
      if (localCheckData && oc.checksum) {
        const match = localCheckData.checksumKeccak.toLowerCase() === oc.checksum.replace(/^0x/, '').toLowerCase();
        setState(match ? 'match' : 'mismatch');
        setShowMismatchDetails(false);
      } else {
        setState('idle');
      }
    } catch (err) {
      setState('error');
      setError(getErrorMessage(err, 'Failed to fetch on-chain metadata'));
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const file = files[0];
    setIsCalculating(true);
    setError('');

    try {
      const buf = await file.arrayBuffer();
      const s1 = await sha256Hex(buf);
      const s2 = await keccakHex(buf);

      const local: LocalCheckData = {
        checksumSha256: s1,
        checksumKeccak: s2,
        fileName: file.name,
        size: file.size,
      };
      setLocalCheckData(local);

      // If we have on-chain data, compare
      if (onChainData?.checksum) {
        const match = s2.toLowerCase() === onChainData.checksum.replace(/^0x/, '').toLowerCase();
        setState(match ? 'match' : 'mismatch');
        setShowMismatchDetails(false);
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to calculate checksum'));
    } finally {
      setIsCalculating(false);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  return (
    <Layout>
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/files')}
            className="gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          <h1>Verify File</h1>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>File ID</CardTitle>
            <CardDescription>Verifying file with ID: {fileId}</CardDescription>
          </CardHeader>
          <CardContent onKeyDown={(e: React.KeyboardEvent) => { if (e.key === 'Enter' && !isCalculating && state !== 'loading') { e.preventDefault(); checkOnChain(); } }}>
            <div className="flex gap-3">
              <code className="flex-1 bg-muted px-3 py-2 rounded text-sm">
                {fileId}
              </code>
              <Button onClick={checkOnChain} disabled={state === 'loading'}>
                {state === 'loading' ? 'Checking...' : 'Check On-Chain'}
              </Button>
            </div>
          </CardContent>
        </Card>

        {onChainData && (
          <Card>
            <CardHeader>
              <CardTitle>On-Chain Data</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {onChainData.name && (
                  <div>
                    <div className="text-sm text-muted-foreground mb-1">File Name</div>
                    <div>{safeText(onChainData.name)}</div>
                  </div>
                )}
                <div>
                  <div className="text-sm text-muted-foreground mb-1">CID</div>
                  <code className="text-sm bg-muted px-2 py-1 rounded block">
                    {onChainData.cid || '-'}
                  </code>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground mb-1">Checksum (keccak256)</div>
                  <code className="text-sm bg-muted px-2 py-1 rounded block break-all">
                    {onChainData.checksum || '-'}
                  </code>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Local File Verification</CardTitle>
            <CardDescription>
              Upload a local file to verify its checksum matches the on-chain data
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <input
                ref={fileInputRef}
                type="file"
                onChange={handleFileSelect}
                className="hidden"
                id="verify-file-input"
              />
              <Button
                onClick={() => fileInputRef.current?.click()}
                disabled={isCalculating}
                variant="outline"
                className="gap-2"
              >
                <Upload className="h-4 w-4" />
                {isCalculating ? 'Calculating...' : 'Choose Local File'}
              </Button>
            </div>

            {localCheckData && (
              <div className="p-4 bg-muted/50 rounded-lg space-y-3">
                <div>
                  <div className="text-sm text-muted-foreground mb-1">File Name</div>
                  <div>{sanitizeFilename(localCheckData.fileName)}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground mb-1">Size</div>
                  <div>{formatBytes(localCheckData.size)}</div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground mb-1">SHA-256</div>
                  <code className="text-sm bg-muted px-2 py-1 rounded block break-all">
                    {localCheckData.checksumSha256}
                  </code>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground mb-1">Keccak256</div>
                  <code className="text-sm bg-muted px-2 py-1 rounded block break-all">
                    {localCheckData.checksumKeccak}
                  </code>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {state === 'match' && (
          <Alert className="border-green-200 bg-green-50 dark:bg-green-900/20 dark:border-green-900">
            <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
            <AlertDescription className="text-green-800 dark:text-green-200">
              <div className="flex items-center justify-between gap-3">
                <span>Verification successful! Checksums match.</span>
                <Badge className="bg-green-600 text-white dark:bg-green-500 dark:text-white">Match</Badge>
              </div>
            </AlertDescription>
          </Alert>
        )}

        {state === 'mismatch' && (
          <Alert className="border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-900">
            <XCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
            <AlertDescription className="text-red-800 dark:text-red-200">
              <div className="flex items-center justify-between gap-3">
                <span>Verification failed! Checksums do not match.</span>
                <Badge className="bg-red-600 text-white dark:bg-red-500 dark:text-white">Mismatch</Badge>
              </div>
              {onChainData?.checksum && localCheckData?.checksumKeccak && (
                <div className="mt-3 space-y-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-2"
                    onClick={() => setShowMismatchDetails((v) => !v)}
                  >
                    {showMismatchDetails ? 'Hide details' : 'Show details'}
                  </Button>
                  {showMismatchDetails && (
                    <div className="space-y-2 rounded-md border border-destructive/30 bg-card p-3 text-sm text-foreground">
                      <div>
                        <div className="text-xs text-muted-foreground mb-1">On-chain checksum</div>
                        <code className="block break-all bg-muted p-2 rounded">{onChainData.checksum}</code>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground mb-1">Local keccak256</div>
                        <code className="block break-all bg-muted p-2 rounded">
                          {localCheckData.checksumKeccak}
                        </code>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </AlertDescription>
          </Alert>
        )}

        {state === 'error' && error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {state === 'match' && onChainData && localCheckData && (
          <Card>
            <CardHeader>
              <CardTitle>Comparison</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-sm text-muted-foreground mb-2">On-Chain Checksum</div>
                    <code className="text-xs bg-muted p-2 rounded block break-all">
                      {onChainData.checksum || '-'}
                    </code>
                  </div>
                  <div>
                    <div className="text-sm text-muted-foreground mb-2">Local Keccak256</div>
                    <code className="text-xs bg-muted p-2 rounded block break-all">
                      {localCheckData.checksumKeccak}
                    </code>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
}
