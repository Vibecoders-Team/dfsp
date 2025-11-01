import type { ReactNode } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './components/AuthContext';
import { Toaster } from './components/ui/sonner';
import LoginPage from './components/pages/LoginPage';
import RegisterPage from './components/pages/RegisterPage';
import FilesPage from './components/pages/FilesPage';
import FileDetailsPage from './components/pages/FileDetailsPage';
import SharePage from './components/pages/SharePage';
import GrantsPage from './components/pages/GrantsPage';
import DownloadPage from './components/pages/DownloadPage';
import UploadPage from './components/pages/UploadPage';
import VerifyPage from './components/pages/VerifyPage';
import SettingsPage, { ProfileSettings, KeysSettings, SecuritySettings } from './components/pages/SettingsPage';
import HealthPage from './components/pages/HealthPage';
import NotFoundPage from './components/pages/NotFoundPage';
import ForbiddenPage from './components/pages/ForbiddenPage';
import ServerErrorPage from './components/pages/ServerErrorPage';

function ProtectedRoute({ children }: { children: ReactNode }) {
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
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
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
        <Route path="/" element={<RootRedirect />} />
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
          <Route path="security" element={<SecuritySettings />} />
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
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <Toaster />
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
