import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../ui/button';
import { Card, CardContent } from '../ui/card';
import { ServerCrash, Home, RefreshCw, Copy } from 'lucide-react';
import { toast } from 'sonner';

export default function ServerErrorPage() {
  const [requestId] = useState(`req_${Date.now()}_${Math.random().toString(36).substring(7)}`);

  const copyRequestId = () => {
    navigator.clipboard.writeText(requestId);
    toast.success('Request ID copied to clipboard');
  };

  const handleReload = () => {
    window.location.reload();
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="text-center max-w-lg w-full">
        <div className="inline-flex items-center justify-center w-20 h-20 bg-red-100 rounded-full mb-6">
          <ServerCrash className="h-10 w-10 text-red-600" />
        </div>
        
        <h1 className="mb-2">500 - Something Went Wrong</h1>
        
        <p className="text-gray-600 mb-8">
          We encountered an unexpected error on our server. Our team has been notified and is working to fix the issue.
        </p>

        <Card className="mb-8">
          <CardContent className="pt-6">
            <div className="text-sm">
              <div className="text-gray-500 mb-2">Request ID</div>
              <div className="flex items-center justify-center gap-2">
                <code className="bg-gray-100 px-3 py-2 rounded text-xs">
                  {requestId}
                </code>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={copyRequestId}
                >
                  <Copy className="h-3.5 w-3.5" />
                </Button>
              </div>
              <p className="text-xs text-gray-500 mt-3">
                Please provide this ID if you contact support
              </p>
            </div>
          </CardContent>
        </Card>
        
        <div className="flex gap-3 justify-center">
          <Button onClick={handleReload} variant="outline" className="gap-2">
            <RefreshCw className="h-4 w-4" />
            Reload Page
          </Button>
          <Link to="/">
            <Button className="gap-2">
              <Home className="h-4 w-4" />
              Go to Home
            </Button>
          </Link>
        </div>

        <div className="mt-8 text-sm text-gray-500">
          <p>If the problem persists, please contact our support team at</p>
          <a href="mailto:support@dfsp.example.com" className="text-blue-600 hover:underline">
            support@dfsp.example.com
          </a>
        </div>
      </div>
    </div>
  );
}
