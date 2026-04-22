import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider } from 'antd';
import ProfessionalLayout from './components/Layout/ProfessionalLayout';
import RoleBasedDashboard from './pages/RoleBasedDashboard';
import LeadsPageEnhanced from './pages/LeadsPageEnhanced';
import LeadDetails from './pages/LeadDetails';
import HospitalsPage from './pages/HospitalsPage';
import CoursesPage from './pages/CoursesPage';
import CoursesPageEnhanced from './pages/CoursesPageEnhanced';
import AnalyticsPage from './pages/AnalyticsPage';
import UsersPage from './pages/UsersPage';
import DragDropPipeline from './features/pipeline/DragDropPipeline';
import UserActivityPage from './pages/UserActivityPage';
import LeadAnalysisPage from './pages/LeadAnalysisPage';
import AuditLogs from './features/audit/AuditLogs';
import LoginPage from './pages/LoginPage';
import FollowupTodayPage from './pages/FollowupTodayPage';
import { isFeatureEnabled } from './config/featureFlags';
import ErrorBoundary from './components/ErrorBoundary';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5 * 60 * 1000,
      cacheTime: 10 * 60 * 1000,
    },
  },
});

// Redirect to /login if no user in localStorage
function RequireAuth({ children }) {
  const user = localStorage.getItem('user');
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function App() {
  return (
    <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <ConfigProvider
        theme={{
          token: {
            colorPrimary: '#3b82f6',
            borderRadius: 8,
            colorSuccess: '#10b981',
            colorWarning: '#f59e0b',
            colorError: '#ef4444',
            colorInfo: '#3b82f6',
            fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, sans-serif',
          },
        }}
      >
        <Router>
          <Routes>
            {/* Public login route */}
            <Route path="/login" element={<LoginPage />} />

            {/* All protected routes wrapped in layout */}
            <Route
              path="/*"
              element={
                <RequireAuth>
                  <ProfessionalLayout>
                    <Routes>
                      <Route path="/" element={<Navigate to="/dashboard" replace />} />
                      <Route path="/dashboard" element={<RoleBasedDashboard />} />
                      <Route path="/followups" element={<FollowupTodayPage />} />
                      <Route path="/leads" element={<LeadsPageEnhanced />} />
                      <Route path="/leads/:leadId" element={<LeadDetails />} />
                      <Route path="/pipeline" element={<DragDropPipeline />} />
                      <Route path="/lead-analysis" element={<LeadAnalysisPage />} />
                      <Route path="/analytics" element={<AnalyticsPage />} />
                      <Route path="/hospitals" element={<HospitalsPage />} />
                      <Route path="/courses" element={<CoursesPageEnhanced />} />
                      <Route path="/users" element={<UsersPage />} />
                      <Route path="/user-activity" element={<UserActivityPage />} />
                      {isFeatureEnabled('AUDIT_LOGS') && (
                        <Route path="/audit-logs" element={<AuditLogs />} />
                      )}
                    </Routes>
                  </ProfessionalLayout>
                </RequireAuth>
              }
            />
          </Routes>
        </Router>
      </ConfigProvider>
    </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
