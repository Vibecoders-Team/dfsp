import { Link, useLocation } from 'react-router-dom';
import { useAuth } from './useAuth';
import { useTheme } from './ThemeContext';
import { Button } from './ui/button';
import { FileText, Key, LogOut, Settings, Share2, Sun, Moon } from 'lucide-react';
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
import type * as React from "react";

interface LayoutProps {
  children: React.ReactNode;
  publicDoc?: boolean; // новый флаг для публичных документов (Terms / Privacy)
}

export default function Layout({ children, publicDoc }: LayoutProps) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const { resolvedTheme, setTheme, theme } = useTheme();

  const toggleTheme = () => {
    if (theme === 'light') setTheme('dark');
    else if (theme === 'dark') setTheme('system');
    else setTheme('light');
  };

  const isActive = (path: string) => {
    const p = location.pathname;
    if (path === '/files') {
      return p === '/files' || p.startsWith('/files/') || p === '/upload' || p.startsWith('/verify/');
    }
    if (path === '/grants') {
      return p === '/grants' || p.startsWith('/download/');
    }
    return p === path || p.startsWith(path + '/');
  };

  if (publicDoc) {
    return (
      <div className="min-h-screen bg-background">
        <header className="bg-card border-b border-border">
          <div className="max-w-[88rem] mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-end">
            <Link to="/register">
              <Button variant="outline" size="sm">Back to register</Button>
            </Link>
          </div>
        </header>
        <main className="max-w-[88rem] mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-card border-b border-border">
        <div className="max-w-[88rem] mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-8">
              <Link to="/files" className="flex items-center gap-2">
                <Key className="h-6 w-6 text-primary" />
                <span className="text-xl font-semibold text-foreground">DFSP</span>
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
              <div className="text-sm text-muted-foreground">
                {user?.displayName && <span className="mr-2">{user.displayName}</span>}
                <Link to="/settings/profile" className="text-xs text-primary hover:underline" title="Open profile">
                  {user?.address.slice(0, 6)}...{user?.address.slice(-4)}
                </Link>
              </div>
              <KeyLockIndicator />
              <AgentSelector compact={!!user} />

              {/* Theme Toggle Button */}
              <Button
                variant="ghost"
                size="sm"
                onClick={toggleTheme}
                title={`Theme: ${theme}`}
              >
                {resolvedTheme === 'dark' ? (
                  <Moon className="h-4 w-4" />
                ) : (
                  <Sun className="h-4 w-4" />
                )}
              </Button>

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
                    <Link to="/settings/appearance">Appearance</Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={logout} className="text-destructive">
                    <LogOut className="h-4 w-4 mr-2" />
                    Logout
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-[88rem] mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  );
}
