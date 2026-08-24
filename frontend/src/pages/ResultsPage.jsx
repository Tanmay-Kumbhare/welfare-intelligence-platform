import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { recommendationService } from "../services/api";
import { CheckCircle, XCircle, FileText } from "lucide-react";

export default function ResultsPage() {
  const { citizenId } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    recommendationService.getForCitizen(citizenId)
      .then(res => setData(res.data))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, [citizenId]);

  if (loading) return <div className="text-center py-12">Loading recommendations...</div>;
  if (!data) return <div className="text-center py-12 text-red-500">Failed to load data.</div>;

  return (
    <div className="max-w-5xl mx-auto py-8">
      <div className="mb-8 flex justify-between items-center">
        <div>
          <h2 className="text-3xl font-bold text-gray-900">Your Eligibility Results</h2>
          <p className="text-gray-600 mt-2">
            Evaluated against {data.total_schemes_evaluated} schemes. You are eligible for {data.eligible_count}.
          </p>
        </div>
        <Link to="/" className="text-blue-600 hover:underline">Start Over</Link>
      </div>

      <div className="space-y-8">
        <section>
          <h3 className="text-2xl font-semibold text-green-700 border-b-2 border-green-200 pb-2 mb-4 flex items-center">
            <CheckCircle className="mr-2" /> Eligible Schemes ({data.eligible_count})
          </h3>
          {data.eligible_schemes.length === 0 ? (
            <p className="text-gray-500">No schemes found based on your current profile.</p>
          ) : (
            <div className="grid gap-6">
              {data.eligible_schemes.map(item => (
                <div key={item.scheme.scheme_id} className="bg-white p-6 rounded-lg shadow-sm border border-green-200 border-l-4 border-l-green-500">
                  <div className="flex justify-between items-start">
                    <div>
                      <h4 className="text-xl font-bold text-gray-900">{item.scheme.scheme_name}</h4>
                      <p className="text-sm text-gray-500">{item.scheme.department_name}</p>
                    </div>
                    {item.scheme.application_url && (
                      <a href={item.scheme.application_url} target="_blank" rel="noreferrer" className="bg-green-600 text-white px-4 py-2 rounded text-sm hover:bg-green-700">
                        Apply Now
                      </a>
                    )}
                  </div>
                  <p className="mt-4 text-gray-700">{item.scheme.benefit_description || item.scheme.description}</p>
                  
                  {item.documents?.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-gray-100">
                      <h5 className="font-medium flex items-center text-gray-700 text-sm mb-2">
                        <FileText className="w-4 h-4 mr-1" /> Required Documents
                      </h5>
                      <div className="flex flex-wrap gap-2">
                        {item.documents.map(doc => (
                          <span key={doc.document_id} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                            {doc.document_type.replace(/_/g, ' ')}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        <section>
          <h3 className="text-2xl font-semibold text-gray-600 border-b-2 border-gray-200 pb-2 mb-4 flex items-center">
            <XCircle className="mr-2 text-red-500" /> Ineligible Schemes ({data.ineligible_count})
          </h3>
          <div className="grid gap-4">
            {data.ineligible_schemes.map(item => (
              <div key={item.scheme.scheme_id} className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
                <h4 className="font-bold text-gray-800">{item.scheme.scheme_name}</h4>
                <p className="text-sm text-red-600 mt-1">{item.reason}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
