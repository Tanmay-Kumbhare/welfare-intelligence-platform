import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ProfileAuditAlert from "./ProfileAuditAlert";
import { citizenService } from "../../services/api";

vi.mock("../../services/api", () => ({
  citizenService: {
    audit: vi.fn(),
  },
}));

describe("ProfileAuditAlert", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const mockHealthyResponse = {
    data: {
      citizen_id: "cit-1",
      audited_at: "2026-10-12T10:00:00Z",
      summary: {
        total_issues: 0,
        confirmed_conflicts_count: 0,
        possible_conflicts_count: 0,
        stale_facts_count: 0,
        missing_information_count: 0,
        is_healthy: true,
        summary_message: "Profile is completely consistent and up to date; no conflicts or stale facts found.",
      },
      issues: [],
    },
  };

  const mockIssuesResponse = {
    data: {
      citizen_id: "cit-1",
      audited_at: "2026-10-12T10:00:00Z",
      summary: {
        total_issues: 4,
        confirmed_conflicts_count: 1,
        possible_conflicts_count: 1,
        stale_facts_count: 1,
        missing_information_count: 1,
        is_healthy: false,
        summary_message: "Audit detected: 1 confirmed conflict, 1 possible conflict, 1 potentially stale fact, 1 missing item.",
      },
      issues: [
        {
          issue_type: "CONFIRMED_CONFLICT",
          attribute_name: "annual_income",
          attribute_label: "Annual Family Income",
          current_value: "₹180000",
          conflicting_value: "₹120000",
          severity: "HIGH",
          description: "Direct profile annual income (₹180000) disagrees with stored profile fact (₹120000).",
          explanation: "Income criteria in scheme evaluations may produce differing outcomes.",
          sources: [
            {
              source_type: "PROFILE_RECORD",
              source_reference: "financial_profile.annual_income",
              value: 180000,
              verified: false,
            },
            {
              source_type: "INCOME_CERTIFICATE",
              source_reference: "profile_fact.ANNUAL_INCOME",
              value: 120000,
              verified: true,
            },
          ],
          affected_schemes: ["PM-KISAN", "State Merit Scholarship"],
          recommended_action: "Review and re-synchronize your income details.",
        },
        {
          issue_type: "POSSIBLE_CONFLICT",
          attribute_name: "land_holding_size",
          attribute_label: "Land Holding Size",
          current_value: "2.5 ha",
          conflicting_value: "1.5 ha",
          severity: "MEDIUM",
          description: "Profile land holding (2.5 ha) differs from unverified fact (1.5 ha).",
          explanation: "Farmer welfare schemes strictly enforce land threshold limits.",
          sources: [],
          affected_schemes: ["PM-KISAN"],
          recommended_action: "Confirm your actual land records.",
        },
        {
          issue_type: "STALE_FACT",
          attribute_name: "employment_status",
          attribute_label: "Employment Status",
          current_value: "UNEMPLOYED",
          conflicting_value: null,
          severity: "LOW",
          description: "Employment status was recorded 400 days ago (exceeds recommended validity period of 365 days).",
          explanation: "Welfare guidelines recommend refreshing employment status annually.",
          sources: [],
          affected_schemes: ["Unemployment Allowance Scheme"],
          recommended_action: "Verify and update your employment status.",
        },
        {
          issue_type: "MISSING_INFORMATION",
          attribute_name: "social_category",
          attribute_label: "Social Category / Caste",
          current_value: null,
          conflicting_value: null,
          severity: "MEDIUM",
          description: "Social category is not specified.",
          explanation: "Affirmative welfare schemes require verified social category membership.",
          sources: [],
          affected_schemes: ["Post-Matric Scholarship for SC/ST Students"],
          recommended_action: "Specify your social category in your profile.",
        },
      ],
    },
  };

  it("does not call citizenService.audit when citizenId is missing", () => {
    render(<ProfileAuditAlert citizenId={null} />);
    expect(citizenService.audit).not.toHaveBeenCalled();
  });

  it("renders loading state while audit request is in flight", () => {
    citizenService.audit.mockReturnValue(new Promise(() => {}));
    render(<ProfileAuditAlert citizenId="cit-1" />);
    expect(
      screen.getByText(/Auditing profile consistency and record freshness/i)
    ).toBeInTheDocument();
  });

  it("renders error state when audit request fails", async () => {
    citizenService.audit.mockRejectedValue(new Error("Network timeout"));
    render(<ProfileAuditAlert citizenId="cit-1" />);

    await waitFor(() => {
      expect(screen.getByText(/Profile Audit Unavailable/i)).toBeInTheDocument();
      expect(screen.getByText(/Network timeout/i)).toBeInTheDocument();
    });
  });

  it("renders healthy state when profile has no issues", async () => {
    citizenService.audit.mockResolvedValue(mockHealthyResponse);
    render(<ProfileAuditAlert citizenId="cit-1" />);

    await waitFor(() => {
      expect(screen.getByText(/Profile Consistent & Up-to-Date/i)).toBeInTheDocument();
      expect(
        screen.getByText(/Profile is completely consistent and up to date/i)
      ).toBeInTheDocument();
    });
  });

  it("renders attention banner and summary pills when issues exist", async () => {
    citizenService.audit.mockResolvedValue(mockIssuesResponse);
    render(
      <MemoryRouter>
        <ProfileAuditAlert citizenId="cit-1" />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/Profile Attention Required/i)).toBeInTheDocument();
    });
    expect(screen.getByText("4 Items")).toBeInTheDocument();
    expect(screen.getAllByText(/1 Confirmed Conflict/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/1 Possible Conflict/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("1 Stale Fact")).toBeInTheDocument();
    expect(screen.getByText("1 Missing Detail")).toBeInTheDocument();
  });

  it("toggles expanded details and displays categorized findings, sources, and affected schemes", async () => {
    citizenService.audit.mockResolvedValue(mockIssuesResponse);
    render(
      <MemoryRouter>
        <ProfileAuditAlert citizenId="cit-1" />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/Review Issues/i)).toBeInTheDocument();
    });

    // Expand details
    const toggleBtn = screen.getByRole("button", { name: /Review Issues/i });
    await userEvent.click(toggleBtn);

    expect(screen.getByText(/Hide Details/i)).toBeInTheDocument();
    expect(screen.getByText(/Confirmed Conflicts/i)).toBeInTheDocument();
    expect(screen.getByText(/Outdated \/ Stale Information/i)).toBeInTheDocument();
    expect(screen.getByText(/Missing Profile Information/i)).toBeInTheDocument();

    // Attribute details
    expect(screen.getByText("Annual Family Income")).toBeInTheDocument();
    expect(screen.getByText("₹180000")).toBeInTheDocument();
    expect(screen.getByText("₹120000")).toBeInTheDocument();
    expect(screen.getAllByText(/PM-KISAN/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Review and re-synchronize your income details/i)).toBeInTheDocument();

    // Stale fact & Missing info details
    expect(screen.getByText("Employment Status")).toBeInTheDocument();
    expect(screen.getByText("Social Category / Caste")).toBeInTheDocument();
    expect(screen.getByText(/Specify your social category in your profile/i)).toBeInTheDocument();

    // Verify read-only nature: link to profile settings without trigger of write calls
    expect(screen.getByRole("link", { name: /Update Profile in Settings/i })).toHaveAttribute(
      "href",
      "/profile"
    );
  });
});
