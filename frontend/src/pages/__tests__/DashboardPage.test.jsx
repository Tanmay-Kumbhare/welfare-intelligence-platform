import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import DashboardPage from '../DashboardPage';
import { authService, citizenService, recommendationService } from '../../services/api';
import api from '../../services/api';

// Mock dependencies
jest.mock('../../services/api', () => ({
  authService: {
    me: jest.fn(),
  },
  citizenService: {
    get: jest.fn(),
  },
  recommendationService: {
    getForCitizen: jest.fn(),
  },
  __esModule: true,
  default: {
    get: jest.fn(),
  },
}));

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockNavigate,
}));

describe('DashboardPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  const renderDashboard = () => {
    render(
      <BrowserRouter>
        <DashboardPage />
      </BrowserRouter>
    );
  };

  it('renders loading state initially', () => {
    authService.me.mockReturnValue(new Promise(() => {}));
    renderDashboard();
    expect(screen.getByText(/Loading your dashboard/i)).toBeInTheDocument();
  });

  it('shows welcome page if no citizen exists', async () => {
    authService.me.mockResolvedValue({ data: { citizen_id: null } });
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText(/Welcome to VidyaSetu/i)).toBeInTheDocument();
      expect(screen.getByText(/Complete your profile/i)).toBeInTheDocument();
    });
  });

  it('renders complete dashboard with profile types, counts, and missing documents', async () => {
    const citizenId = 'cit-123';
    authService.me.mockResolvedValue({ data: { citizen_id: citizenId } });
    
    citizenService.get.mockResolvedValue({
      data: {
        citizen_id: citizenId,
        full_name: 'Test Citizen',
        profile_types: ['STUDENT', 'FARMER'],
      }
    });

    recommendationService.getForCitizen.mockResolvedValue({
      data: {
        eligible_count: 5,
        ineligible_count: 2,
        eligible_schemes: [
          { scheme: { scheme_id: 's1', scheme_name: 'Scholarship 1' }, document_status: 'COMPLETE' },
          { scheme: { scheme_id: 's2', scheme_name: 'Scholarship 2' }, document_status: 'MISSING_DOCUMENTS' }
        ]
      }
    });

    api.get.mockResolvedValue({
      data: {
        STUDENT: [
          { type: '10TH_MARKSHEET', name: '10th Marksheet', required: true, document: { validation_status: 'VALID' } },
          { type: 'INCOME_CERTIFICATE', name: 'Income Certificate', required: true, document: null }, // Missing
        ],
        FARMER: [
          { type: 'LAND_RECORD', name: 'Land Record', required: true, document: { validation_status: 'INVALID' } },
        ]
      }
    });

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText(/Welcome back, Test Citizen/i)).toBeInTheDocument();
      expect(screen.getByText(/Profile Complete/i)).toBeInTheDocument();
      
      // Domains
      expect(screen.getByText(/STUDENT/i)).toBeInTheDocument();
      expect(screen.getByText(/FARMER/i)).toBeInTheDocument();
      
      // Eligibility
      expect(screen.getByText('5')).toBeInTheDocument(); // Eligible count
      expect(screen.getByText('2')).toBeInTheDocument(); // Ineligible count
      
      // Documents
      expect(screen.getByText('1')).toBeInTheDocument(); // Valid
      expect(screen.getByText('1')).toBeInTheDocument(); // Invalid (Land Record)
      expect(screen.getByText('1')).toBeInTheDocument(); // Not Uploaded (Income)
      
      // Missing Docs list
      expect(screen.getByText(/Documents needing attention/i)).toBeInTheDocument();
      expect(screen.getByText(/Income Certificate/i)).toBeInTheDocument();
      expect(screen.getByText(/Land Record/i)).toBeInTheDocument();

      // Recommended Schemes Preview
      expect(screen.getByText(/Scholarship 1/i)).toBeInTheDocument();
      expect(screen.getByText(/Documents Complete/i)).toBeInTheDocument();
      expect(screen.getByText(/Scholarship 2/i)).toBeInTheDocument();
      expect(screen.getByText(/Documents Pending/i)).toBeInTheDocument();
    });
  });
});
