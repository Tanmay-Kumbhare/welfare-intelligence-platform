import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import AdminSchemeDetailPage from "../AdminSchemeDetailPage";
import { adminService } from "../../../services/api";
import {
  schemeDetail,
  schemeListItem,
  GROUP,
  rule as ruleFixture,
  PROVENANCE,
  documentRequirement,
  sourceDocument,
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

const SCHEME_ID = "s0000000-0000-0000-0000-000000000001";
const RULE = ruleFixture();

function renderPage(scheme = schemeDetail()) {
  return render(
    <MemoryRouter initialEntries={[`/admin/schemes/${scheme.scheme_id}`]}>
      <Routes>
        {/* Match the real route shape so useParams delivers the scheme id. */}
        <Route path="admin/schemes/:id" element={<AdminSchemeDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

function mockDefaults(overrides = {}) {
  const detail = schemeDetail(overrides);
  adminService.schemeDetail.mockResolvedValue({ data: detail });
  return detail;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockDefaults();
  adminService.listSchemes.mockResolvedValue({ data: [schemeListItem()] });
  adminService.listRuleGroups.mockResolvedValue({
    data: [{ ...GROUP, rules: [RULE] }],
  });
  adminService.rulesWithProvenance.mockResolvedValue({
    data: { scheme_id: SCHEME_ID, rules: [{ ...RULE, provenance: PROVENANCE }] },
  });
  adminService.listDocuments.mockResolvedValue({
    data: [documentRequirement()],
  });
  adminService.listSchemeSourceDocuments.mockResolvedValue({
    data: [sourceDocument()],
  });
});

describe("loading and tabs", () => {
  it("renders the scheme header with status and verification state", async () => {
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    // The name appears in the header and the Record field list; status both
    // as badge and in the Record list.
    expect(screen.getAllByText("Test Scholarship").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ACTIVE").length).toBeGreaterThan(0);
  });

  it("shows an API-failure state with retry instead of a blank screen", async () => {
    adminService.schemeDetail.mockRejectedValue(
      httpError(500, { detail: "Schemes are unavailable" })
    );
    renderPage();
    await screen.findByText("Schemes are unavailable");
    expect(
      screen.getByText(/Unable to load scheme/i)
    ).toBeInTheDocument();
  });
});

describe("overview + metadata editing", () => {
  it("shows record fields and opens the metadata editor", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    expect(screen.getAllByText("Department of Education").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Edit metadata" }));
    expect(screen.getByText("Edit metadata", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByLabelText(/^Scheme name/)).toHaveValue("Test Scholarship");
  });

  it("saves metadata and never claims verification (server-labelled distinction)", async () => {
    const user = userEvent.setup();
    adminService.updateScheme.mockResolvedValue({ data: {} });
    adminService.schemeDetail
      .mockResolvedValueOnce({ data: schemeDetail() })
      .mockResolvedValueOnce({
        data: schemeDetail({ description: "Edited description" }),
      });
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByRole("button", { name: "Edit metadata" }));
    await user.type(screen.getByLabelText(/^Description/), " (edited)");
    await user.click(screen.getByText("Save metadata"));
    await waitFor(() => {
      expect(adminService.updateScheme).toHaveBeenCalledWith(
        SCHEME_ID,
        expect.objectContaining({
          scheme_name: "Test Scholarship",
          description: "A test education scheme. (edited)",
        })
      );
    });
    expect(
      await screen.findByText(/the scheme was NOT verified/i)
    ).toBeInTheDocument();
  });
});

describe("archive / restore / delete", () => {
  it("archives after explicit confirmation", async () => {
    const user = userEvent.setup();
    adminService.archiveScheme.mockResolvedValue({ data: {} });
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByRole("button", { name: "Archive" }));
    await user.click(screen.getByText("Confirm"));
    await waitFor(() => {
      expect(adminService.archiveScheme).toHaveBeenCalledWith(SCHEME_ID);
    });
  });

  it("restores an archived scheme", async () => {
    const user = userEvent.setup();
    mockDefaults({ status: "INACTIVE" });
    adminService.restoreScheme.mockResolvedValue({ data: {} });
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByRole("button", { name: "Restore" }));
    await user.click(screen.getByText("Confirm"));
    await waitFor(() => {
      expect(adminService.restoreScheme).toHaveBeenCalledWith(SCHEME_ID);
    });
  });

  it("warns that delete is permanent and surfaces the 409 protection verbatim", async () => {
    const user = userEvent.setup();
    adminService.deleteScheme.mockRejectedValue(
      httpError(409, { detail: "Scheme is linked to source documents; archive it instead" })
    );
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(
      await screen.findByText(/permanent hard delete/i)
    ).toBeInTheDocument();
    await user.click(screen.getByText("Confirm"));
    await waitFor(() => {
      expect(
        screen.getByText(/linked to source documents/i)
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/permanent hard delete/i)).not.toBeInTheDocument();
  });
});

describe("rules tab", () => {
  it("lists groups with rules and their provenance citations", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Eligibility rules"));
    await screen.findByText("Income gate");
    expect(
      screen.getByText((_content, element) =>
        element?.tagName === "P" && element.textContent.includes("Must be an adult")
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText((_content, element) =>
        element?.tagName === "P" &&
        element.textContent.includes("must be at least 18 years old")
      )
    ).toBeInTheDocument();
    // no weight, no mandatory concepts
    expect(screen.queryByText(/weight/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/mandatory flag/i)).not.toBeInTheDocument();
  });

  it("shows an active scheme with no rule groups as needing rules", async () => {
    const user = userEvent.setup();
    adminService.listRuleGroups.mockResolvedValue({ data: [] });
    adminService.rulesWithProvenance.mockResolvedValue({ data: { rules: [] } });
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Eligibility rules"));
    await screen.findByText("No rule groups yet");
  });

  it("edits rule fields with the server as authority on rejection", async () => {
    const user = userEvent.setup();
    adminService.updateRule.mockRejectedValue(
      httpError(400, {
        detail: "required_value for numeric parameter 'age' must be a number (e.g. '18'), got 'x'",
      })
    );
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Eligibility rules"));
    await screen.findByText("Income gate");
    await user.click(screen.getAllByText("Edit")[0]);
    await user.click(screen.getByText("Save rule"));
    await waitFor(() => {
      expect(
        screen.getByText(/must be a number/)
      ).toBeInTheDocument();
    });
  });

  it("creates a rule via the group's add-rule flow", async () => {
    const user = userEvent.setup();
    adminService.createRule.mockResolvedValue({ data: RULE });
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Eligibility rules"));
    await screen.findByText("Income gate");
    await user.click(screen.getByText("+ Add rule"));
    // The value editor adapts to the selected parameter: age => numeric input.
    await user.selectOptions(screen.getByLabelText(/^Parameter/), "age");
    await user.type(screen.getByLabelText(/Value \(number\)/), "18");
    await user.click(screen.getByText("Add rule"));
    await waitFor(() => {
      expect(adminService.createRule).toHaveBeenCalledWith(
        SCHEME_ID,
        expect.objectContaining({ parameter_name: "age", required_value: "18" })
      );
    });
  });

  it("deletes a rule after confirmation explains evidence protection", async () => {
    const user = userEvent.setup();
    adminService.deleteRule.mockRejectedValue(
      httpError(409, { detail: "Rule has source provenance and cannot be deleted" })
    );
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Eligibility rules"));
    await screen.findByText("Income gate");
    await user.click(screen.getByRole("button", { name: /^Delete rule age/ }));
    expect(await screen.findByText(/Delete this rule\?/)).toBeInTheDocument();
    await user.click(screen.getByText("Confirm"));
    await waitFor(() => {
      expect(
        screen.getByText(/provenance and cannot be deleted/i)
      ).toBeInTheDocument();
    });
  });

  it("switches the group combining operator only after a material-change confirmation", async () => {
    const user = userEvent.setup();
    adminService.setGroupCombiningOperator.mockResolvedValue({ data: {} });
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Eligibility rules"));
    await user.click(screen.getByText("Switch to OR"));
    expect(await screen.findByText(/real eligibility outcomes/i)).toBeInTheDocument();
    await user.click(screen.getByText("Confirm"));
    await waitFor(() => {
      expect(adminService.setGroupCombiningOperator).toHaveBeenCalledWith(
        SCHEME_ID,
        "OR"
      );
    });
  });
});

describe("documents tab", () => {
  it("lists requirements using only the existing type vocabulary", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Required documents"));
    await screen.findByText("INCOME_CERTIFICATE");
    expect(screen.getByText("MANDATORY")).toBeInTheDocument();
    expect(screen.getByText(/Mandatory documents/)).toBeInTheDocument();
  });

  it("adds a requirement from the controlled dropdown only", async () => {
    const user = userEvent.setup();
    adminService.createDocument.mockResolvedValue({ data: documentRequirement() });
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Required documents"));
    await user.click(screen.getByText("+ Add requirement"));
    await user.selectOptions(
      screen.getByLabelText(/^Document type/),
      "RATION_CARD"
    );
    await user.click(screen.getByText("Add requirement"));
    await waitFor(() => {
      expect(adminService.createDocument).toHaveBeenCalledWith(
        SCHEME_ID,
        expect.objectContaining({ document_type: "RATION_CARD", mandatory_flag: true })
      );
    });
  });

  it("supports editing the mandatory flag", async () => {
    const user = userEvent.setup();
    adminService.updateDocument.mockResolvedValue({ data: documentRequirement({ mandatory_flag: false }) });
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Required documents"));
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.selectOptions(screen.getByLabelText(/^Requirement mode/), "false");
    await user.click(screen.getByText("Save requirement"));
    await waitFor(() => {
      expect(adminService.updateDocument).toHaveBeenCalledWith(
        SCHEME_ID,
        documentRequirement().document_id,
        expect.objectContaining({ mandatory_flag: false })
      );
    });
  });

  it("explains permanent removal before deleting a requirement", async () => {
    const user = userEvent.setup();
    adminService.deleteDocument.mockResolvedValue({ data: {} });
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Required documents"));
    await screen.findByText("INCOME_CERTIFICATE");
    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(
      await screen.findByText(/no undo for the requirement itself/i)
    ).toBeInTheDocument();
    await user.click(screen.getByText("Confirm"));
    await waitFor(() => {
      expect(adminService.deleteDocument).toHaveBeenCalledWith(
        SCHEME_ID,
        documentRequirement().document_id
      );
    });
  });
});

describe("sources tab", () => {
  it("lists linked snapshots as linked and offers deliberate unlinking", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Sources / provenance"));
    await screen.findByText("Scheme circular 2026.pdf");
    expect(screen.getByText("LINKED")).toBeInTheDocument();
    await user.click(screen.getByText("Unlink"));
    expect(
      await screen.findByText(/snapshot itself is NOT deleted/i)
    ).toBeInTheDocument();
    adminService.unlinkSchemeSourceDocument.mockResolvedValue({ data: sourceDocument({ scheme_id: null }) });
    await user.click(screen.getByText("Confirm"));
    await waitFor(() => {
      expect(adminService.unlinkSchemeSourceDocument).toHaveBeenCalledWith(
        SCHEME_ID,
        sourceDocument().source_document_id
      );
    });
  });

  it("links a snapshot by its ID (idempotent association)", async () => {
    const user = userEvent.setup();
    adminService.linkSchemeSourceDocument.mockResolvedValue({ data: sourceDocument() });
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Sources / provenance"));
    // A snapshot already linked below would be disabled (idempotency guard);
    // link one that is not in the list yet.
    const newSnapshotId = "00000000-0000-0000-0000-000000000007";
    const input = screen.getByLabelText("Source snapshot ID");
    await user.type(input, newSnapshotId);
    await user.click(screen.getByText("Link snapshot"));
    await waitFor(() => {
      expect(adminService.linkSchemeSourceDocument).toHaveBeenCalledWith(
        SCHEME_ID,
        newSnapshotId
      );
    });
  });

  it("rejects malformed snapshot IDs locally before any request", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Sources / provenance"));
    await user.type(screen.getByLabelText("Source snapshot ID"), "not-a-uuid");
    expect(screen.getByText("Link snapshot").closest("button")).toBeDisabled();
    expect(adminService.linkSchemeSourceDocument).not.toHaveBeenCalled();
  });
});

