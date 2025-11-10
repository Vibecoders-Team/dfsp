import { Link, useLocation } from 'react-router-dom';
import { useAuth } from './useAuth';
import { Button } from './ui/button';
import { FileText, Key, LogOut, Settings, Share2 } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';
import AgentSelector from './AgentSelector';
import KeyLockIndicator from './KeyLockIndicator';

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const { user, logout } = useAuth();
  const location = useLocation();

  const isActive = (path: string) => {
    return location.pathname === path || location.pathname.startsWith(path + '/');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-8">
              <Link to="/files" className="flex items-center gap-2">
                <Key className="h-6 w-6 text-blue-600" />
                <span className="text-xl">DFSP</span>
              </Link>
              
              <nav className="flex gap-1">
                <Link to="/files">
                  <Button
                    variant={isActive('/files') ? 'secondary' : 'ghost'}
                    size="sm"
                    className="gap-2"
                  >
                    <FileText className="h-4 w-4" />
                    Files
                  </Button>
                </Link>
                <Link to="/grants">
                  <Button
                    variant={isActive('/grants') ? 'secondary' : 'ghost'}
                    size="sm"
                    className="gap-2"
                  >
                    <Share2 className="h-4 w-4" />
                    Grants
                  </Button>
                </Link>
              </nav>
            </div>

            <div className="flex items-center gap-4">
              <div className="text-sm text-gray-600">
                {user?.displayName && <span className="mr-2">{user.displayName}</span>}
                <Link to="/settings/profile" className="text-xs text-blue-600 hover:underline" title="Open profile">
                  {user?.address.slice(0, 6)}...{user?.address.slice(-4)}
                </Link>
              </div>
              <KeyLockIndicator />
              <AgentSelector compact={!!user} />

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm">
                    <Settings className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuLabel>Settings</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <Link to="/settings/profile">Profile</Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link to="/settings/keys">Keys</Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link to="/settings/security">Security</Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={logout} className="text-red-600">
                    <LogOut className="h-4 w-4 mr-2" />
                    Logout
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  );
}
