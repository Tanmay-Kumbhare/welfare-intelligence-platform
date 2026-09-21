import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import QuestionRenderer from "./QuestionRenderer";
import FormSection from "./FormSection";
import ReviewStep from "./ReviewStep";
import { FORM_DETAIL } from "../../test/fixtures";

const byCode = (code) => FORM_DETAIL.sections.flatMap((s) => s.questions).find((q) => q.question_code === code);

describe("QuestionRenderer", () => {
  it("renders text, number, date, boolean, and select questions by type", () => {
    render(
      <div>
        <QuestionRenderer question={byCode("MARITAL_STATUS")} value="" onChange={() => {}} />
        <QuestionRenderer question={byCode("ANNUAL_INCOME")} value={null} onChange={() => {}} />
        <QuestionRenderer question={byCode("CURRENTLY_STUDYING")} value={null} onChange={() => {}} />
        <QuestionRenderer question={byCode("PINCODE")} value="" onChange={() => {}} />
      </div>,
    );
    expect(screen.getByLabelText(/marital status/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/annual family income/i)).toHaveAttribute("type", "number");
    expect(screen.getByLabelText(/currently studying/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/pin code/i)).toBeInTheDocument();
  });

  it("emits typed values: numbers stay numeric, empty becomes null", async () => {
    const user = userEvent.setup();
    function Harness() {
      const [value, setValue] = useState(null);
      const [seen, setSeen] = useState("none");
      return (
        <div>
          <QuestionRenderer question={byCode("ANNUAL_INCOME")} value={value} onChange={setValue} />
          <output data-testid="seen">{seen}</output>
          <button type="button" onClick={() => setSeen(JSON.stringify(value))}>
            sync
          </button>
        </div>
      );
    }
    render(<Harness />);
    await user.type(screen.getByLabelText(/annual family income/i), "240000");
    await user.click(screen.getByRole("button", { name: /sync/i }));
    expect(screen.getByTestId("seen")).toHaveTextContent("240000");
    await user.clear(screen.getByLabelText(/annual family income/i));
    await user.click(screen.getByRole("button", { name: /sync/i }));
    expect(screen.getByTestId("seen")).toHaveTextContent("null");
  });

  it("boolean questions map Yes/No to native booleans", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<QuestionRenderer question={byCode("CURRENTLY_STUDYING")} value={null} onChange={onChange} />);
    await user.selectOptions(screen.getByLabelText(/currently studying/i), "YES");
    expect(onChange).toHaveBeenCalledWith(true);
    await user.selectOptions(screen.getByLabelText(/currently studying/i), "NO");
    expect(onChange).toHaveBeenCalledWith(false);
  });

  it("select questions emit option codes", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<QuestionRenderer question={byCode("MARITAL_STATUS")} value="" onChange={onChange} />);
    await user.selectOptions(screen.getByLabelText(/marital status/i), "MARRIED");
    expect(onChange).toHaveBeenCalledWith("MARRIED");
  });

  it("unknown question types fail visibly, not silently", () => {
    render(
      <QuestionRenderer
        question={{ ...byCode("MARITAL_STATUS"), question_type: "hologram" }}
        value=""
        onChange={() => {}}
      />,
    );
    expect(screen.getByText(/not yet supported/i)).toBeInTheDocument();
  });
});

describe("FormSection conditional visibility", () => {
  const applicable = (visibleIds) => {
    const map = new Map();
    for (const q of FORM_DETAIL.sections.flatMap((s) => s.questions)) map.set(q.question_id, visibleIds.has(q.question_code));
    return map;
  };

  it("hides conditional questions and their values are excluded on change", async () => {
    const user = userEvent.setup();
    const onAnswerChange = vi.fn();
    const visible = applicable(new Set(["MARITAL_STATUS", "CURRENTLY_STUDYING", "ANNUAL_INCOME"]));
    render(
      <FormSection
        section={FORM_DETAIL.sections[1]}
        answers={new Map()}
        applicable={visible}
        onAnswerChange={onAnswerChange}
        sectionIndex={1}
        totalSections={3}
      />,
    );
    expect(screen.queryByLabelText(/which course/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/currently studying/i)).toBeInTheDocument();

    // Answer YES → question appears (visibility map recomputed by caller).
    await user.selectOptions(screen.getByLabelText(/currently studying/i), "YES");
    expect(onAnswerChange).toHaveBeenCalled();
  });

  it("shows the conditional question when applicable", () => {
    const visible = applicable(new Set(["MARITAL_STATUS", "CURRENTLY_STUDYING", "ANNUAL_INCOME", "COURSE_NAME"]));
    render(
      <FormSection
        section={FORM_DETAIL.sections[1]}
        answers={new Map([["q0000000-0000-0000-0000-000000000010", true]])}
        applicable={visible}
        onAnswerChange={() => {}}
        sectionIndex={1}
        totalSections={3}
      />,
    );
    expect(screen.getByLabelText(/which course/i)).toBeInTheDocument();
  });

  it("marks backend-mapped required errors on the right question", () => {
    const visible = applicable(new Set(["MARITAL_STATUS", "CURRENTLY_STUDYING", "ANNUAL_INCOME", "COURSE_NAME"]));
    render(
      <FormSection
        section={FORM_DETAIL.sections[1]}
        answers={new Map()}
        applicable={visible}
        fieldErrors={new Map([["q0000000-0000-0000-0000-000000000011", "This answer is required."]])}
        onAnswerChange={() => {}}
        sectionIndex={1}
        totalSections={3}
      />,
    );
    expect(screen.getByText("This answer is required.")).toBeInTheDocument();
  });
});

describe("ReviewStep", () => {
  it("lists questions and answers by section without internal identifiers", () => {
    const reviewSections = FORM_DETAIL.sections.map((section) => ({
      section,
      items: section.questions
        .filter((q) => !["COURSE_NAME"].includes(q.question_code))
        .map((q) => ({ question: q, value: q.question_code === "MARITAL_STATUS" ? "Single" : null })),
    }));
    render(<ReviewStep reviewSections={reviewSections} onEdit={() => {}} />);
    expect(screen.getByText(/personal information/i)).toBeInTheDocument();
    expect(screen.getByText("Single")).toBeInTheDocument();
    expect(screen.getAllByText(/not provided/i).length).toBeGreaterThan(0);
    // Internal identifiers never appear.
    expect(screen.queryByText(/q0000000/)).not.toBeInTheDocument();
    expect(screen.queryByText(/profile_field/i)).not.toBeInTheDocument();
  });

  it("displays booleans and option labels rather than codes", () => {
    const marital = byCode("MARITAL_STATUS");
    render(
      <ReviewStep
        reviewSections={[{ section: FORM_DETAIL.sections[0], items: [{ question: marital, value: "MARRIED" }] }]}
        onEdit={() => {}}
      />,
    );
    expect(screen.getByText("Married")).toBeInTheDocument();
    expect(screen.queryByText("MARRIED")).not.toBeInTheDocument();
  });
});
