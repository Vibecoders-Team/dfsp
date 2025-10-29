import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { Button } from '../ui/button';
import { ShieldX, Home, LogIn } from 'lucide-react';

export default function ForbiddenPage() {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="text-center max-w-md">
        <div className="inline-flex items-center justify-center w-20 h-20 bg-red-100 rounded-full mb-6">
          <ShieldX className="h-10 w-10 text-red-600" />
        </div>
        
        <h1 className="mb-2">403 - Access Denied</h1>
        
        <p className="text-gray-600 mb-8">
          You don't have permission to access this resource. This could be because you're not authenticated or don't have the required privileges.
        </p>
        
        <div className="flex gap-3 justify-center">
          {isAuthenticated ? (
            <Link to="/files">
              <Button className="gap-2">
                <Home className="h-4 w-4" />
                Go to Files
              </Button>
            </Link>
          ) : (
            <>
              <Link to="/login">
                <Button className="gap-2">
                  <LogIn className="h-4 w-4" />
                  Login
                </Button>
              </Link>
              <Button
                variant="outline"
                onClick={() => navigate(-1)}
              >
                Go Back
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
