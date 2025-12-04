import type { ReactNode } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider } from './components/AuthContext';
import { Toaster } from './components/ui/sonner';
import UpdateNotification from './components/UpdateNotification';
import ABICompatibilityCheck from './components/ABICompatibilityCheck';
import LoginPage from './components/pages/LoginPage';
import RegisterPage from './components/pages/RegisterPage';
import FilesPage from './components/pages/FilesPage';
import FileDetailsPage from './components/pages/FileDetailsPage';
import SharePage from './components/pages/SharePage';
import GrantsPage from './components/pages/GrantsPage';
import DownloadPage from './components/pages/DownloadPage';
import UploadPage from './components/pages/UploadPage';
import VerifyPage from './components/pages/VerifyPage';
import SettingsPage, { ProfileSettings, KeysSettings } from './components/pages/SettingsPage';
import HealthPage from './components/pages/HealthPage';
import NotFoundPage from './components/pages/NotFoundPage';
import ForbiddenPage from './components/pages/ForbiddenPage';
import ServerErrorPage from './components/pages/ServerErrorPage';
import { MiniApp, MiniFilesPage, MiniGrantsPage, MiniHomePage, MiniVerifyPage, MiniPublicLinkPage } from './mini/MiniApp';
import IntentPage from './components/pages/IntentPage';
import UnlockPortal from './components/UnlockPortal';
import { useAuth } from './components/useAuth';
import TermsPage from './components/pages/TermsPage';
import RestorePage from './components/pages/RestorePage';
import PrivacyPage from './components/pages/PrivacyPage';
import TelegramLinkPage from './components/pages/TelegramLinkPage';
import { MainLandingPage } from './pages/MainLandingPage/MainLandingPage';
import PublicPage from './components/pages/PublicPage.tsx';

const LANDING_ENABLED = (import.meta as any).env?.VITE_LANDING_ENABLED !== 'false';

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();
  
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto"></div>
          <p className="mt-4">Loading...</p>
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
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto"></div>
          <p className="mt-4">Loading...</p>
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
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto"></div>
          <p className="mt-4">Loading...</p>
        </div>
      </div>
    );
  }
  
  return <Navigate to={isAuthenticated ? "/files" : "/login"} replace />;
}

function AppRoutes() {
  return (
    <>
      <Routes>
        {/* Новый корневой маршрут: лендинг */}
        <Route path="/" element={LANDING_ENABLED ? <MainLandingPage /> : <RootRedirect />} />
        {/* Старая логика редиректа доступна по "/app" для отката */}
        <Route path="/app" element={<RootRedirect />} />
        <Route
          path="/login"
          element={
            <PublicRoute children={<LoginPage />} />
          }
        />
        <Route
          path="/register"
          element={
            <PublicRoute children={<RegisterPage />} />
          }
        />
        <Route
          path="/files"
          element={
            <ProtectedRoute children={<FilesPage />} />
          }
        />
        <Route
          path="/files/:id"
          element={
            <ProtectedRoute children={<FileDetailsPage />} />
          }
        />
        <Route
          path="/files/:id/share"
          element={
            <ProtectedRoute children={<SharePage />} />
          }
        />
        <Route
          path="/grants"
          element={
            <ProtectedRoute children={<GrantsPage />} />
          }
        />
        <Route
          path="/download/:capId"
          element={
            <ProtectedRoute children={<DownloadPage />} />
          }
        />
        <Route
          path="/upload"
          element={
            <ProtectedRoute children={<UploadPage />} />
          }
        />
        <Route
          path="/verify/:fileId"
          element={
            <ProtectedRoute children={<VerifyPage />} />
          }
        />
        {/* Settings nested routes */}
        <Route
          path="/settings"
          element={
            <ProtectedRoute children={<SettingsPage />} />
          }
        >
          <Route index element={<KeysSettings />} />
          <Route path="profile" element={<ProfileSettings />} />
          <Route path="keys" element={<KeysSettings />} />
          <Route path="*" element={<Navigate to="keys" replace />} />
        </Route>
        <Route
          path="/health"
          element={
            <ProtectedRoute children={<HealthPage />} />
          }
        />
        <Route path="/404" element={<NotFoundPage />} />
        <Route path="/403" element={<ForbiddenPage />} />
        <Route path="/500" element={<ServerErrorPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/intent/:intentId" element={<IntentPage />} />
        <Route
          path="/restore"
          element={<PublicRoute children={<RestorePage />} />}
        />
        <Route path="/mini" element={<MiniApp />}>
          <Route index element={<MiniHomePage />} />
          <Route path="files" element={<MiniFilesPage />} />
          <Route path="grants" element={<MiniGrantsPage />} />
          <Route path="verify" element={<MiniVerifyPage />} />
          <Route path="public/:token" element={<MiniPublicLinkPage />} />
          <Route path="*" element={<Navigate to="/mini" replace />} />
        </Route>
        <Route
          path="/tg/link"
          element={
            <ProtectedRoute children={<TelegramLinkPage />} />
          }
        />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/public/:token" element={<PublicPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <Toaster richColors position="top-right" closeButton duration={3500} />
      <ABICompatibilityCheck />
      <UpdateNotification />
      <UnlockPortal />
    </>
  );
}

export default function App() {
  return (
    <Router>
      <AuthProvider children={<AppRoutes />} />
    </Router>
  );
}
