import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import AdminSchemesPage from "../AdminSchemesPage";
import { adminService } from "../../../services/api";
import {
  schemeListItem,
  httpError,
} from "../../../test/adminFixtures";

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

const SCHEMES = [
  schemeListItem({ scheme_id: "scheme-alpha", scheme_name: "Alpha Scheme", status: "ACTIVE", rule_count: 3 }),
  schemeListItem({ scheme_id: "scheme-beta", scheme_name: "Beta Scheme", status: "INACTIVE", rule_count: 0 }),
];

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminSchemesPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  adminService.listSchemes.mockResolvedValue({ data: SCHEMES });
});

describe("AdminSchemesPage — list rendering", () => {
  it("shows loading then every scheme with its status and links", async () => {
    renderPage();
    expect(screen.getByText(/Loading schemes/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Alpha Scheme")).toBeInTheDocument();
      expect(screen.getByText("Beta Scheme")).toBeInTheDocument();
    });
    // Status text also appears as a filter <option>; badges use the same word.
    expect(screen.getAllByText("ACTIVE").length).toBeGreaterThan(0);
    expect(screen.getAllByText("INACTIVE").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Open detail").length).toBe(2);
  });

  it("filters by status and search without re-fetching", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Alpha Scheme");
    await user.selectOptions(screen.getByLabelText(/Status/), "INACTIVE");
    expect(screen.getByText("Beta Scheme")).toBeInTheDocument();
    expect(screen.queryByText("Alpha Scheme")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText(/Status/), "ALL");
    await user.type(screen.getByLabelText(/Search/), "alpha");
    expect(screen.getByText("Alpha Scheme")).toBeInTheDocument();
    expect(screen.queryByText("Beta Scheme")).not.toBeInTheDocument();
  });

  it("renders an empty state when the catalogue is empty", async () => {
    adminService.listSchemes.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("No schemes yet")).toBeInTheDocument();
    });
  });

  it("renders an API-error state instead of a blank screen", async () => {
    adminService.listSchemes.mockRejectedValue(
      httpError(500, { detail: "db down" })
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("db down")).toBeInTheDocument();
    });
  });
});

describe("AdminSchemesPage — creation", () => {
  it("requires a scheme name before enabling submit", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByText("+ Create scheme"));
    const submit = screen.getByText("Create scheme");
    expect(submit.closest("button")).toBeDisabled();
  });

  it("rejects an end date before the start date inline", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByText("+ Create scheme"));
    await user.type(screen.getByLabelText(/^Scheme name/, { selector: "input" }), "New Scheme");
    await user.type(screen.getByLabelText(/Start date/), "2026-05-01");
    await user.type(screen.getByLabelText(/End date/), "2026-01-01");
    expect(screen.getByText(/End date must not be before the start date/i)).toBeInTheDocument();
    expect(screen.getByText("Create scheme").closest("button")).toBeDisabled();
  });

  it("creates a scheme, shows the success notice and reloads", async () => {
    const user = userEvent.setup();
    adminService.createScheme.mockResolvedValue({
      data: schemeListItem({ scheme_id: "scheme-new", scheme_name: "New Scheme" }),
    });
    // The list refresh after creation now includes the new record.
    adminService.listSchemes
      .mockResolvedValueOnce({ data: SCHEMES })
      .mockResolvedValue({
        data: [...SCHEMES, schemeListItem({ scheme_id: "scheme-new", scheme_name: "New Scheme" })],
      });
    renderPage();
    await screen.findByText("Alpha Scheme");
    await user.click(screen.getByText("+ Create scheme"));
    await user.type(screen.getByLabelText(/^Scheme name/, { selector: "input" }), "New Scheme");
    await user.click(screen.getByText("Create scheme"));
    await waitFor(() => {
      expect(
        screen.getByText(/New Scheme” created — open it to add rules/i)
      ).toBeInTheDocument();
    });
    expect(adminService.createScheme).toHaveBeenCalledWith(
      expect.objectContaining({ scheme_name: "New Scheme" })
    );
    await waitFor(() => {
      expect(screen.getByText("New Scheme")).toBeInTheDocument();
    });
  });

  it("surfaces server-side validation errors verbatim", async () => {
    const user = userEvent.setup();
    adminService.createScheme.mockRejectedValue(
      httpError(400, { detail: "scheme_name must not be empty" })
    );
    renderPage();
    await screen.findByText("Alpha Scheme");
    await user.click(screen.getByText("+ Create scheme"));
    await user.type(screen.getByLabelText(/^Scheme name/, { selector: "input" }), "X");
    await user.click(screen.getByText("Create scheme"));
    await waitFor(() => {
      expect(screen.getByText("scheme_name must not be empty")).toBeInTheDocument();
    });
  });
});

describe("AdminSchemesPage — archive / restore", () => {
  it("archives an active scheme after explicit confirmation", async () => {
    const user = userEvent.setup();
    adminService.archiveScheme.mockResolvedValue({ data: {} });
    renderPage();
    await screen.findByText("Alpha Scheme");
    await user.click(screen.getAllByText("Archive")[0]);
    expect(
      screen.getByText(/becomes INACTIVE and disappears from all citizen-facing listings/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Reversible/i)).toBeInTheDocument();
    await user.click(screen.getByText("Confirm"));
    await waitFor(() => {
      expect(adminService.archiveScheme).toHaveBeenCalledWith(SCHEMES[0].scheme_id);
    });
  });

  it("restores an inactive scheme after explicit confirmation", async () => {
    const user = userEvent.setup();
    adminService.restoreScheme.mockResolvedValue({ data: {} });
    renderPage();
    await screen.findByText("Beta Scheme");
    await user.click(screen.getAllByText("Restore")[0]);
    await user.click(screen.getByText("Confirm"));
    await waitFor(() => {
      expect(adminService.restoreScheme).toHaveBeenCalledWith(SCHEMES[1].scheme_id);
    });
  });

  it("cancels the confirmation without touching the backend", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Alpha Scheme");
    await user.click(screen.getAllByText("Archive")[0]);
    await user.click(screen.getByText("Cancel"));
    expect(adminService.archiveScheme).not.toHaveBeenCalled();
  });

  it("shows the API error when archive fails", async () => {
    const user = userEvent.setup();
    adminService.archiveScheme.mockRejectedValue(
      httpError(409, { detail: "Scheme is referenced by assessment history; archive it instead" })
    );
    renderPage();
    await screen.findByText("Alpha Scheme");
    await user.click(screen.getAllByText("Archive")[0]);
    await user.click(screen.getByText("Confirm"));
    await waitFor(() => {
      // The error is shown twice (row-local and page banner) by design.
      expect(
        screen.getAllByText(/referenced by assessment history/i).length
      ).toBeGreaterThan(0);
    });
  });
});
