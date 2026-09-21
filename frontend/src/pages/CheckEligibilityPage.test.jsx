import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import CheckEligibilityPage from "./CheckEligibilityPage";
import * as api from "../services/api";
import { setStoredCitizenId } from "../utils/citizenStorage";
import { FORM_DETAIL, CITIZEN, submissionResponse, httpError, typedAnswer } from "../test/fixtures";

vi.mock("../services/api", () => ({
  citizenService: {
    get: vi.fn(),
    register: vi.fn(),
  },
  formService: {
    getActive: vi.fn(),
  },
  eligibilityService: {
    evaluate: vi.fn(),
  },
  formSubmissionService: {
    create: vi.fn(),
    get: vi.fn(),
    update: vi.fn(),
    complete: vi.fn(),
    normalize: vi.fn(),
  },
}));

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, useNavigate: () => navigateMock };
});

beforeEach(() => {
  navigateMock.mockReset();
  localStorage.clear();
  api.formService.getActive.mockResolvedValue({ data: FORM_DETAIL });
  api.eligibilityService.evaluate.mockResolvedValue({ data: {} });
  api.formSubmissionService.create.mockResolvedValue({ data: submissionResponse() });
  api.formSubmissionService.update.mockImplementation((id, body) =>
    Promise.resolve({
      data: submissionResponse({
        completion_percentage: 40,
        answers: body.answers.map((a) => typedAnswer(a.question_id, a.value)),
      }),
    }),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPage() {
  return render(
    <MemoryRouter>
      <CheckEligibilityPage />
    </MemoryRouter>,
  );
}

const CITIZEN_FULL = {
  ...CITIZEN,
  date_of_birth: "2000-01-01",
  gender: "FEMALE",
};

describe("CheckEligibilityPage — form loading", () => {
  it("shows a loading state, then renders the API-driven form", async () => {
    setStoredCitizenId(CITIZEN.citizen_id);
    api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
    renderPage();
    expect(screen.getByText(/loading your profile/i)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /citizen profile/i })).toBeInTheDocument();
    expect(await screen.findByText(/section 1 of 3/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/marital status/i)).toBeInTheDocument();
  });

  it("shows an error state when the form API fails, with retry", async () => {
    setStoredCitizenId(CITIZEN.citizen_id);
    api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
    api.formService.getActive.mockRejectedValue(httpError(500, {}));
    renderPage();
    expect(await screen.findByText(/unable to load the form/i)).toBeInTheDocument();
    api.formService.getActive.mockResolvedValue({ data: FORM_DETAIL });
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    // After retry the form loads on top of the still-valid citizen context.
    expect(await screen.findByRole("heading", { name: /citizen profile/i })).toBeInTheDocument();
  });

  it("renders sections and questions from the API definition, not hardcoded copies", async () => {
    setStoredCitizenId(CITIZEN.citizen_id);
    api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
    const custom = {
      ...FORM_DETAIL,
      form_name: "Custom Profile",
      sections: [
        {
          ...FORM_DETAIL.sections[0],
          section_name: "Totally Custom Section",
          questions: [FORM_DETAIL.sections[0].questions[0]],
        },
      ],
    };
    api.formService.getActive.mockResolvedValue({ data: custom });
    renderPage();
    expect(await screen.findByRole("heading", { name: /custom profile/i })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /totally custom section/i })).toBeInTheDocument();
    expect(screen.getByText(/section 1 of 1/i)).toBeInTheDocument();
  });
});

