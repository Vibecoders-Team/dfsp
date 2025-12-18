import type { ReactNode } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider } from './components/AuthContext';
import { ThemeProvider } from './components/ThemeContext';
import { Toaster } from './components/ui/sonner';
import UpdateNotification from './components/UpdateNotification';
import ABICompatibilityCheck from './components/ABICompatibilityCheck';
import LoginPage from './components/pages/LoginPage';
import RegisterPage from './components/pages/RegisterPage';
import React, { Suspense } from 'react';
import { useAuth } from './components/useAuth';
import UnlockPortal from './components/UnlockPortal';
const FilesPage = React.lazy(() => import('./components/pages/FilesPage'));
const FileDetailsPage = React.lazy(() => import('./components/pages/FileDetailsPage'));
const SharePage = React.lazy(() => import('./components/pages/SharePage'));
const GrantsPage = React.lazy(() => import('./components/pages/GrantsPage'));
const DownloadPage = React.lazy(() => import('./components/pages/DownloadPage'));
const UploadPage = React.lazy(() => import('./components/pages/UploadPage'));
const VerifyPage = React.lazy(() => import('./components/pages/VerifyPage'));
const OneTimePageLazy = React.lazy(() => import('./components/pages/OneTimePage'));
const SettingsPage = React.lazy(() => import('./components/pages/SettingsPage'));
const ProfileSettings = React.lazy(() => import('./components/pages/SettingsPage').then(m => ({ default: m.ProfileSettings })));
const KeysSettings = React.lazy(() => import('./components/pages/SettingsPage').then(m => ({ default: m.KeysSettings })));
const AppearanceSettings = React.lazy(() => import('./components/pages/SettingsPage').then(m => ({ default: m.AppearanceSettings })));
const HealthPage = React.lazy(() => import('./components/pages/HealthPage'));
const NotFoundPage = React.lazy(() => import('./components/pages/NotFoundPage'));
const ForbiddenPage = React.lazy(() => import('./components/pages/ForbiddenPage'));
const ServerErrorPage = React.lazy(() => import('./components/pages/ServerErrorPage'));
const TermsPage = React.lazy(() => import('./components/pages/TermsPage'));
const IntentPage = React.lazy(() => import('./components/pages/IntentPage'));
import RestorePage from './components/pages/RestorePage';
import PrivacyPage from './components/pages/PrivacyPage';
import TelegramLinkPage from './components/pages/TelegramLinkPage';
import { MainLandingPage } from './pages/MainLandingPage/MainLandingPage';
import PublicPage from './components/pages/PublicPage';
import { MiniApp, MiniHomePage, MiniFilesPage, MiniGrantsPage, MiniVerifyPage, MiniPublicLinkPage } from './mini/MiniApp';
const _IM = (import.meta as unknown) as { env?: Record<string, string> };
const LANDING_ENABLED = _IM.env?.VITE_LANDING_ENABLED !== 'false';
function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-foreground">Loading...</p>
        </div>
      </div>
    );
  }
  if (!isAuthenticated) {
    const redirect = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?redirect=${redirect}`} replace />;
  }
  return <>{children}</>;
}
function PublicRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-foreground">Loading...</p>
        </div>
      </div>
    );
  }
  if (isAuthenticated) {
    return <Navigate to="/files" replace />;
  }
  return <>{children}</>;
}
function RootRedirect() {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-foreground">Loading...</p>
        </div>
      </div>
    );
  }
  return <Navigate to={isAuthenticated ? "/files" : "/login"} replace />;
}
function AppRoutes() {
  return (
    <>
      <Suspense fallback={<div className="min-h-screen flex items-center justify-center bg-background text-foreground">Loading…</div>}>
        <Routes>
          <Route path="/" element={LANDING_ENABLED ? <MainLandingPage /> : <RootRedirect />} />
          <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
          <Route path="/register" element={<PublicRoute><RegisterPage /></PublicRoute>} />
          <Route path="/files" element={<ProtectedRoute><FilesPage /></ProtectedRoute>} />
          <Route path="/files/:id" element={<ProtectedRoute><FileDetailsPage /></ProtectedRoute>} />
          <Route path="/files/:id/share" element={<ProtectedRoute><SharePage /></ProtectedRoute>} />
          <Route path="/grants" element={<ProtectedRoute><GrantsPage /></ProtectedRoute>} />
          <Route path="/download/:capId" element={<ProtectedRoute><DownloadPage /></ProtectedRoute>} />
          <Route path="/upload" element={<ProtectedRoute><UploadPage /></ProtectedRoute>} />
          <Route path="/verify/:fileId" element={<ProtectedRoute><VerifyPage /></ProtectedRoute>} />
          <Route path="/health" element={<ProtectedRoute><HealthPage /></ProtectedRoute>} />
          {/* Settings nested routes */}
          <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>}>
            <Route path="profile" element={<ProfileSettings />} />
            <Route path="keys" element={<KeysSettings />} />
            <Route path="appearance" element={<AppearanceSettings />} />
            <Route path="*" element={<Navigate to="keys" replace />} />
          </Route>
          <Route path="/404" element={<NotFoundPage />} />
          <Route path="/403" element={<ForbiddenPage />} />
          <Route path="/500" element={<ServerErrorPage />} />
          <Route path="/terms" element={<TermsPage />} />
          <Route path="/intent/:intentId" element={<IntentPage />} />
          <Route path="/restore" element={<PublicRoute><RestorePage /></PublicRoute>} />
          {/* Mini App routes */}
          <Route path="/mini" element={<MiniApp />}>
            <Route index element={<MiniHomePage />} />
            <Route path="files" element={<MiniFilesPage />} />
            <Route path="grants" element={<MiniGrantsPage />} />
            <Route path="verify" element={<MiniVerifyPage />} />
            <Route path="public/:token" element={<MiniPublicLinkPage />} />
            <Route path="*" element={<Navigate to="/mini" replace />} />
          </Route>
          <Route path="/tg/link" element={<ProtectedRoute><TelegramLinkPage /></ProtectedRoute>} />
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="/public/:token" element={<PublicPage />} />
          <Route path="/dl/one-time/:token" element={<OneTimePageLazy />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
      <Toaster richColors position="top-right" closeButton duration={3500} />
      <ABICompatibilityCheck />
      <UpdateNotification />
      <UnlockPortal />
    </>
  );
}
export default function App() {
  return (
    <ThemeProvider>
      <Router>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </Router>
    </ThemeProvider>
  );
}
