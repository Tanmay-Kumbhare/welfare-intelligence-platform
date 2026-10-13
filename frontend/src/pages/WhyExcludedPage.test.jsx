import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import WhyExcludedPage from "./WhyExcludedPage";
import * as api from "../services/api";

vi.mock("../services/api", () => ({
  recommendationService: {
    getForCitizen: vi.fn(),
  },
}));

describe("WhyExcludedPage gap analysis integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders gap analysis card and rule evaluation details for ineligible scheme", async () => {
    const citizenId = "cit-123";
    const schemeId = "sch-999";

    api.recommendationService.getForCitizen.mockResolvedValue({
      data: {
        citizen_id: citizenId,
        ineligible_schemes: [
          {
            scheme: {
              scheme_id: schemeId,
              scheme_name: "Post-Matric Scholarship",
              department_name: "Education Dept",
              scheme_category: "EDUCATION",
            },
            reason: "Not eligible due to income and student status.",
            gap_analysis: {
              has_gaps: true,
              summary_message: "Income criteria was not met and caste certificate is missing.",
              failed_conditions: [
                {
                  parameter: "annual_income",
                  parameter_label: "Annual family income",
                  actual_value: 400000,
                  actual_display: "₹4,00,000",
                  required_value: "250000",
                  operator: "<=",
                  requirement_display: "Must be at most ₹2,50,000",
                  message: "Income exceeds ceiling.",
                },
              ],
              missing_information: [],
              missing_documents: [
                {
                  document_type: "CASTE_CERTIFICATE",
                  document_name: "Caste Certificate",
                  status: "MISSING",
                  required: true,
                  message: "Caste Certificate is required.",
                },
              ],
            },
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={[`/why-excluded/${citizenId}/${schemeId}`]}>
        <Routes>
          <Route path="/why-excluded/:citizenId/:schemeId" element={<WhyExcludedPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Post-Matric Scholarship")).toBeInTheDocument();
    });

    // Check gap analysis integration
    expect(screen.getByText("Eligibility Gap Analysis")).toBeInTheDocument();
    expect(screen.getByText("Income exceeds ceiling.")).toBeInTheDocument();
    expect(screen.getByText("Caste Certificate is required.")).toBeInTheDocument();
  });

  it("renders alternative schemes card on WhyExcludedPage when alternatives exist", async () => {
    const citizenId = "cit-123";
    const schemeId = "sch-target-excl";

    api.recommendationService.getForCitizen.mockResolvedValue({
      data: {
        citizen_id: citizenId,
        ineligible_schemes: [
          {
            scheme: {
              scheme_id: schemeId,
              scheme_name: "PM-Awas Urban",
            },
            reason: "Does not meet urban residency requirement.",
            alternative_schemes: [
              {
                scheme_id: "sch-alt-rural",
                scheme_name: "PM-Awas Gramin",
                department_name: "Rural Housing",
                rule_match_score: 95.0,
                suggestion_reason: "Same housing category and you meet rural criteria.",
                is_confirmed_eligible: true,
              },
            ],
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={[`/why-excluded/${citizenId}/${schemeId}`]}>
        <Routes>
          <Route path="/why-excluded/:citizenId/:schemeId" element={<WhyExcludedPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("PM-Awas Urban")).toBeInTheDocument();
    });

    expect(screen.getByText("Suggested Alternative Schemes")).toBeInTheDocument();
    expect(screen.getByText("PM-Awas Gramin")).toBeInTheDocument();
    expect(screen.getByText("Confirmed Eligible")).toBeInTheDocument();
    expect(screen.getByText("Same housing category and you meet rural criteria.")).toBeInTheDocument();
  });
});