describe("CheckEligibilityPage — identity gate", () => {
  it("shows first-time registration when no citizen exists, then loads the form", async () => {
    api.citizenService.get.mockRejectedValue(httpError(404, {}));
    renderPage();
    expect(await screen.findByText(/create your citizen profile/i)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/full name/i), "New Citizen");
    await userEvent.type(screen.getByLabelText(/date of birth/i), "2000-01-01");
    api.citizenService.register.mockResolvedValue({ data: CITIZEN_FULL });
    await userEvent.click(screen.getByRole("button", { name: /create profile and continue/i }));
    expect(api.citizenService.register).toHaveBeenCalled();
    // Stored for later pages, and the already-loaded form renders immediately.
    expect(localStorage.getItem("vidyasetu.citizen_id")).toBe(CITIZEN.citizen_id);
    expect(await screen.findByRole("heading", { name: /citizen profile/i })).toBeInTheDocument();
  });

  it("clears a stale citizen pointer and recovers to registration", async () => {
    setStoredCitizenId("stale-id");
    api.citizenService.get.mockRejectedValue(httpError(404, {}));
    renderPage();
    expect(await screen.findByText(/create your citizen profile/i)).toBeInTheDocument();
    expect(localStorage.getItem("vidyasetu.citizen_id")).toBeNull();
  });

  it("does not ask identity questions again for a returning citizen", async () => {
    setStoredCitizenId(CITIZEN.citizen_id);
    api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
    renderPage();
    expect(await screen.findByRole("heading", { name: /citizen profile/i })).toBeInTheDocument();
    // The registration form never appears; identity is summarized read-only.
    expect(screen.queryByText(/create your citizen profile/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^full name$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^date of birth$/i)).not.toBeInTheDocument();
    expect(screen.getByText(/answering as/i)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(CITIZEN_FULL.full_name))).toBeInTheDocument();
  });

  it("sends the stored citizen_id on submission create", async () => {
    setStoredCitizenId(CITIZEN.citizen_id);
    api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
    renderPage();
    await screen.findByRole("heading", { name: /citizen profile/i });
    await waitFor(() => expect(api.formSubmissionService.create).toHaveBeenCalled());
    expect(api.formSubmissionService.create.mock.calls[0][1].citizen_id).toBe(CITIZEN.citizen_id);
  });
});

describe("CheckEligibilityPage — wizard, save, resume", () => {
  async function startOnForm() {
    setStoredCitizenId(CITIZEN.citizen_id);
    api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
    renderPage();
    await screen.findByRole("heading", { name: /citizen profile/i });
  }

  it("saves answers and advances on Save & continue", async () => {
    await startOnForm();
    await userEvent.selectOptions(await screen.findByLabelText(/marital status/i), "MARRIED");
    await userEvent.click(screen.getByRole("button", { name: /save & continue/i }));
    await waitFor(() => expect(api.formSubmissionService.update).toHaveBeenCalled());
    const [submissionId, body] = api.formSubmissionService.update.mock.calls[0];
    expect(submissionId).toBe(submissionResponse().submission_id);
    expect(body.citizen_id).toBe(CITIZEN.citizen_id);
    expect(body.answers).toEqual(
      expect.arrayContaining([expect.objectContaining({ question_id: FORM_DETAIL.sections[0].questions[0].question_id, value: "MARRIED" })]),
    );
    expect(await screen.findByText(/section 2 of 3/i)).toBeInTheDocument();
  });

  it("keeps answers locally when a save fails and allows retry", async () => {
    await startOnForm();
    await userEvent.selectOptions(await screen.findByLabelText(/marital status/i), "MARRIED");
    api.formSubmissionService.update.mockRejectedValueOnce(httpError(500, {}));
    await userEvent.click(screen.getByRole("button", { name: /save & continue/i }));
    expect(await screen.findByText(/something went wrong while saving/i)).toBeInTheDocument();
    // Answers retained: retry succeeds and carries the typed value.
    await userEvent.click(screen.getByRole("button", { name: /save & continue/i }));
    const [, body] = api.formSubmissionService.update.mock.calls[1];
    expect(body.answers.some((a) => a.value === "MARRIED")).toBe(true);
    expect(await screen.findByText(/section 2 of 3/i)).toBeInTheDocument();
  });

  it("resumes a saved draft with answers restored (refresh preserves context)", async () => {
    setStoredCitizenId(CITIZEN.citizen_id);
    api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
    api.formSubmissionService.create.mockResolvedValue({
      data: submissionResponse({
        completion_percentage: 20,
        answers: [typedAnswer(FORM_DETAIL.sections[0].questions[0].question_id, "MARRIED")],
      }),
    });
    renderPage();
    expect(await screen.findByLabelText(/marital status/i)).toHaveValue("MARRIED");
    expect(screen.getByText(/progress saved/i)).toBeInTheDocument();
  });

  it("hides conditional questions in response to answers (no value sent when hidden)", async () => {
    await startOnForm();
    await userEvent.click(screen.getByRole("button", { name: /save & continue/i }));
    await screen.findByText(/section 2 of 3/i);
    await userEvent.selectOptions(screen.getByLabelText(/currently studying/i), "NO");
    expect(screen.queryByLabelText(/which course/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /save & continue/i }));
    const [, body] = api.formSubmissionService.update.mock.calls.at(-1);
    const courseQuestion = FORM_DETAIL.sections[1].questions[1];
    expect(body.answers.find((a) => a.question_id === courseQuestion.question_id)).toBeUndefined();
  });
});

