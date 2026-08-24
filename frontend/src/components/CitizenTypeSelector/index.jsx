import { User, Tractor, GraduationCap, Users } from "lucide-react";

export default function CitizenTypeSelector({ onSelect }) {
  const types = [
    { id: "FARMER", name: "Farmer", icon: Tractor, desc: "Agriculture and allied activities" },
    { id: "STUDENT", name: "Student", icon: GraduationCap, desc: "School, college or university" },
    { id: "SENIOR", name: "Senior Citizen", icon: Users, desc: "60 years and above" },
    { id: "GENERAL", name: "General Citizen", icon: User, desc: "Employed, self-employed or other" },
  ];

  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
      {types.map((t) => {
        const Icon = t.icon;
        return (
          <button
            key={t.id}
            onClick={() => onSelect(t.id)}
            className="flex flex-col items-center p-8 bg-white border border-gray-200 rounded-xl shadow-sm hover:border-blue-500 hover:ring-1 hover:ring-blue-500 transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            <Icon className="w-12 h-12 text-blue-600 mb-4" />
            <h3 className="text-xl font-medium text-gray-900">{t.name}</h3>
            <p className="mt-2 text-sm text-gray-500 text-center">{t.desc}</p>
          </button>
        );
      })}
    </div>
  );
}
