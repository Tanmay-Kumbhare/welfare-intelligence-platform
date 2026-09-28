import { NavLink, Outlet } from "react-router-dom";
import { LayoutDashboard, Users, Landmark, FileText, FlaskConical } from "lucide-react";
import AdminGate from "../../components/auth/AdminGate";
import Footer from "../../components/layout/Footer";

const ADMIN_LINKS = [
  { to: "/admin", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/admin/users", label: "Users", icon: Users },
  { to: "/admin/schemes", label: "Schemes", icon: Landmark },
  { to: "/admin/submissions", label: "Submissions", icon: FileText },
  { to: "/admin/sources", label: "Sources", icon: FlaskConical },
];

function adminNavClasses({ isActive }) {
  return `flex items-center gap-2 px-3 py-2 text-sm rounded-sm transition-colors ${
    isActive
      ? "bg-accent text-white font-medium"
      : "text-ink-soft hover:text-ink hover:bg-accent-tint"
  }`;
}

/**
 * Admin area layout: own sidebar, separate from the citizen Header.
 * Wrapped in AdminGate so only admins reach anything inside.
 */
export default function AdminLayout() {
  return (
    <AdminGate>
      <div className="min-h-[70vh] w-full max-w-[1040px] mx-auto px-5 sm:px-7 py-8 flex flex-col md:flex-row gap-8">
        <aside className="md:w-52 shrink-0">
          <div className="mb-4">
            <p className="text-xs uppercase tracking-wide text-ink-soft">Administration</p>
            <h2 className="text-lg font-display font-semibold text-ink">VidyaSetu Admin</h2>
          </div>
          <nav aria-label="Admin sections" className="flex md:flex-col gap-1 flex-wrap">
            {ADMIN_LINKS.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} className={adminNavClasses}>
                <Icon className="h-4 w-4" />
                {label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
      </div>
      <Footer />
    </AdminGate>
  );
}