describe("CheckEligibilityPage — submission lifecycle", () => {
  async function reachReview() {
    setStoredCitizenId(CITIZEN.citizen_id);
    api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
    api.formSubmissionService.create.mockResolvedValue({
      data: submissionResponse({
        answers: [
          typedAnswer(FORM_DETAIL.sections[0].questions[0].question_id, "MARRIED"),
          typedAnswer(FORM_DETAIL.sections[2].questions[0].question_id, 240000),
        ],
      }),
    });
    renderPage();
    await screen.findByRole("heading", { name: /citizen profile/i });
    // Advance through the wizard to the last section, then review.
    await userEvent.click(await screen.findByRole("button", { name: /save & continue/i }));
    await screen.findByText(/section 2 of 3/i);
    await userEvent.click(screen.getByRole("button", { name: /save & continue/i }));
    await screen.findByText(/section 3 of 3/i);
    await userEvent.click(screen.getByRole("button", { name: /review & submit/i }));
    await screen.findByText(/review your information/i);
  }

  it("review shows sections with edit actions", async () => {
    await reachReview();
    expect(screen.getAllByRole("button", { name: /^edit$/i }).length).toBe(3);
    await userEvent.click(screen.getAllByRole("button", { name: /^edit$/i })[1]);
    expect(await screen.findByText(/section 2 of 3/i)).toBeInTheDocument();
  });

  it("completes, normalizes, evaluates eligibility, then navigates to results", async () => {
    await reachReview();
    api.formSubmissionService.complete.mockResolvedValue({ data: submissionResponse({ status: "COMPLETED", completed_at: "2026-09-16T10:05:00Z" }) });
    api.formSubmissionService.normalize.mockResolvedValue({ data: { status: "NORMALIZED", facts_created: 8 } });
    await userEvent.click(screen.getByRole("button", { name: /submit and check eligibility/i }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/results/${CITIZEN.citizen_id}`));
    expect(api.formSubmissionService.complete).toHaveBeenCalledTimes(1);
    expect(api.formSubmissionService.normalize).toHaveBeenCalledTimes(1);
    expect(api.eligibilityService.evaluate).toHaveBeenCalledTimes(1);
  });

  it("maps backend missing-required errors to the right questions and section", async () => {
    await reachReview();
    api.formSubmissionService.complete.mockRejectedValue(
      httpError(422, { detail: { message: "Incomplete", missing_required: ["ANNUAL_INCOME"] } }),
    );
    await userEvent.click(screen.getByRole("button", { name: /submit and check eligibility/i }));
    await screen.findByText(/some required answers are still missing/i);
    // Landed on the Financial section (contains ANNUAL_INCOME).
    expect(screen.getByText(/section 3 of 3/i)).toBeInTheDocument();
    expect(screen.getByText(/this answer is required/i)).toBeInTheDocument();
  });

  it("does not call normalization when completion fails", async () => {
    await reachReview();
    api.formSubmissionService.complete.mockRejectedValue(httpError(422, { detail: { message: "Incomplete", missing_required: ["ANNUAL_INCOME"] } }));
    await userEvent.click(screen.getByRole("button", { name: /submit and check eligibility/i }));
    await screen.findByText(/some required answers are still missing/i);
    expect(api.formSubmissionService.normalize).not.toHaveBeenCalled();
  });
});
