import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EligibilitySimulation from "./EligibilitySimulation";
import * as api from "../../services/api";

vi.mock("../../services/api", () => ({
  eligibilityService: {
    simulate: vi.fn(),
  },
}));

describe("EligibilitySimulation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const mockSimulationResponse = {
    data: {
      citizen_id: "cit-sim-1",
      hypothetical_inputs: { annual_income: 150000, land_holding_size: 1.5 },
      total_schemes_evaluated: 2,
      newly_eligible_count: 1,
      newly_ineligible_count: 0,
      unaltered_eligible_count: 1,
      improved_score_count: 1,
      overall_summary: "Simulated overrides made you newly eligible for 1 scheme.",
      simulated_schemes: [
        {
          scheme_id: "sch-kisan",
          scheme_name: "PM-KISAN",
          department_name: "Agriculture Dept",
          scheme_category: "AGRICULTURE",
          baseline_eligible: false,
          simulated_eligible: true,
          baseline_match_score: 50.0,
          simulated_match_score: 100.0,
          outcome_change: "BECAME_ELIGIBLE",
          summary_explanation: "Land holding size now meets <= 2 ha requirement.",
          changed_conditions: [
            {
              parameter: "land_holding_size",
              parameter_label: "Land holding size",
              baseline_value: 3.5,
              simulated_value: 1.5,
              baseline_passed: false,
              simulated_passed: true,
              status: "IMPROVED",
            },
          ],
        },
      ],
    },
  };

  it("renders closed by default and toggles open to display form and disclaimer", async () => {
    const user = userEvent.setup();
    render(<EligibilitySimulation citizenId="cit-sim-1" />);

    expect(screen.getByText("What-If Eligibility Simulation")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open simulation/i })).toBeInTheDocument();

    // Not yet open
    expect(screen.queryByLabelText(/annual family income/i)).not.toBeInTheDocument();

    // Open simulation
    await user.click(screen.getByRole("button", { name: /open simulation/i }));

    expect(screen.getByLabelText(/annual family income/i)).toBeInTheDocument();
    expect(screen.getByText(/what-if simulation results are purely hypothetical/i)).toBeInTheDocument();
  });

  it("submits valid hypothetical overrides and renders comparative baseline vs simulated results", async () => {
    const user = userEvent.setup();
    api.eligibilityService.simulate.mockResolvedValue(mockSimulationResponse);

    render(<EligibilitySimulation citizenId="cit-sim-1" />);
    await user.click(screen.getByRole("button", { name: /open simulation/i }));

    const incomeInput = screen.getByLabelText(/annual family income/i);
    const landInput = screen.getByLabelText(/land holding size/i);

    await user.type(incomeInput, "150000");
    await user.type(landInput, "1.5");

    await user.click(screen.getByRole("button", { name: /run simulation/i }));

    expect(api.eligibilityService.simulate).toHaveBeenCalledWith("cit-sim-1", {
      annual_income: 150000,
      land_holding_size: 1.5,
    });

    await waitFor(() => {
      expect(screen.getByText("Simulation Comparison")).toBeInTheDocument();
    });

    // Overview counters
    expect(screen.getByText("+1")).toBeInTheDocument();
    expect(screen.getByText(/simulated overrides made you newly eligible for 1 scheme/i)).toBeInTheDocument();

    // Scheme comparisons
    expect(screen.getByText("PM-KISAN")).toBeInTheDocument();
    expect(screen.getAllByText("Newly Eligible").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Baseline")).toBeInTheDocument();
    expect(screen.getByText("Simulated")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();

    // Condition delta
    expect(screen.getByText("Changed Conditions:")).toBeInTheDocument();
    expect(screen.getByText("IMPROVED")).toBeInTheDocument();
    expect(screen.getByText("1.5")).toBeInTheDocument();
  });

  it("shows error when submitting without any overrides", async () => {
    const user = userEvent.setup();
    render(<EligibilitySimulation citizenId="cit-sim-1" />);
    await user.click(screen.getByRole("button", { name: /open simulation/i }));

    await user.click(screen.getByRole("button", { name: /run simulation/i }));

    expect(api.eligibilityService.simulate).not.toHaveBeenCalled();
    expect(
      screen.getByText(/please specify at least one hypothetical profile attribute/i)
    ).toBeInTheDocument();
  });

  it("shows error and prevents call when citizenId is missing", async () => {
    const user = userEvent.setup();
    render(<EligibilitySimulation citizenId={null} />);
    await user.click(screen.getByRole("button", { name: /open simulation/i }));

    const incomeInput = screen.getByLabelText(/annual family income/i);
    await user.type(incomeInput, "200000");

    await user.click(screen.getByRole("button", { name: /run simulation/i }));

    expect(api.eligibilityService.simulate).not.toHaveBeenCalled();
    expect(
      screen.getByText(/citizen profile id is required/i)
    ).toBeInTheDocument();
  });

  it("handles API error gracefully and displays error feedback", async () => {
    const user = userEvent.setup();
    api.eligibilityService.simulate.mockRejectedValue({
      response: { data: { detail: "Citizen profile not found" } },
    });

    render(<EligibilitySimulation citizenId="cit-sim-1" />);
    await user.click(screen.getByRole("button", { name: /open simulation/i }));

    const incomeInput = screen.getByLabelText(/annual family income/i);
    await user.type(incomeInput, "200000");

    await user.click(screen.getByRole("button", { name: /run simulation/i }));

    await waitFor(() => {
      expect(screen.getByText("Citizen profile not found")).toBeInTheDocument();
    });
  });
});
