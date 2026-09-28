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
import ProfileCompletionGate from "./pages/auth/ProfileCompletionGate";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          <Route path="/" element={<HomePage />} />

          <Route element={<AuthLayout />}>
            <Route element={<ProfileCompletionGate />}>
              <Route path="/schemes" element={<SchemesPage />} />
              <Route path="/schemes/:id" element={<SchemeDetailPage />} />
              <Route path="/explore" element={<ExplorePage />} />
              <Route path="/help" element={<HelpPage />} />
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/results/:citizenId" element={<ResultsPage />} />
              <Route path="/why-excluded/:citizenId/:schemeId" element={<WhyExcludedPage />} />
            </Route>
          </Route>

          <Route path="/check-eligibility" element={<CheckEligibilityPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
