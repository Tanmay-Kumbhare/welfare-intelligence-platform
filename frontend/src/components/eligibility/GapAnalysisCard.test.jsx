import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import GapAnalysisCard from "./GapAnalysisCard";

describe("GapAnalysisCard", () => {
  it("renders correctly with failed conditions, missing info, and document gaps", () => {
    const gapAnalysis = {
      has_gaps: true,
      summary_message: "2 eligibility conditions and 1 document need attention.",
      failed_conditions: [
        {
          parameter: "annual_income",
          parameter_label: "Annual family income",
          actual_value: 500000,
          actual_display: "₹5,00,000",
          required_value: "250000",
          operator: "<=",
          requirement_display: "Must be at most ₹2,50,000",
          rule_description: "Income under ceiling",
          message: "Annual family income (₹5,00,000) does not meet requirement: Must be at most ₹2,50,000.",
        },
      ],
      missing_information: [
        {
          parameter: "land_holding_size",
          parameter_label: "Land holding size",
          required_value: "2",
          operator: "<=",
          requirement_display: "Must be at most 2 hectares",
          rule_description: "Land holding requirement",
          message: "Land holding size is not provided in your profile.",
        },
      ],
      missing_documents: [
        {
          document_type: "INCOME_CERTIFICATE",
          document_name: "Income Certificate",
          status: "MISSING",
          required: true,
          message: "Income Certificate has not been uploaded.",
        },
      ],
    };

    render(<GapAnalysisCard gapAnalysis={gapAnalysis} />);

    // Section headings & counts
    expect(screen.getByText("Eligibility Gap Analysis")).toBeInTheDocument();
    expect(screen.getByText("3 potential gaps identified")).toBeInTheDocument();
    expect(screen.getByText("2 eligibility conditions and 1 document need attention.")).toBeInTheDocument();

    // 1. Criteria not met (Failed conditions)
    expect(screen.getByText(/Criteria Not Met \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText("Annual family income")).toBeInTheDocument();
    expect(screen.getByText("Does not meet requirement")).toBeInTheDocument();
    expect(screen.getByText("₹5,00,000")).toBeInTheDocument();

    // 2. Missing information
    expect(screen.getByText(/Missing Information \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText("Land holding size")).toBeInTheDocument();
    expect(screen.getByText("Information not provided")).toBeInTheDocument();
    expect(screen.getByText("Land holding size is not provided in your profile.")).toBeInTheDocument();

    // 3. Documents to review or provide
    expect(screen.getByText(/Documents to Review or Provide \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText("Income Certificate")).toBeInTheDocument();
    expect(screen.getByText("Income Certificate has not been uploaded.")).toBeInTheDocument();
    expect(screen.getByText("MISSING")).toBeInTheDocument();

    // Citizen-friendly non-guarantee disclaimer
    expect(
      screen.getByText(/Addressing these gaps helps align your profile criteria with scheme rules. It does not guarantee scheme eligibility, approval, or disbursement./i)
    ).toBeInTheDocument();
  });

  it("handles empty or absent gap analysis gracefully without rendering", () => {
    const { container: c1 } = render(<GapAnalysisCard gapAnalysis={null} />);
    expect(c1.firstChild).toBeNull();

    const { container: c2 } = render(<GapAnalysisCard gapAnalysis={undefined} />);
    expect(c2.firstChild).toBeNull();

    const { container: c3 } = render(
      <GapAnalysisCard
        gapAnalysis={{
          has_gaps: false,
          summary_message: "",
          failed_conditions: [],
          missing_information: [],
          missing_documents: [],
        }}
      />
    );
    expect(c3.firstChild).toBeNull();
  });

  it("renders invalid document gap with appropriate badge", () => {
    const gapAnalysis = {
      has_gaps: true,
      summary_message: "Document verification issue.",
      failed_conditions: [],
      missing_information: [],
      missing_documents: [
        {
          document_type: "CASTE_CERTIFICATE",
          document_name: "Caste Certificate",
          status: "INVALID",
          required: true,
          message: "Uploaded Caste Certificate is invalid or illegible.",
        },
      ],
    };

    render(<GapAnalysisCard gapAnalysis={gapAnalysis} />);
    expect(screen.getByText("Caste Certificate")).toBeInTheDocument();
    expect(screen.getByText("INVALID")).toBeInTheDocument();
    expect(screen.getByText("Uploaded Caste Certificate is invalid or illegible.")).toBeInTheDocument();
  });
});
