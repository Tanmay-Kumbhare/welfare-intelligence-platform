import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import DocumentsPage from "../DocumentsPage";
import { authService, citizenService, documentService } from "../../services/api";

vi.mock("../../services/api", () => ({
  authService: {
    me: vi.fn(),
  },
  citizenService: {
    get: vi.fn(),
  },
  documentService: {
    getRequirements: vi.fn(),
    upload: vi.fn(),
    delete: vi.fn(),
  },
  __esModule: true,
  default: {},
}));

const mockRequirements = {
  STUDENT: [
    {
      type: "AADHAAR_CARD",
      name: "Aadhaar Card",
      required: true,
      document: {
        document_id: "doc-1",
        original_filename: "aadhaar.pdf",
        detected_type: "AADHAAR_CARD",
        validation_status: "VALID",
        validation_message: "Valid Aadhaar Card",
      },
    },
    {
      type: "10TH_MARKSHEET",
      name: "10th Marksheet",
      required: true,
      document: {
        document_id: "doc-2",
        original_filename: "fake_sheet.pdf",
        detected_type: "UNKNOWN",
        validation_status: "INVALID",
        validation_message: "Does not match mark sheet format",
      },
    },
    {
      type: "INCOME_CERTIFICATE",
      name: "Income Certificate",
      required: true,
      document: {
        document_id: "doc-3",
        original_filename: "income.pdf",
        detected_type: "INCOME_CERTIFICATE",
        validation_status: "REVIEW_REQUIRED",
        validation_message: "Manual review required",
      },
    },
    {
      type: "CASTE_CERTIFICATE",
      name: "Caste Certificate",
      required: true,
      document: null,
    },
    {
      type: "SPORTS_CERTIFICATE",
      name: "Sports Certificate",
      required: false,
      document: null,
    },
  ],
};

describe("DocumentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authService.me.mockResolvedValue({
      data: { citizen_id: "cit-123" },
    });
    citizenService.get.mockResolvedValue({
      data: { citizen_id: "cit-123", full_name: "Aarav Sharma" },
    });
    documentService.getRequirements.mockResolvedValue({
      data: mockRequirements,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderPage = () => {
    return render(
      <BrowserRouter>
        <DocumentsPage />
      </BrowserRouter>
    );
  };

  it("renders loading state initially", () => {
    authService.me.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText(/loading your document requirements/i)).toBeInTheDocument();
  });

  it("shows error state when citizen profile is not found", async () => {
    authService.me.mockResolvedValue({ data: { citizen_id: null } });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/profile not found/i)).toBeInTheDocument();
    });
  });

  it("renders requirements, status badges, and summary counts correctly", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Your Documents")).toBeInTheDocument();
    });

    // Summary counts: 4 total required, 1 valid, 1 invalid, 1 review, 1 not uploaded
    expect(screen.getByText("4 total required documents")).toBeInTheDocument();
    expect(screen.getByText("1 valid")).toBeInTheDocument();
    expect(screen.getByText("1 invalid")).toBeInTheDocument();
    expect(screen.getByText("1 review required")).toBeInTheDocument();
    expect(screen.getByText("1 not uploaded")).toBeInTheDocument();

    // Check individual document items
    expect(screen.getByText("Aadhaar Card")).toBeInTheDocument();
    expect(screen.getByText("Valid")).toBeInTheDocument();

    expect(screen.getByText("10th Marksheet")).toBeInTheDocument();
    expect(screen.getByText("Incorrect document")).toBeInTheDocument();
    expect(screen.getByText("Does not match mark sheet format")).toBeInTheDocument();

    expect(screen.getByText("Income Certificate")).toBeInTheDocument();
    expect(screen.getByText("Review Required")).toBeInTheDocument();

    expect(screen.getByText("Caste Certificate")).toBeInTheDocument();
    expect(screen.getAllByText("Not uploaded").length).toBe(2);
  });

  it("uploads a document via documentService and triggers refresh", async () => {
    documentService.upload.mockResolvedValue({
      data: { message: "Uploaded" },
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Caste Certificate")).toBeInTheDocument();
    });

    const fileInput = screen.getByLabelText("Upload Caste Certificate");
    const testFile = new File(["dummy content"], "caste.pdf", { type: "application/pdf" });

    await userEvent.upload(fileInput, testFile);

    const uploadButton = screen.getByRole("button", { name: "Upload Document" });
    expect(uploadButton).toBeInTheDocument();

    await userEvent.click(uploadButton);

    await waitFor(() => {
      expect(documentService.upload).toHaveBeenCalledWith(
        "cit-123",
        expect.objectContaining({
          requirement_type: "CASTE_CERTIFICATE",
          filename: "caste.pdf",
          content_type: "application/pdf",
        })
      );
    });

    // Requirements refreshed
    expect(documentService.getRequirements).toHaveBeenCalledTimes(2);
  });

  it("deletes an existing uploaded document after user confirmation", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    documentService.delete.mockResolvedValue({
      data: { message: "Deleted" },
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Aadhaar Card")).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByRole("button", { name: "Delete Document" });
    expect(deleteButtons.length).toBeGreaterThan(0);

    await userEvent.click(deleteButtons[0]);

    expect(confirmSpy).toHaveBeenCalledWith("Are you sure you want to delete your uploaded Aadhaar Card?");
    await waitFor(() => {
      expect(documentService.delete).toHaveBeenCalledWith("cit-123", "doc-1");
    });

    // Should refresh requirements
    expect(documentService.getRequirements).toHaveBeenCalledTimes(2);
  });

  it("cancels document deletion when user declines confirmation", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Aadhaar Card")).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByRole("button", { name: "Delete Document" });
    await userEvent.click(deleteButtons[0]);

    expect(confirmSpy).toHaveBeenCalled();
    expect(documentService.delete).not.toHaveBeenCalled();
    expect(documentService.getRequirements).toHaveBeenCalledTimes(1);
  });

  it("displays an error message when document deletion fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    documentService.delete.mockRejectedValue({
      response: { data: { detail: "Document could not be deleted" } },
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Aadhaar Card")).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByRole("button", { name: "Delete Document" });
    await userEvent.click(deleteButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("Document could not be deleted")).toBeInTheDocument();
    });
  });
});
