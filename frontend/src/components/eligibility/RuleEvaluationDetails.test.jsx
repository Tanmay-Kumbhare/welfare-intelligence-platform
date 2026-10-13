import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import RuleEvaluationDetails from "./RuleEvaluationDetails";

describe("RuleEvaluationDetails", () => {
  it("renders correctly with passed, failed, and missing information rules", () => {
    const details = {
      groups: [
        {
          group_name: "General Criteria",
          intra_group_operator: "AND",
          rules: [
            {
              parameter: "age",
              actual: 25,
              operator: ">=",
              required: "18",
              passed: true,
              is_missing: false,
              description: "Must be 18 years or older",
            },
            {
              parameter: "annual_income",
              actual: 500000,
              operator: "<=",
              required: "250000",
              passed: false,
              is_missing: false,
              description: "Income must be under ₹2,50,000",
            },
            {
              parameter: "land_holding_size",
              actual: null,
              operator: "<=",
              required: "2",
              passed: false,
              is_missing: true,
              description: "Land holding required",
            },
          ],
        },
      ],
    };

    render(<RuleEvaluationDetails details={details} />);

    // Check passed condition
    expect(screen.getAllByText("Meets requirement").length).toBeGreaterThanOrEqual(1);

    // Check failed condition
    expect(screen.getAllByText("Does not meet requirement").length).toBeGreaterThanOrEqual(1);

    // Check missing condition
    expect(screen.getAllByText("Information not provided").length).toBeGreaterThanOrEqual(1);
  });

  it("handles null or empty details gracefully without errors", () => {
    const { container } = render(<RuleEvaluationDetails details={null} />);
    expect(container.firstChild).toBeNull();
  });
});
