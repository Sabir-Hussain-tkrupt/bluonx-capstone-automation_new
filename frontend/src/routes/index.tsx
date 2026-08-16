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
import { AcceptInvitePage } from '@/features/auth/pages/AcceptInvitePage';

// Protected pages
import { DashboardPage } from '@/features/dashboard/pages/DashboardPage';
import { VendorListPage } from '@/features/vendors/pages/VendorListPage';
import { VendorDetailPage } from '@/features/vendors/pages/VendorDetailPage';
import { ProjectListPage } from '@/features/projects/pages/ProjectListPage';
import { ProjectDetailPage } from '@/features/projects/pages/ProjectDetailPage';
import { TaskListPage } from '@/features/projects/pages/TaskListPage';
import { TaskDetailPage } from '@/features/projects/pages/TaskDetailPage';
import { BidPackageCreatePage } from '@/features/bids/pages/BidPackageCreatePage';
import { BidPackageDetailPage } from '@/features/bids/pages/BidPackageDetailPage';
import { BidPackageComparePage } from '@/features/bids/pages/BidPackageComparePage';
import { BidPackageListPage } from '@/features/bids/pages/BidPackageListPage';
import { MilestoneDetailPage } from '@/features/milestones/pages/MilestoneDetailPage';
import { MilestoneListPage } from '@/features/milestones/pages/MilestoneListPage';
import { BidTemplateListPage } from '@/features/bid-templates/pages/BidTemplateListPage';
import { BidTemplateDetailPage } from '@/features/bid-templates/pages/BidTemplateDetailPage';
import { BidTemplateFormPage } from '@/features/bid-templates/pages/BidTemplateFormPage';
import { NotificationsPage } from '@/features/notifications/pages/NotificationsPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { TradesSettingsPage } from '@/features/trades';
import { UserManagementPage } from '@/features/user-management';
import { HolidayCalendarPage } from '@/features/holidays';
import { ContractSignersPage } from '@/features/contract-signers';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { UnauthorizedPage } from '@/pages/UnauthorizedPage';
import { ComponentShowcasePage } from '@/pages/ComponentShowcasePage';

// Vendor Portal (public, isolated from admin auth/layout)
import {
  AlreadySubmittedPage,
  BidFormPage,
  BiddingClosedPage,
  InvalidTokenPage,
  MagicLinkLandingPage,
  MilestoneLandingPage,
  MilestoneNoLongerCurrentPage,
  MilestoneRecordedPage,
  MilestoneRespondPage,
  PortalLayout,
  RevisionDeclinedPage,
  RevisionInactivePage,
  RevisionLandingPage,
  SubmissionConfirmationPage,
  TokenExpiredPage,
  VendorPortalGuard,
  VendorPortalProvider,
} from '@/features/vendor-portal';

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
      {/*
        Accept-invite is a BARE route (C2): the invited user arrives already
        authenticated but passwordless (Supabase /auth/v1/verify created the
        session on click). It must NOT sit under PublicRoute (which would bounce
        an authenticated user to the dashboard) or ProtectedRoute.
      */}
      <Route path={ROUTES.ACCEPT_INVITE} element={<AcceptInvitePage />} />

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
        <Route path={ROUTES.CREATE_BID_PACKAGE} element={<BidPackageCreatePage />} />
        <Route path={ROUTES.BID_PACKAGE_DETAIL} element={<BidPackageDetailPage />} />
        <Route path={ROUTES.BID_PACKAGE_COMPARE} element={<BidPackageComparePage />} />
        <Route path={ROUTES.MILESTONE_DETAIL} element={<MilestoneDetailPage />} />
        <Route path={ROUTES.MILESTONES} element={<MilestoneListPage />} />
        <Route path={ROUTES.BID_PACKAGES} element={<BidPackageListPage />} />
        <Route path={ROUTES.BID_TEMPLATES} element={<BidTemplateListPage />} />
        <Route path={ROUTES.BID_TEMPLATE_NEW} element={<BidTemplateFormPage />} />
        <Route path={ROUTES.BID_TEMPLATE_DETAIL} element={<BidTemplateDetailPage />} />
        <Route path={ROUTES.BID_TEMPLATE_EDIT} element={<BidTemplateFormPage />} />
        <Route path={ROUTES.NOTIFICATIONS} element={<NotificationsPage />} />
        <Route
          path={ROUTES.SETTINGS}
          element={
            <ProtectedRoute requiredRole="admin">
              <SettingsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path={ROUTES.SETTINGS_TRADES}
          element={
            <ProtectedRoute requiredRole="admin">
              <TradesSettingsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path={ROUTES.SETTINGS_USERS}
          element={
            <ProtectedRoute requiredRole="admin">
              <UserManagementPage />
            </ProtectedRoute>
          }
        />
        <Route
          path={ROUTES.SETTINGS_CALENDAR}
          element={
            <ProtectedRoute requiredRole="admin">
              <HolidayCalendarPage />
            </ProtectedRoute>
          }
        />
        <Route
          path={ROUTES.SETTINGS_CONTRACT_SIGNERS}
          element={
            <ProtectedRoute requiredRole="admin">
              <ContractSignersPage />
            </ProtectedRoute>
          }
        />
      </Route>

      {/* Vendor Portal — public, isolated from admin layout/auth */}
      <Route
        element={
          <VendorPortalProvider>
            <PortalLayout />
          </VendorPortalProvider>
        }
      >
        <Route path={ROUTES.PORTAL_LANDING} element={<MagicLinkLandingPage />} />
        <Route path={ROUTES.PORTAL_MILESTONE_LANDING} element={<MilestoneLandingPage />} />
        <Route element={<VendorPortalGuard />}>
          <Route path={ROUTES.PORTAL_REVISION} element={<RevisionLandingPage />} />
          <Route path={ROUTES.PORTAL_FORM} element={<BidFormPage />} />
          <Route path={ROUTES.PORTAL_SUBMITTED} element={<SubmissionConfirmationPage />} />
          <Route path={ROUTES.PORTAL_MILESTONE} element={<MilestoneRespondPage />} />
        </Route>
        <Route path={ROUTES.PORTAL_REVISION_INACTIVE} element={<RevisionInactivePage />} />
        <Route path={ROUTES.PORTAL_REVISION_DECLINED} element={<RevisionDeclinedPage />} />
        <Route path={ROUTES.PORTAL_MILESTONE_RECORDED} element={<MilestoneRecordedPage />} />
        <Route path={ROUTES.PORTAL_MILESTONE_INACTIVE} element={<MilestoneNoLongerCurrentPage />} />
        <Route path={ROUTES.PORTAL_EXPIRED} element={<TokenExpiredPage />} />
        <Route path={ROUTES.PORTAL_INVALID} element={<InvalidTokenPage />} />
        <Route path={ROUTES.PORTAL_CLOSED} element={<BiddingClosedPage />} />
        <Route path={ROUTES.PORTAL_ALREADY_SUBMITTED} element={<AlreadySubmittedPage />} />
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
