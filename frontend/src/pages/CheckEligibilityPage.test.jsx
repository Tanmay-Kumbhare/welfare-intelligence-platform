import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import CheckEligibilityPage from "./CheckEligibilityPage";
import * as api from "../services/api";
import { FORM_DETAIL, CITIZEN, submissionResponse, httpError, typedAnswer } from "../test/fixtures";

vi.mock("../services/api", () => ({
  authService: {
    me: vi.fn(),
  },
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
  recommendationService: {
    getForCitizen: vi.fn(),
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

const CITIZEN_FULL = {
  ...CITIZEN,
  date_of_birth: "2000-01-01",
  gender: "FEMALE",
  profile_status: "COMPLETE",
  profile_completion: 100,
  missing_fields: [],
};

const SAMPLE_RECOMMENDATION = {
  eligible_schemes: [
    {
      scheme: {
        scheme_id: "sch-0001",
        scheme_name: "Post Matric Scholarship",
        department_name: "Higher Education",
        status: "ACTIVE",
        benefit_description: "Financial assistance for post-matriculation studies.",
      },
      match_score: 95,
      document_status: "COMPLETE",
      scheme_documents: [],
    },
  ],
  ineligible_schemes: [],
};

beforeEach(() => {
  navigateMock.mockReset();
  localStorage.clear();
  api.authService.me.mockResolvedValue({
    data: { user_id: "user-001", citizen_id: CITIZEN.citizen_id },
  });
  api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
  api.formService.getActive.mockResolvedValue({ data: FORM_DETAIL });
  api.eligibilityService.evaluate.mockResolvedValue({ data: { message: "Evaluation complete" } });
  api.recommendationService.getForCitizen.mockResolvedValue({ data: SAMPLE_RECOMMENDATION });
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

function renderPage(initialEntries = ["/check-eligibility?mode=form"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <CheckEligibilityPage />
    </MemoryRouter>,
  );
}

describe("CheckEligibilityPage — form loading", () => {
  it("shows a loading state, then renders the API-driven form in questionnaire mode", async () => {
    api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
    renderPage();
    expect(screen.getByText(/loading your profile/i)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /citizen profile/i })).toBeInTheDocument();
    const sectionIndicators = await screen.findAllByText(/section 1 of 3/i);
    expect(sectionIndicators.length).toBeGreaterThan(0);
    expect(screen.getByLabelText(/marital status/i)).toBeInTheDocument();
  });

  it("shows an error state when the form API fails, with retry", async () => {
    api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
    api.formService.getActive.mockRejectedValue(httpError(500, {}));
    renderPage();
    expect(await screen.findByText(/unable to load eligibility service/i)).toBeInTheDocument();
    api.formService.getActive.mockResolvedValue({ data: FORM_DETAIL });
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("heading", { name: /citizen profile/i })).toBeInTheDocument();
  });

  it("renders sections and questions from the API definition, not hardcoded copies", async () => {
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
    const sectionIndicators = await screen.findAllByText(/section 1 of 1/i);
    expect(sectionIndicators.length).toBeGreaterThan(0);
  });
});

describe("CheckEligibilityPage — authentication and profile gates", () => {
  it("shows login gate when user is unauthenticated", async () => {
    api.authService.me.mockRejectedValue(httpError(401, { detail: "Unauthorized" }));
    renderPage(["/check-eligibility"]);
    expect(await screen.findByRole("heading", { name: /check your eligibility/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /login \/ register/i })).toBeInTheDocument();
  });

  it("shows incomplete profile gate when citizen profile is incomplete in clean mode", async () => {
    api.citizenService.get.mockResolvedValue({
      data: {
        ...CITIZEN_FULL,
        profile_status: "INCOMPLETE",
        profile_completion: 40,
        missing_fields: ["Annual Income", "Social Category"],
      },
    });
    renderPage(["/check-eligibility"]);
    expect(await screen.findByRole("heading", { name: /complete your profile/i })).toBeInTheDocument();
    expect(screen.getByText(/annual income/i)).toBeInTheDocument();
    expect(screen.getByText(/social category/i)).toBeInTheDocument();
    expect(screen.getByText(/40%/i)).toBeInTheDocument();
  });

  it("sends authenticated citizen_id on submission create", async () => {
    api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
    renderPage();
    await screen.findByRole("heading", { name: /citizen profile/i });
    await waitFor(() => expect(api.formSubmissionService.create).toHaveBeenCalled());
    expect(api.formSubmissionService.create.mock.calls[0][1].citizen_id).toBe(CITIZEN.citizen_id);
  });
});

describe("CheckEligibilityPage — wizard navigation and draft answers", () => {
  async function startOnForm() {
    api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
    renderPage();
    await screen.findByRole("heading", { name: /citizen profile/i });
  }

  it("navigates forward and backward through wizard sections", async () => {
    await startOnForm();
    await userEvent.selectOptions(await screen.findByLabelText(/marital status/i), "MARRIED");
    await userEvent.click(screen.getByRole("button", { name: /next section/i }));
    const s2Indicators = await screen.findAllByText(/section 2 of 3/i);
    expect(s2Indicators.length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: /^back$/i }));
    const s1Indicators = await screen.findAllByText(/section 1 of 3/i);
    expect(s1Indicators.length).toBeGreaterThan(0);
    expect(screen.getByLabelText(/marital status/i)).toHaveValue("MARRIED");
  });

  it("resumes a saved draft with answers restored", async () => {
    api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
    api.formSubmissionService.create.mockResolvedValue({
      data: submissionResponse({
        completion_percentage: 20,
        answers: [typedAnswer(FORM_DETAIL.sections[0].questions[0].question_id, "MARRIED")],
      }),
    });
    renderPage();
    expect(await screen.findByLabelText(/marital status/i)).toHaveValue("MARRIED");
  });

  it("hides conditional questions in response to answers", async () => {
    await startOnForm();
    await userEvent.click(await screen.findByRole("button", { name: /next section/i }));
    await screen.findAllByText(/section 2 of 3/i);
    await userEvent.selectOptions(screen.getByLabelText(/currently studying/i), "NO");
    expect(screen.queryByLabelText(/which course/i)).not.toBeInTheDocument();
  });
});

describe("CheckEligibilityPage — questionnaire completion and profile refresh lifecycle", () => {
  async function reachLastSection(initialCitizen = CITIZEN_FULL) {
    api.citizenService.get.mockResolvedValue({ data: initialCitizen });
    renderPage();
    await screen.findByRole("heading", { name: /citizen profile/i });
    // Section 1 -> 2
    const nextBtn1 = await screen.findByRole("button", { name: /next section/i });
    await userEvent.click(nextBtn1);
    await screen.findAllByText(/section 2 of 3/i);
    // Section 2 -> 3 (last section)
    const nextBtn2 = await screen.findByRole("button", { name: /next section/i });
    await userEvent.click(nextBtn2);
    await screen.findAllByText(/section 3 of 3/i);
  }

  it("refreshes citizen profile after normalization and runs eligibility check when profile becomes complete", async () => {
    const incompleteCitizen = {
      ...CITIZEN_FULL,
      profile_status: "INCOMPLETE",
      profile_completion: 50,
      missing_fields: ["Annual Income"],
    };
    const completedCitizen = {
      ...CITIZEN_FULL,
      profile_status: "COMPLETE",
      profile_completion: 100,
      missing_fields: [],
    };

    // Citizen starts incomplete
    await reachLastSection(incompleteCitizen);

    api.formSubmissionService.update.mockResolvedValue({ data: submissionResponse() });
    api.formSubmissionService.complete.mockResolvedValue({
      data: submissionResponse({ status: "COMPLETED", completed_at: "2026-09-16T10:05:00Z" }),
    });
    api.formSubmissionService.normalize.mockResolvedValue({
      data: { status: "NORMALIZED", facts_created: 8 },
    });

    // When citizen profile is refreshed after normalization, return completed profile
    api.citizenService.get.mockResolvedValue({ data: completedCitizen });

    await userEvent.click(screen.getByRole("button", { name: /submit & evaluate/i }));

    await waitFor(() => expect(api.formSubmissionService.normalize).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.citizenService.get).toHaveBeenCalledWith(CITIZEN.citizen_id));
    await waitFor(() => expect(api.eligibilityService.evaluate).toHaveBeenCalledWith(CITIZEN.citizen_id));
    await waitFor(() => expect(api.recommendationService.getForCitizen).toHaveBeenCalledWith(CITIZEN.citizen_id));

    // Displays recommendation results
    expect(await screen.findByRole("heading", { name: /eligible for you/i })).toBeInTheDocument();
    expect(screen.getByText(/post matric scholarship/i)).toBeInTheDocument();
  });

  it("blocks eligibility evaluation and shows missing fields if profile remains incomplete after normalization", async () => {
    const incompleteCitizen = {
      ...CITIZEN_FULL,
      profile_status: "INCOMPLETE",
      profile_completion: 50,
      missing_fields: ["Annual Income", "Social Category"],
    };
    const stillIncompleteCitizen = {
      ...CITIZEN_FULL,
      profile_status: "INCOMPLETE",
      profile_completion: 75,
      missing_fields: ["Annual Income"],
    };

    await reachLastSection(incompleteCitizen);

    api.formSubmissionService.update.mockResolvedValue({ data: submissionResponse() });
    api.formSubmissionService.complete.mockResolvedValue({
      data: submissionResponse({ status: "COMPLETED", completed_at: "2026-09-16T10:05:00Z" }),
    });
    api.formSubmissionService.normalize.mockResolvedValue({
      data: { status: "NORMALIZED", facts_created: 4 },
    });

    // Re-fetched citizen profile is still INCOMPLETE
    api.citizenService.get.mockResolvedValue({ data: stillIncompleteCitizen });

    await userEvent.click(screen.getByRole("button", { name: /submit & evaluate/i }));

    await waitFor(() => expect(api.formSubmissionService.normalize).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.citizenService.get).toHaveBeenCalledWith(CITIZEN.citizen_id));

    // Must NOT run eligibility evaluation or fetch recommendations
    expect(api.eligibilityService.evaluate).not.toHaveBeenCalled();
    expect(api.recommendationService.getForCitizen).not.toHaveBeenCalled();

    // Renders incomplete profile gate showing the remaining missing field
    expect(await screen.findByRole("heading", { name: /complete your profile/i })).toBeInTheDocument();
    expect(screen.getByText(/annual income/i)).toBeInTheDocument();
    expect(screen.queryByText(/social category/i)).not.toBeInTheDocument();
    expect(screen.getByText(/75%/i)).toBeInTheDocument();
  });

  it("shows error state when submission update fails", async () => {
    await reachLastSection();
    api.formSubmissionService.update.mockRejectedValue(httpError(500, { detail: "Server error" }));
    await userEvent.click(screen.getByRole("button", { name: /submit & evaluate/i }));
    expect(await screen.findByText(/failed to submit form answers/i)).toBeInTheDocument();
  });
});

describe("CheckEligibilityPage — clean eligibility view", () => {
  it("evaluates eligibility and displays recommendations on button click", async () => {
    api.citizenService.get.mockResolvedValue({ data: CITIZEN_FULL });
    renderPage(["/check-eligibility"]);
    expect(await screen.findByRole("heading", { name: /check scheme eligibility/i })).toBeInTheDocument();
    expect(screen.getByText(/profile complete/i)).toBeInTheDocument();

    const checkButton = screen.getByRole("button", { name: /check my eligibility/i });
    await userEvent.click(checkButton);

    await waitFor(() => expect(api.eligibilityService.evaluate).toHaveBeenCalledWith(CITIZEN.citizen_id));
    await waitFor(() => expect(api.recommendationService.getForCitizen).toHaveBeenCalledWith(CITIZEN.citizen_id));
    expect(await screen.findByRole("heading", { name: /eligible for you/i })).toBeInTheDocument();
  });
});
