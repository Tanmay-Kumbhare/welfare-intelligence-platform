import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ResultsPage from "./ResultsPage";
import * as api from "../services/api";

vi.mock("../services/api", () => ({
  citizenService: {
    get: vi.fn(),
  },
  eligibilityService: {
    evaluate: vi.fn(),
  },
  recommendationService: {
    getForCitizen: vi.fn(),
  },
}));

describe("ResultsPage Task 2 integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders rule match scores, disclaimer, and recommendation explanations", async () => {
    const citizenId = "cit-123";
    api.citizenService.get.mockResolvedValue({
      data: {
        citizen_id: citizenId,
        full_name: "Test Citizen",
        citizen_type: "Farmer",
        location: { state: "Maharashtra" },
      },
    });

    api.eligibilityService.evaluate.mockResolvedValue({ data: [] });

    api.recommendationService.getForCitizen.mockResolvedValue({
      data: {
        citizen_id: citizenId,
        total_schemes_evaluated: 2,
        eligible_count: 1,
        ineligible_count: 1,
        eligible_schemes: [
          {
            scheme: {
              scheme_id: "sch-1",
              scheme_name: "PM-KISAN Scheme",
              status: "ACTIVE",
            },
            eligibility_result: true,
            rule_match_score: 100.0,
            recommendation_explanation: "Perfect fit based on land holding and farming status.",
          },
        ],
        ineligible_schemes: [
          {
            scheme: {
              scheme_id: "sch-2",
              scheme_name: "Post-Matric Scholarship",
              status: "ACTIVE",
            },
            eligibility_result: false,
            rule_match_score: 50.0,
            recommendation_explanation: "Partial match on age but requires student status.",
            reason: "Citizen is not a student.",
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={[`/results/${citizenId}`]}>
        <Routes>
          <Route path="/results/:citizenId" element={<ResultsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("PM-KISAN Scheme")).toBeInTheDocument();
    });

    // Check Rule Match Score indicators
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();

    // Check official disclaimer text
    expect(
      screen.getByText(
        "Rule match score indicates criteria alignment based on stored profile information. It is not a guarantee of government grant approval or disbursement."
      )
    ).toBeInTheDocument();

    // Check recommendation explanations
    expect(
      screen.getByText("Perfect fit based on land holding and farming status.")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Partial match on age but requires student status.")
    ).toBeInTheDocument();
  });

  it("handles null rule match score and explanation gracefully", async () => {
    const citizenId = "cit-456";
    api.citizenService.get.mockResolvedValue({
      data: { citizen_id: citizenId, full_name: "Test Citizen 2" },
    });
    api.eligibilityService.evaluate.mockResolvedValue({ data: [] });
    api.recommendationService.getForCitizen.mockResolvedValue({
      data: {
        citizen_id: citizenId,
        eligible_schemes: [
          {
            scheme: {
              scheme_id: "sch-3",
              scheme_name: "Legacy Scheme",
              status: "ACTIVE",
            },
            eligibility_result: true,
            rule_match_score: null,
            recommendation_explanation: null,
          },
        ],
        ineligible_schemes: [],
      },
    });

    render(
      <MemoryRouter initialEntries={[`/results/${citizenId}`]}>
        <Routes>
          <Route path="/results/:citizenId" element={<ResultsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Legacy Scheme")).toBeInTheDocument();
    });

    // Verify it doesn't render "Match Score" or "Why recommended" for null values
    expect(screen.queryByText(/Match Score:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Why recommended:/i)).not.toBeInTheDocument();
  });

  it("renders gap analysis card on scheme cards when gap_analysis data is present", async () => {
    const citizenId = "cit-789";
    api.citizenService.get.mockResolvedValue({
      data: { citizen_id: citizenId, full_name: "Test Citizen 3" },
    });
    api.eligibilityService.evaluate.mockResolvedValue({ data: [] });
    api.recommendationService.getForCitizen.mockResolvedValue({
      data: {
        citizen_id: citizenId,
        eligible_schemes: [],
        ineligible_schemes: [
          {
            scheme: {
              scheme_id: "sch-gap",
              scheme_name: "Farmer Subsidy Scheme",
              status: "ACTIVE",
            },
            eligibility_result: false,
            rule_match_score: 50.0,
            gap_analysis: {
              has_gaps: true,
              summary_message: "1 condition not met.",
              failed_conditions: [
                {
                  parameter: "land_holding_size",
                  parameter_label: "Land holding size",
                  actual_value: 5,
                  actual_display: "5 hectares",
                  required_value: "2",
                  operator: "<=",
                  requirement_display: "Must be at most 2 hectares",
                  message: "Land holding size (5 hectares) exceeds requirement.",
                },
              ],
              missing_information: [],
              missing_documents: [],
            },
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={[`/results/${citizenId}`]}>
        <Routes>
          <Route path="/results/:citizenId" element={<ResultsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Farmer Subsidy Scheme")).toBeInTheDocument();
    });

    expect(screen.getByText("Eligibility Gap Analysis")).toBeInTheDocument();
    expect(screen.getByText("Land holding size (5 hectares) exceeds requirement.")).toBeInTheDocument();
  });

  it("renders alternative schemes card on ineligible scheme cards when data is present", async () => {
    const citizenId = "cit-alt-user";
    api.citizenService.get.mockResolvedValue({
      data: { citizen_id: citizenId, full_name: "Test Citizen Alternatives" },
    });
    api.eligibilityService.evaluate.mockResolvedValue({ data: [] });
    api.recommendationService.getForCitizen.mockResolvedValue({
      data: {
        citizen_id: citizenId,
        eligible_schemes: [],
        ineligible_schemes: [
          {
            scheme: {
              scheme_id: "sch-target",
              scheme_name: "Target Ineligible Scheme",
              status: "ACTIVE",
            },
            eligibility_result: false,
            rule_match_score: 40.0,
            alternative_schemes: [
              {
                scheme_id: "sch-alt-discovered",
                scheme_name: "Alternative Support Scheme",
                department_name: "Welfare Dept",
                rule_match_score: 90.0,
                suggestion_reason: "Matches your farming category and profile.",
                is_confirmed_eligible: true,
              },
            ],
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={[`/results/${citizenId}`]}>
        <Routes>
          <Route path="/results/:citizenId" element={<ResultsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Target Ineligible Scheme")).toBeInTheDocument();
    });

    expect(screen.getByText("Suggested Alternative Schemes")).toBeInTheDocument();
    expect(screen.getByText("Alternative Support Scheme")).toBeInTheDocument();
    expect(screen.getByText("Confirmed Eligible")).toBeInTheDocument();
    expect(screen.getByText("Matches your farming category and profile.")).toBeInTheDocument();
  });

  it("renders What-If Simulation component on ResultsPage for valid citizenId", async () => {
    const citizenId = "cit-sim-integ";
    api.citizenService.get.mockResolvedValue({
      data: { citizen_id: citizenId, full_name: "Citizen Sim" },
    });
    api.eligibilityService.evaluate.mockResolvedValue({ data: [] });
    api.recommendationService.getForCitizen.mockResolvedValue({
      data: {
        citizen_id: citizenId,
        eligible_schemes: [],
        ineligible_schemes: [],
      },
    });

    render(
      <MemoryRouter initialEntries={[`/results/${citizenId}`]}>
        <Routes>
          <Route path="/results/:citizenId" element={<ResultsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("What-If Eligibility Simulation")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /open simulation/i })).toBeInTheDocument();
  });

  it("renders prominent warning for stale eligible schemes and hides normal confirmation text", async () => {
    const citizenId = "cit-stale-eligible";
    api.citizenService.get.mockResolvedValue({
      data: { citizen_id: citizenId, full_name: "Citizen Stale" },
    });
    api.eligibilityService.evaluate.mockResolvedValue({ data: [] });
    api.recommendationService.getForCitizen.mockResolvedValue({
      data: {
        citizen_id: citizenId,
        eligible_schemes: [
          {
            scheme: {
              scheme_id: "sch-stale-1",
              scheme_name: "Modified Subsidy Scheme",
              status: "ACTIVE",
            },
            eligibility_result: true,
            is_stale: true,
            rule_match_score: 95.0,
            recommendation_explanation: "Scheme rules changed since your last evaluation.",
          },
        ],
        ineligible_schemes: [],
      },
    });

    render(
      <MemoryRouter initialEntries={[`/results/${citizenId}`]}>
        <Routes>
          <Route path="/results/:citizenId" element={<ResultsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Modified Subsidy Scheme")).toBeInTheDocument();
    });

    // Warning message and badges must be displayed
    expect(
      screen.getByText(
        "Scheme rules have changed since your last evaluation. This result may no longer be accurate. Re-evaluate before relying on it."
      )
    ).toBeInTheDocument();
    expect(screen.getAllByText(/STALE/i).length).toBeGreaterThan(0);

    // Normal confirmation text must NOT be displayed for stale items
    expect(
      screen.queryByText("Your information meets the stored eligibility requirements.")
    ).not.toBeInTheDocument();

    // Visual distinction: card has amber accent border, not green ok border
    const cardElement = screen.getByText("Modified Subsidy Scheme").closest(".bg-paper-raised");
    expect(cardElement).toHaveClass("border-l-accent");
    expect(cardElement).not.toHaveClass("border-l-ok");
  });

  it("renders prominent warning for stale ineligible schemes as well", async () => {
    const citizenId = "cit-stale-ineligible";
    api.citizenService.get.mockResolvedValue({
      data: { citizen_id: citizenId, full_name: "Citizen Ineligible Stale" },
    });
    api.eligibilityService.evaluate.mockResolvedValue({ data: [] });
    api.recommendationService.getForCitizen.mockResolvedValue({
      data: {
        citizen_id: citizenId,
        eligible_schemes: [],
        ineligible_schemes: [
          {
            scheme: {
              scheme_id: "sch-stale-2",
              scheme_name: "Updated Pension Scheme",
              status: "ACTIVE",
            },
            eligibility_result: false,
            is_stale: true,
            rule_match_score: 40.0,
            reason: "Age threshold was updated.",
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={[`/results/${citizenId}`]}>
        <Routes>
          <Route path="/results/:citizenId" element={<ResultsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Updated Pension Scheme")).toBeInTheDocument();
    });

    // Warning message and badge must be present in ineligible section
    expect(
      screen.getByText(
        "Scheme rules have changed since your last evaluation. This result may no longer be accurate. Re-evaluate before relying on it."
      )
    ).toBeInTheDocument();
    expect(screen.getAllByText(/STALE/i).length).toBeGreaterThan(0);

    // Definitive ineligibility statement must NOT be displayed for stale items
    expect(
      screen.queryByText(
        "You are not currently eligible because this eligibility condition was not satisfied."
      )
    ).not.toBeInTheDocument();

    // Neutral statement must be displayed instead
    expect(
      screen.getByText(
        "Your previous evaluation found that you did not meet the stored eligibility requirements. Because the scheme rules have changed, this result may no longer be accurate."
      )
    ).toBeInTheDocument();
  });

  it("handles HTTP 422 incomplete profile by displaying incomplete profile banner with missing field labels", async () => {
    const citizenId = "cit-inc-1";
    api.citizenService.get.mockResolvedValue({
      data: { citizen_id: citizenId, full_name: "Incomplete Citizen" },
    });
    api.eligibilityService.evaluate.mockRejectedValue({
      response: {
        status: 422,
        data: {
          detail: {
            message: "Profile is incomplete for eligibility evaluation. Please complete required profile fields.",
            profile_status: "INCOMPLETE",
            profile_completion: 40,
            missing_field_labels: ["Annual Income", "Social Category", "State / Location"],
          },
        },
      },
    });

    render(
      <MemoryRouter initialEntries={[`/results/${citizenId}`]}>
        <Routes>
          <Route path="/results/:citizenId" element={<ResultsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Profile Incomplete")).toBeInTheDocument();
    });

    expect(screen.getByText(/Evaluation Paused: Missing Information/i)).toBeInTheDocument();
    expect(screen.getByText("Annual Income")).toBeInTheDocument();
    expect(screen.getByText("Social Category")).toBeInTheDocument();
    expect(screen.getByText("State / Location")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();

    // Verify navigation links
    const questionnaireBtn = screen.getByRole("link", { name: /Complete Profile Questionnaire/i });
    expect(questionnaireBtn).toHaveAttribute("href", "/check-eligibility");

    const profileBtn = screen.getByRole("link", { name: /View Profile Details/i });
    expect(profileBtn).toHaveAttribute("href", "/profile");

    // Must NOT fall through to EmptyState
    expect(screen.queryByText(/No evaluated schemes currently match/i)).not.toBeInTheDocument();
  });

  it("handles HTTP 422 with missing_fields fallback if missing_field_labels is absent", async () => {
    const citizenId = "cit-inc-2";
    api.citizenService.get.mockResolvedValue({
      data: { citizen_id: citizenId, full_name: "Incomplete Citizen 2" },
    });
    api.eligibilityService.evaluate.mockRejectedValue({
      response: {
        status: 422,
        data: {
          detail: {
            message: "Profile is incomplete for eligibility evaluation.",
            missing_fields: ["Date of Birth", "Gender"],
          },
        },
      },
    });

    render(
      <MemoryRouter initialEntries={[`/results/${citizenId}`]}>
        <Routes>
          <Route path="/results/:citizenId" element={<ResultsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Profile Incomplete")).toBeInTheDocument();
    });

    expect(screen.getByText("Date of Birth")).toBeInTheDocument();
    expect(screen.getByText("Gender")).toBeInTheDocument();
    expect(screen.queryByText(/No evaluated schemes currently match/i)).not.toBeInTheDocument();
  });

  it("preserves fallback to stored recommendations on non-404, non-422 evaluation failure", async () => {
    const citizenId = "cit-tol-1";
    api.citizenService.get.mockResolvedValue({
      data: { citizen_id: citizenId, full_name: "Tolerant Citizen" },
    });
    api.eligibilityService.evaluate.mockRejectedValue({
      response: { status: 500, data: { detail: "Internal Server Error" } },
    });
    api.recommendationService.getForCitizen.mockResolvedValue({
      data: {
        citizen_id: citizenId,
        eligible_schemes: [
          {
            scheme: {
              scheme_id: "sch-stored",
              scheme_name: "Previously Stored Scheme",
              status: "ACTIVE",
            },
            eligibility_result: true,
            rule_match_score: 95.0,
          },
        ],
        ineligible_schemes: [],
      },
    });

    render(
      <MemoryRouter initialEntries={[`/results/${citizenId}`]}>
        <Routes>
          <Route path="/results/:citizenId" element={<ResultsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Previously Stored Scheme")).toBeInTheDocument();
    });
  });

  it("renders information needed schemes in a dedicated section with missing critical facts", async () => {
    const citizenId = "cit-tri-state";
    api.citizenService.get.mockResolvedValue({
      data: { citizen_id: citizenId, full_name: "Tri-State Citizen", citizen_type: "Student" },
    });
    api.eligibilityService.evaluate.mockResolvedValue({ data: [] });
    api.recommendationService.getForCitizen.mockResolvedValue({
      data: {
        citizen_id: citizenId,
        total_schemes_evaluated: 3,
        eligible_count: 1,
        ineligible_count: 1,
        information_needed_count: 1,
        eligible_schemes: [
          {
            scheme: { scheme_id: "sch-1", scheme_name: "Eligible Scheme", status: "ACTIVE" },
            eligibility_result: true,
            rule_match_score: 100.0,
          },
        ],
        ineligible_schemes: [
          {
            scheme: { scheme_id: "sch-2", scheme_name: "Ineligible Scheme", status: "ACTIVE" },
            eligibility_result: false,
            rule_match_score: 25.0,
          },
        ],
        information_needed_schemes: [
          {
            scheme: { scheme_id: "sch-3", scheme_name: "Scholarship with Income Cap", status: "ACTIVE" },
            eligibility_result: false,
            eligibility_status: "INSUFFICIENT_INFORMATION",
            rule_match_score: 50.0,
            reason: "Eligibility cannot be determined: missing information for annual_income.",
            missing_critical_facts: ["annual_income"],
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={[`/results/${citizenId}`]}>
        <Routes>
          <Route path="/results/:citizenId" element={<ResultsPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Scholarship with Income Cap")).toBeInTheDocument();
    });

    expect(screen.getByText("INFORMATION NEEDED")).toBeInTheDocument();
    expect(screen.getByText("Information needed")).toBeInTheDocument();
    expect(screen.getByText("annual income")).toBeInTheDocument();
    expect(screen.getByText("Provide missing info")).toBeInTheDocument();
  });
});
