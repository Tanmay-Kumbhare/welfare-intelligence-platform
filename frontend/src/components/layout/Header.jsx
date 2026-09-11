import { NavLink } from "react-router-dom";
import { HelpCircle } from "lucide-react";

const PRIMARY_LINKS = [
  { to: "/", label: "Home", end: true },
  { to: "/schemes", label: "Schemes" },
  { to: "/explore", label: "Explore" },
  { to: "/check-eligibility", label: "Check Eligibility" },
  { to: "/profile", label: "My Profile" },
];

function navClasses({ isActive }) {
  return `font-sans text-sm px-3 py-2 border-b-2 transition-colors ${
    isActive
      ? "text-ink border-accent font-medium"
      : "text-ink-soft border-transparent hover:text-ink"
  }`;
}

export default function Header() {
  return (
    <header className="bg-paper-raised border-b-[3px] border-accent">
      <div className="max-w-[1040px] mx-auto px-5 sm:px-7 py-4 flex items-center justify-between gap-6 flex-wrap">
        <NavLink to="/" className="font-display font-semibold text-[22px] tracking-tight text-ink">
          Vidya<span className="text-accent-ink">Setu</span>
        </NavLink>

        <nav aria-label="Site pages" className="flex items-center gap-1 flex-wrap">
          {PRIMARY_LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end} className={navClasses}>
              {link.label}
            </NavLink>
          ))}
          <NavLink
            to="/help"
            className="flex items-center gap-1 font-sans text-sm px-3 py-2 text-ink-soft hover:text-ink"
          >
            <HelpCircle className="h-4 w-4" />
            Help
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
