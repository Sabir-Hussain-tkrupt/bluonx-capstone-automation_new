import { Navigate, Route, Routes } from 'react-router-dom';
import { ROUTES } from '@/constants/routes';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { PublicRoute } from '@/components/auth/PublicRoute';
import { AuthLayout } from '@/components/layout/AuthLayout';
import { DashboardLayout } from '@/components/layout/DashboardLayout';

// Auth pages
import { LoginPage } from '@/features/auth/pages/LoginPage';
import { ForgotPasswordPage } from '@/features/auth/pages/ForgotPasswordPage';
import { AuthCallbackPage } from '@/features/auth/pages/AuthCallbackPage';
import { ResetPasswordPage } from '@/features/auth/pages/ResetPasswordPage';

// Protected pages
import { DashboardPage } from '@/features/dashboard/pages/DashboardPage';
import { VendorListPage } from '@/features/vendors/pages/VendorListPage';
import { VendorDetailPage } from '@/features/vendors/pages/VendorDetailPage';
import { ProjectListPage } from '@/features/projects/pages/ProjectListPage';
import { ProjectDetailPage } from '@/features/projects/pages/ProjectDetailPage';
import { TaskListPage } from '@/features/projects/pages/TaskListPage';
import { TaskDetailPage } from '@/features/projects/pages/TaskDetailPage';
import { BidManagementPage } from '@/features/bids/pages/BidManagementPage';
import { AwardPage } from '@/features/contracts/pages/AwardPage';
import { BidTemplateListPage } from '@/features/bid-templates/pages/BidTemplateListPage';
import { BidTemplateDetailPage } from '@/features/bid-templates/pages/BidTemplateDetailPage';
import { BidTemplateFormPage } from '@/features/bid-templates/pages/BidTemplateFormPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { UnauthorizedPage } from '@/pages/UnauthorizedPage';
import { ComponentShowcasePage } from '@/pages/ComponentShowcasePage';

export function AppRoutes() {
  return (
    <Routes>
      {/* Public auth routes — redirects authenticated users to dashboard */}
      <Route
        element={
          <PublicRoute>
            <AuthLayout />
          </PublicRoute>
        }
      >
        <Route path={ROUTES.LOGIN} element={<LoginPage />} />
        <Route path={ROUTES.FORGOT_PASSWORD} element={<ForgotPasswordPage />} />
      </Route>

      {/* Auth callback routes — no layout wrapper */}
      <Route path={ROUTES.AUTH_CALLBACK} element={<AuthCallbackPage />} />
      <Route path={ROUTES.AUTH_RESET_PASSWORD} element={<ResetPasswordPage />} />

      {/* Protected routes — dashboard layout with sidebar/header */}
      <Route
        element={
          <ProtectedRoute>
            <DashboardLayout />
          </ProtectedRoute>
        }
      >
        <Route path={ROUTES.DASHBOARD} element={<DashboardPage />} />
        <Route path={ROUTES.VENDORS} element={<VendorListPage />} />
        <Route path={ROUTES.VENDOR_DETAIL} element={<VendorDetailPage />} />
        <Route path={ROUTES.PROJECTS} element={<ProjectListPage />} />
        <Route path={ROUTES.PROJECT_DETAIL} element={<ProjectDetailPage />} />
        <Route path={ROUTES.TASKS} element={<TaskListPage />} />
        <Route path={ROUTES.TASK_DETAIL} element={<TaskDetailPage />} />
        <Route path={ROUTES.BID_MANAGEMENT} element={<BidManagementPage />} />
        <Route path={ROUTES.AWARD} element={<AwardPage />} />
        <Route path={ROUTES.BID_TEMPLATES} element={<BidTemplateListPage />} />
        <Route path={ROUTES.BID_TEMPLATE_NEW} element={<BidTemplateFormPage />} />
        <Route path={ROUTES.BID_TEMPLATE_DETAIL} element={<BidTemplateDetailPage />} />
        <Route path={ROUTES.BID_TEMPLATE_EDIT} element={<BidTemplateFormPage />} />
        <Route
          path={ROUTES.SETTINGS}
          element={
            <ProtectedRoute requiredRole="admin">
              <SettingsPage />
            </ProtectedRoute>
          }
        />
      </Route>

      {/* Dev-only showcase route */}
      <Route path="/dev/components" element={<ComponentShowcasePage />} />

      {/* Error pages */}
      <Route path={ROUTES.UNAUTHORIZED} element={<UnauthorizedPage />} />

      {/* Root redirect */}
      <Route path="/" element={<Navigate to={ROUTES.DASHBOARD} replace />} />

      {/* 404 catch-all */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
