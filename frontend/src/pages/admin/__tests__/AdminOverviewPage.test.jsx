import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AdminOverviewPage from "../AdminOverviewPage";
import { adminService } from "../../../services/api";
import { schemeListItem, httpError } from "../../../test/adminFixtures";

vi.mock("../../../services/api", () => ({
  adminService: {
    stats: vi.fn(),
    listSchemes: vi.fn(),
    schemeDetail: vi.fn(),
    createScheme: vi.fn(),
    updateScheme: vi.fn(),
    archiveScheme: vi.fn(),
    restoreScheme: vi.fn(),
    deleteScheme: vi.fn(),
    verifyScheme: vi.fn(),
    listRuleGroups: vi.fn(),
    createRuleGroup: vi.fn(),
    updateRuleGroup: vi.fn(),
    deleteRuleGroup: vi.fn(),
    setGroupCombiningOperator: vi.fn(),
    createRule: vi.fn(),
    updateRule: vi.fn(),
    deleteRule: vi.fn(),
    listDocuments: vi.fn(),
    createDocument: vi.fn(),
    updateDocument: vi.fn(),
    deleteDocument: vi.fn(),
    listSchemeSourceDocuments: vi.fn(),
    linkSchemeSourceDocument: vi.fn(),
    unlinkSchemeSourceDocument: vi.fn(),
    rulesWithProvenance: vi.fn(),
    latestDocumentSentences: vi.fn(),
    documentSentences: vi.fn(),
    linkRuleProvenance: vi.fn(),
    verifyRuleProvenance: vi.fn(),
  },
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminOverviewPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  adminService.stats.mockResolvedValue({
    data: {
      counts: { users: 3, citizens: 2, schemes: 3, submissions: 0, assessments: 4 },
      recent_registrations: [{ email: "a@x.test", created_at: "2026-10-01T00:00:00Z" }],
    },
  });
  adminService.listSchemes.mockResolvedValue({
    data: [
      schemeListItem({ scheme_name: "S1", status: "ACTIVE", rule_count: 2 }),
      schemeListItem({ scheme_name: "S2", status: "ACTIVE", rule_count: 0 }),
      schemeListItem({ scheme_name: "S3", status: "INACTIVE", rule_count: 1 }),
    ],
  });
});

describe("AdminOverviewPage", () => {
  it("shows loading then headline counts", async () => {
    renderPage();
    expect(screen.getByText(/Loading platform statistics/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("4")).toBeInTheDocument(); // assessments
    });
    expect(screen.getByText("User accounts")).toBeInTheDocument();
  });

  it("breaks schemes down by status from the catalogue list", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Active schemes")).toBeInTheDocument();
      expect(screen.getByText("Inactive / archived")).toBeInTheDocument();
    });
    expect(screen.getByText("Schemes by state")).toBeInTheDocument();
  });

  it("flags active schemes without eligibility rules as needing attention", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/need attention/i)).toBeInTheDocument();
    });
  });

  it("renders the recent registrations feed", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("a@x.test")).toBeInTheDocument();
    });
  });

  it("renders a server error state and stays usable for retry", async () => {
    adminService.stats.mockRejectedValue(httpError(500, { detail: "admin_stats error: boom" }));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("admin_stats error: boom")).toBeInTheDocument();
    });
    expect(screen.getByText(/Unable to load overview/i)).toBeInTheDocument();
  });

  it("does not fake a scheme breakdown when the list call fails", async () => {
    adminService.listSchemes.mockRejectedValue(httpError(500, { detail: "db down" }));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Scheme breakdown could not be loaded/i)).toBeInTheDocument();
    });
    // No breakdown numbers were loaded — the cards are simply absent.
    expect(screen.queryByText("Active schemes")).not.toBeInTheDocument();
    expect(screen.queryByText("Inactive / archived")).not.toBeInTheDocument();
  });
});
