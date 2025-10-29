import { Link } from 'react-router-dom';
import { Button } from '../ui/button';
import { FileQuestion, Home } from 'lucide-react';

export default function NotFoundPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="text-center max-w-md">
        <div className="inline-flex items-center justify-center w-20 h-20 bg-gray-100 rounded-full mb-6">
          <FileQuestion className="h-10 w-10 text-gray-400" />
        </div>
        
        <h1 className="mb-2">404 - Page Not Found</h1>
        
        <p className="text-gray-600 mb-8">
          The page you're looking for doesn't exist or has been moved.
        </p>
        
        <Link to="/">
          <Button className="gap-2">
            <Home className="h-4 w-4" />
            Go to Home
          </Button>
        </Link>
      </div>
    </div>
  );
}
