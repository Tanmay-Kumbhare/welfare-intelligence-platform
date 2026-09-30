import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/layout/Layout";
import AuthLayout from "./components/auth/AuthLayout";
import HomePage from "./pages/HomePage";
import SchemesPage from "./pages/SchemesPage";
import SchemeDetailPage from "./pages/SchemeDetailPage";
import ExplorePage from "./pages/ExplorePage";
import CheckEligibilityPage from "./pages/CheckEligibilityPage";
import ResultsPage from "./pages/ResultsPage";
import WhyExcludedPage from "./pages/WhyExcludedPage";
import ProfilePage from "./pages/ProfilePage";
import HelpPage from "./pages/HelpPage";
import NotFoundPage from "./pages/NotFoundPage";
import LoginPage from "./pages/auth/LoginPage";
import RegisterPage from "./pages/auth/RegisterPage";
import OAuthCallbackPage from "./pages/auth/OAuthCallbackPage";
import ProfileCompletionGate from "./pages/auth/ProfileCompletionGate";
import AdminLayout from "./pages/admin/AdminLayout";
import AdminOverviewPage from "./pages/admin/AdminOverviewPage";
import AdminUsersPage from "./pages/admin/AdminUsersPage";
import AdminSchemesPage from "./pages/admin/AdminSchemesPage";
import AdminSubmissionsPage from "./pages/admin/AdminSubmissionsPage";
import AdminSourcesPage from "./pages/admin/AdminSourcesPage";

import DocumentsPage from "./pages/DocumentsPage";
import DashboardPage from "./pages/DashboardPage";

function App() {
  return (
    <BrowserRouter>
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

        {/* Admin area: completely separate shell — its own header, sidebar
            and nav. Gated by AdminGate (UX) and require_admin on every
            backend endpoint (real security). Deliberately NOT nested in the
            citizen Layout so citizen navigation never appears here. */}
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<AdminOverviewPage />} />
          <Route path="users" element={<AdminUsersPage />} />
          <Route path="schemes" element={<AdminSchemesPage />} />
          <Route path="submissions" element={<AdminSubmissionsPage />} />
          <Route path="sources" element={<AdminSourcesPage />} />
        </Route>

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
