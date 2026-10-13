import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AlternativeSchemesCard from "./AlternativeSchemesCard";

describe("AlternativeSchemesCard", () => {
  const sampleAlternatives = [
    {
      scheme_id: "sch-alt-1",
      scheme_name: "Farmer Support Scheme",
      department_name: "Agriculture Dept",
      scheme_category: "AGRICULTURE",
      rule_match_score: 100.0,
      suggestion_reason: "You meet the stored criteria for this scheme · offers benefits in the same category.",
      is_confirmed_eligible: true,
    },
    {
      scheme_id: "sch-alt-2",
      scheme_name: "Rural Livelihood Mission",
      department_name: "Rural Dev",
      scheme_category: "RURAL_DEVELOPMENT",
      rule_match_score: 75.0,
      suggestion_reason: "75.0% criteria match based on your profile.",
      is_confirmed_eligible: false,
    },
    {
      scheme_id: "sch-alt-3",
      scheme_name: "General Welfare Initiative",
      department_name: "Social Welfare",
      rule_match_score: null,
      suggestion_reason: "Suggested alternative based on your overall welfare profile.",
      is_confirmed_eligible: false,
    },
  ];

  it("renders alternative schemes with suggestion reasons, scores, and status tags", () => {
    render(
      <MemoryRouter>
        <AlternativeSchemesCard alternatives={sampleAlternatives} />
      </MemoryRouter>
    );

    // Header and counts
    expect(screen.getByText("Suggested Alternative Schemes")).toBeInTheDocument();
    expect(screen.getByText("3 suggestions")).toBeInTheDocument();

    // Scheme names
    expect(screen.getByText("Farmer Support Scheme")).toBeInTheDocument();
    expect(screen.getByText("Rural Livelihood Mission")).toBeInTheDocument();
    expect(screen.getByText("General Welfare Initiative")).toBeInTheDocument();

    // Confirmed eligible vs unconfirmed suggestions
    expect(screen.getByText("Confirmed Eligible")).toBeInTheDocument();
    expect(screen.getAllByText("Suggested Option").length).toBe(2);

    // Rule match scores
    expect(screen.getByText("Match: 100%")).toBeInTheDocument();
    expect(screen.getByText("Match: 75%")).toBeInTheDocument();

    // Suggestion reasons
    expect(
      screen.getByText("You meet the stored criteria for this scheme · offers benefits in the same category.")
    ).toBeInTheDocument();
    expect(screen.getByText("75.0% criteria match based on your profile.")).toBeInTheDocument();

    // Scheme navigation links
    const links = screen.getAllByRole("link", { name: /view scheme details/i });
    expect(links).toHaveLength(3);
    expect(links[0]).toHaveAttribute("href", "/schemes/sch-alt-1");

    // Disclaimer
    expect(
      screen.getByText("These are suggested alternatives, not a guarantee of eligibility or approval.")
    ).toBeInTheDocument();
  });

  it("filters out self-recommendation when targetSchemeId matches", () => {
    render(
      <MemoryRouter>
        <AlternativeSchemesCard
          alternatives={sampleAlternatives}
          targetSchemeId="sch-alt-1"
        />
      </MemoryRouter>
    );

    expect(screen.queryByText("Farmer Support Scheme")).not.toBeInTheDocument();
    expect(screen.getByText("Rural Livelihood Mission")).toBeInTheDocument();
    expect(screen.getByText("2 suggestions")).toBeInTheDocument();
  });

  it("handles null, undefined, or empty alternatives gracefully", () => {
    const { container: c1 } = render(
      <MemoryRouter>
        <AlternativeSchemesCard alternatives={null} />
      </MemoryRouter>
    );
    expect(c1.firstChild).toBeNull();

    const { container: c2 } = render(
      <MemoryRouter>
        <AlternativeSchemesCard alternatives={[]} />
      </MemoryRouter>
    );
    expect(c2.firstChild).toBeNull();

    const { container: c3 } = render(
      <MemoryRouter>
        <AlternativeSchemesCard
          alternatives={[{ scheme_id: "same-id", scheme_name: "Self" }]}
          targetSchemeId="same-id"
        />
      </MemoryRouter>
    );
    expect(c3.firstChild).toBeNull();
  });
});
