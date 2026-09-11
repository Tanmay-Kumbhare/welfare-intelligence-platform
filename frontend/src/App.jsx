import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/layout/Layout";
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

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/schemes" element={<SchemesPage />} />
          <Route path="/schemes/:id" element={<SchemeDetailPage />} />
          <Route path="/explore" element={<ExplorePage />} />
          <Route path="/check-eligibility" element={<CheckEligibilityPage />} />
          <Route path="/results/:citizenId" element={<ResultsPage />} />
          <Route path="/why-excluded/:citizenId/:schemeId" element={<WhyExcludedPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
