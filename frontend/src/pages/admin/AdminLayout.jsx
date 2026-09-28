import { NavLink, Outlet, Link as RouterLink, useNavigate } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import {
  LayoutDashboard,
  Users,
  Landmark,
  FileText,
  FlaskConical,
  LogOut,
  ExternalLink,
  ShieldCheck,
} from "lucide-react";
import AdminGate from "../../components/auth/AdminGate";
import { getUser, clearAuth } from "../../services/auth";
import { authService } from "../../services/api";

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
 * Admin area shell: completely separate from the citizen site. Own top bar
 * (brand + admin nav + account), own footer. Citizen navigation (Home,
 * Schemes, Explore...) deliberately does not appear here. Wrapped in
 * AdminGate so only admins reach anything inside.
 */
export default function AdminLayout() {
  const navigate = useNavigate();
  const user = getUser();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  const handleLogout = async () => {
    setMenuOpen(false);
    try {
      await authService.logout().catch(() => {});
    } finally {
      clearAuth();
      navigate("/login");
    }
  };

  return (
    <AdminGate>
      <div className="min-h-screen flex flex-col bg-paper">
        {/* Admin top bar — distinct visual identity from the citizen header */}
        <header className="bg-ink text-white">
          <div className="max-w-[1200px] mx-auto px-5 sm:px-7 py-3 flex items-center justify-between gap-6 flex-wrap">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-accent" />
              <span className="font-display font-semibold text-lg tracking-tight">
                VidyaSetu
                <span className="text-accent ml-2 font-sans text-sm font-medium">
                  Admin Console
                </span>
              </span>
            </div>

            <nav aria-label="Admin sections" className="flex items-center gap-1 flex-wrap">
              {ADMIN_LINKS.map(({ to, label, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    `font-sans text-sm px-3 py-1.5 rounded-sm transition-colors ${
                      isActive
                        ? "bg-white/15 text-white font-medium"
                        : "text-white/70 hover:text-white hover:bg-white/10"
                    }`
                  }
                >
                  {label}
                </NavLink>
              ))}
            </nav>

            <div className="flex items-center gap-3">
              <RouterLink
                to="/"
                className="font-sans text-xs text-white/70 hover:text-white inline-flex items-center gap-1"
                title="Open the citizen site in this tab"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                View public site
              </RouterLink>

              <div className="relative" ref={menuRef}>
                <button
                  type="button"
                  className="flex items-center gap-2 text-sm text-white/90 hover:text-white"
                  aria-label="Account menu"
                  aria-expanded={menuOpen}
                  onClick={() => setMenuOpen((v) => !v)}
                >
                  <span className="flex items-center justify-center h-8 w-8 rounded-full bg-white/15">
                    <Users className="h-4 w-4" />
                  </span>
                  <span className="hidden sm:inline max-w-[160px] truncate">
                    {user?.email}
                  </span>
                </button>
                {menuOpen && (
                  <div className="absolute right-0 mt-2 w-52 bg-paper-raised border border-line rounded-sm shadow-md z-20 text-ink">
                    <div className="border-b border-line py-2 px-3">
                      <p className="text-xs text-ink-soft truncate" title={user?.email}>
                        {user?.email}
                      </p>
                      <p className="text-xs text-accent-ink mt-0.5">Administrator</p>
                    </div>
                    <button
                      type="button"
                      className="w-full text-left px-3 py-2 text-sm text-excl-ink hover:bg-excl-tint"
                      onClick={handleLogout}
                    >
                      <LogOut className="h-4 w-4 inline mr-2" /> Sign out
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </header>

        {/* Section nav + content */}
        <div className="flex-1 w-full max-w-[1200px] mx-auto px-5 sm:px-7 py-8 flex flex-col md:flex-row gap-8">
          <aside className="md:w-52 shrink-0">
            <p className="text-xs uppercase tracking-wide text-ink-soft mb-3">
              Manage
            </p>
            <nav
              aria-label="Admin detail sections"
              className="flex md:flex-col gap-1 flex-wrap"
            >
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

        <footer className="border-t border-line py-4">
          <div className="max-w-[1200px] mx-auto px-5 sm:px-7 text-xs text-ink-soft">
            VidyaSetu Administration · Welfare Intelligence Platform · Vishwakarma
            Institute of Technology, Pune
          </div>
        </footer>
      </div>
    </AdminGate>
  );
}