describe("verification tab", () => {
  it("shows the current state and keeps saving separate from verifying", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Verification"));
    await screen.findByText(/no verification has ever been recorded/i);
    expect(
      screen.getByText(/Saving metadata.*never claim verification|never touch this state/s)
    ).toBeInTheDocument();
  });

  it("requires checkbox confirmations before recording verification", async () => {
    const user = userEvent.setup();
    adminService.verifyScheme.mockResolvedValue({ data: schemeDetail({ last_verified_at: "2026-10-14" }) });
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Verification"));
    await user.type(screen.getByLabelText("Verified on"), "2026-10-14");
    await user.click(screen.getByText("Record verification"));
    await screen.findByText(/Record verification\?/i);
    const confirm = screen.getByText("Yes, record it");
    // until both confirmations tick, the dialog confirm stays disabled
    expect(confirm).toBeDisabled();
    await user.click(screen.getAllByRole("checkbox")[0]);
    await user.click(screen.getAllByRole("checkbox")[1]);
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    await waitFor(() => {
      expect(adminService.verifyScheme).toHaveBeenCalledWith(SCHEME_ID, "2026-10-14");
    });
  });

  it("shows the updated verification date from the server response", async () => {
    const user = userEvent.setup();
    adminService.schemeDetail
      .mockResolvedValueOnce({ data: schemeDetail() })
      .mockResolvedValueOnce({
        data: schemeDetail({ last_verified_at: "2026-10-14" }),
      });
    adminService.verifyScheme.mockResolvedValue({ data: schemeDetail({ last_verified_at: "2026-10-14" }) });
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Verification"));
    await user.type(screen.getByLabelText("Verified on"), "2026-10-14");
    await user.click(screen.getByText("Record verification"));
    await screen.findByText(/Record verification\?/i);
    await user.click(screen.getAllByRole("checkbox")[0]);
    await user.click(screen.getAllByRole("checkbox")[1]);
    await user.click(screen.getByText("Yes, record it"));
    await waitFor(() => {
      expect(screen.getByText(/last verified on/i)).toBeInTheDocument();
    });
  });

  it("surfaces the backend rejection of a future date", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: /Test Scholarship/ });
    await user.click(screen.getByText("Verification"));
    await user.type(screen.getByLabelText("Verified on"), "2099-01-01");
    expect(
      screen.getByText(/future date would be a false claim/i)
    ).toBeInTheDocument();
    expect(screen.getByText("Record verification")).toBeDisabled();
  });
});
