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
});
