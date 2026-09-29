import { useEffect, useState } from "react";
import { UploadCloud, CheckCircle, XCircle, Clock } from "lucide-react";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import { LoadingState, ErrorState } from "../components/ui/StatusStates";
import { authService, citizenService } from "../services/api";
import { getStoredCitizenId, clearStoredCitizenId } from "../utils/citizenStorage";
import axios from "axios"; // Using standard axios or we can use our api singleton
import api from "../services/api";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

const fileToBase64 = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.onerror = error => reject(error);
});

function DocumentUploadCard({ requirement, citizenId, onUploadComplete }) {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const doc = requirement.document;

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
      setError(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const base64 = await fileToBase64(file);
      await api.post(`/documents/upload/${citizenId}`, {
        requirement_type: requirement.type,
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        content_base64: base64
      });
      setFile(null);
      onUploadComplete();
    } catch (err) {
      setError(err?.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <Card className="mb-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-medium text-ink flex items-center gap-2">
            {requirement.name}
            {requirement.required ? (
              <Badge variant="excl">REQUIRED</Badge>
            ) : (
              <Badge variant="neutral">OPTIONAL</Badge>
            )}
          </h3>
          
          <div className="mt-4">
            {doc ? (
              <div>
                <p className="text-sm font-mono text-ink-soft mb-1">Status:</p>
                <div className="flex items-center gap-2">
                  {doc.validation_status === "VALID" && <CheckCircle className="h-5 w-5 text-ok" />}
                  {doc.validation_status === "INVALID" && <XCircle className="h-5 w-5 text-excl" />}
                  {doc.validation_status === "REVIEW_REQUIRED" && <Clock className="h-5 w-5 text-accent-ink" />}
                  {doc.validation_status === "PENDING" && <Clock className="h-5 w-5 text-ink-soft" />}
                  <span className={doc.validation_status === "INVALID" ? "text-excl-ink font-medium" : doc.validation_status === "REVIEW_REQUIRED" ? "text-accent-ink font-medium" : "text-ink font-medium"}>
                    {doc.validation_status === "VALID" ? "Valid" : doc.validation_status === "INVALID" ? "Incorrect document" : doc.validation_status === "REVIEW_REQUIRED" ? "Review Required" : "Uploaded"}
                  </span>
                </div>
                
                <div className="mt-3 text-sm flex items-center gap-2">
                  <span className="font-semibold text-ink-soft">Detected type:</span>
                  <span className="text-ink font-medium">{doc.detected_type.replace(/_/g, ' ')}</span>
                </div>

                <div className="mt-2 text-sm text-ink bg-surface p-3 rounded border border-line">
                  <p className="font-semibold mb-1">Validation message:</p>
                  <span className={doc.validation_status === "INVALID" ? "text-excl-ink" : "text-ink"}>{doc.validation_message}</span>
                </div>
                
                <div className="text-xs text-ink-soft mt-3">File: {doc.original_filename}</div>
              </div>
            ) : (
              <p className="text-sm text-ink-soft flex items-center gap-2">
                <XCircle className="h-4 w-4 text-ink-soft" /> Not uploaded
              </p>
            )}
          </div>
        </div>
        
        <div className="flex flex-col gap-2 min-w-[200px]">
          <input 
            type="file" 
            id={`file-${requirement.type}`} 
            className="text-sm text-ink-soft file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-medium file:bg-surface file:text-ink hover:file:bg-line cursor-pointer"
            onChange={handleFileChange}
          />
          {file && (
            <Button onClick={handleUpload} disabled={uploading}>
              {uploading ? "Uploading..." : doc ? "Replace Document" : "Upload Document"}
            </Button>
          )}
          {error && <p className="text-xs text-excl-ink mt-1">{error}</p>}
        </div>
      </div>
    </Card>
  );
}

export default function DocumentsPage() {
  const [identity, setIdentity] = useState(null);
  const [requirements, setRequirements] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchRequirements = async (citizenId) => {
    try {
      const response = await api.get(`/documents/requirements/${citizenId}`);
      setRequirements(response.data);
    } catch (err) {
      setError("Unable to load document requirements.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const loadCitizen = async () => {
      try {
        const me = await authService.me();
        const citizenId = me.data?.citizen_id;
        if (citizenId) {
          const response = await citizenService.get(citizenId);
          setIdentity({ citizenId: response.data.citizen_id, fullName: response.data.full_name });
          fetchRequirements(response.data.citizen_id);
          return;
        }
      } catch {}
      
      const stored = getStoredCitizenId();
      if (!stored) {
        setLoading(false);
        return;
      }
      try {
        const response = await citizenService.get(stored);
        setIdentity({ citizenId: response.data.citizen_id, fullName: response.data.full_name });
        fetchRequirements(response.data.citizen_id);
      } catch {
        clearStoredCitizenId();
        setLoading(false);
      }
    };
    loadCitizen();
  }, []);

  if (loading) return <LoadingState label="Loading your document requirements..." />;
  if (!identity) return <ErrorState title="Profile not found" message="Please create a citizen profile first." />;
  if (error) return <ErrorState title="Error" message={error} />;

  let totalRequired = 0;
  let validCount = 0;
  let invalidCount = 0;
  let reviewCount = 0;
  let notUploadedCount = 0;

  Object.values(requirements || {}).forEach(reqs => {
    reqs.forEach(req => {
      if (req.required) {
        totalRequired++;
        if (!req.document) {
          notUploadedCount++;
        } else if (req.document.validation_status === "VALID") {
          validCount++;
        } else if (req.document.validation_status === "INVALID") {
          invalidCount++;
        } else if (req.document.validation_status === "REVIEW_REQUIRED") {
          reviewCount++;
        } else {
          notUploadedCount++;
        }
      }
    });
  });

  return (
    <div className="max-w-[800px]">
      <header className="border-b border-line pb-7 mb-8">
        <h1 className="text-[32px] leading-tight mb-3">Your Documents</h1>
        <p className="max-w-[68ch] mb-3">
          Upload documents required for your profile type. 
          The system will automatically verify whether the correct document type was provided.
        </p>
      </header>

      {totalRequired > 0 && (
        <Card className="mb-8 bg-surface border-accent">
          <h3 className="text-lg font-semibold mb-3">Required Documents Summary</h3>
          <p className="text-sm text-ink-soft mb-4">{totalRequired} total required document{totalRequired !== 1 ? 's' : ''}</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div className="flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-ok" />
              <span>{validCount} valid</span>
            </div>
            <div className="flex items-center gap-2">
              <XCircle className="h-4 w-4 text-excl" />
              <span>{invalidCount} invalid</span>
            </div>
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-accent-ink" />
              <span>{reviewCount} review required</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="h-4 w-4 rounded-full border border-ink-soft flex-shrink-0" />
              <span>{notUploadedCount} not uploaded</span>
            </div>
          </div>
        </Card>
      )}
      
      {Object.entries(requirements || {}).map(([domain, reqs]) => (
        <section key={domain} className="mb-10">
          <h2 className="text-2xl mb-4 font-semibold text-ink border-b border-line pb-2">
            {domain} Documents
          </h2>
          {reqs.length === 0 ? (
            <p className="text-ink-soft text-sm">No documents required for this section.</p>
          ) : (
            <div className="space-y-4">
              {reqs.map((req) => (
                <DocumentUploadCard 
                  key={req.type} 
                  requirement={req} 
                  citizenId={identity.citizenId} 
                  onUploadComplete={() => fetchRequirements(identity.citizenId)} 
                />
              ))}
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
