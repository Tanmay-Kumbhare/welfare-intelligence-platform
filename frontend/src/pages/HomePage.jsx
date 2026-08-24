import { useNavigate } from "react-router-dom";
import CitizenTypeSelector from "../components/CitizenTypeSelector";

export default function HomePage() {
  const navigate = useNavigate();

  const handleSelectType = (type) => {
    navigate(`/profile?type=${type}`);
  };

  return (
    <div className="max-w-3xl mx-auto py-12">
      <div className="text-center mb-12">
        <h2 className="text-3xl font-extrabold text-gray-900 sm:text-4xl">
          Find Your Welfare Schemes
        </h2>
        <p className="mt-4 text-lg text-gray-500">
          Select your primary occupation or status to get started. We will guide you through a quick profile to find schemes you are eligible for.
        </p>
      </div>
      <CitizenTypeSelector onSelect={handleSelectType} />
    </div>
  );
}
