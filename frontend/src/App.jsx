import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/layout/Layout";
import AuthLayout from "./components/auth/AuthLayout";
import HomePage from "./pages/HomePage";
import SchemesPage from "./pages/SchemesPage";
import DashboardPage from "./pages/DashboardPage";
import CheckEligibilityPage from "./pages/CheckEligibilityPage";
import ProfilePage from "./pages/ProfilePage";
import LoginPage from "./pages/auth/LoginPage";
import RegisterPage from "./pages/auth/RegisterPage";
import OAuthCallbackPage from "./pages/auth/OAuthCallbackPage";
import ProfileCompletionGate from "./pages/auth/ProfileCompletionGate";
import NotFoundPage from "./pages/NotFoundPage";

// Route-level lazy loading for secondary citizen pages & admin portal
const SchemeDetailPage = lazy(() => import("./pages/SchemeDetailPage"));
const ExplorePage = lazy(() => import("./pages/ExplorePage"));
const ResultsPage = lazy(() => import("./pages/ResultsPage"));
const WhyExcludedPage = lazy(() => import("./pages/WhyExcludedPage"));
const HelpPage = lazy(() => import("./pages/HelpPage"));
const DocumentsPage = lazy(() => import("./pages/DocumentsPage"));

const AdminLayout = lazy(() => import("./pages/admin/AdminLayout"));
const AdminOverviewPage = lazy(() => import("./pages/admin/AdminOverviewPage"));
const AdminUsersPage = lazy(() => import("./pages/admin/AdminUsersPage"));
const AdminSchemesPage = lazy(() => import("./pages/admin/AdminSchemesPage"));
const AdminSubmissionsPage = lazy(() => import("./pages/admin/AdminSubmissionsPage"));
const AdminSourcesPage = lazy(() => import("./pages/admin/AdminSourcesPage"));

function RouteLoader() {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div className="text-sm text-slate-500 animate-pulse">Loading…</div>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<RouteLoader />}>
        <Routes>
          {/* Citizen area: shared Layout with the citizen Header/Footer. */}
          <Route element={<Layout />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/auth/callback" element={<OAuthCallbackPage />} />

            <Route path="/" element={<HomePage />} />

            <Route element={<AuthLayout />}>
              <Route path="/profile" element={<ProfilePage />} />
              <Route element={<ProfileCompletionGate />}>
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/schemes" element={<SchemesPage />} />
                <Route path="/schemes/:id" element={<SchemeDetailPage />} />
                <Route path="/explore" element={<ExplorePage />} />
                <Route path="/help" element={<HelpPage />} />
                <Route path="/results/:citizenId" element={<ResultsPage />} />
                <Route path="/why-excluded/:citizenId/:schemeId" element={<WhyExcludedPage />} />
              </Route>
            </Route>

            <Route path="/check-eligibility" element={<CheckEligibilityPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
          </Route>

          {/* Admin area: completely separate shell */}
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<AdminOverviewPage />} />
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="schemes" element={<AdminSchemesPage />} />
            <Route path="submissions" element={<AdminSubmissionsPage />} />
            <Route path="sources" element={<AdminSourcesPage />} />
          </Route>

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
