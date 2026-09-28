import { NavLink, useNavigate } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { User, LogOut, HelpCircle, ShieldCheck } from "lucide-react";
import { getUser, clearAuth } from "../../services/auth";
import { authService } from "../../services/api";

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

function UserMenu({ user, onLogout }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const handleLogout = async () => {
    setOpen(false);
    await onLogout();
    navigate("/login");
  };

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        className="flex items-center justify-center h-9 w-9 rounded-full bg-accent-tint text-accent-ink hover:bg-accent hover:text-white transition-colors"
        aria-label="Account menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <User className="h-4.5 w-4.5" />
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-52 bg-paper-raised border border-line rounded-sm shadow-md z-20">
          <div className="border-b border-line py-2 px-3">
            <p className="text-xs text-ink-soft truncate" title={user?.email}>
              {user?.email}
            </p>
          </div>
          <NavLink
            to="/profile"
            className="block px-3 py-2 text-sm text-ink hover:bg-accent-tint"
            onClick={() => setOpen(false)}
          >
            My profile
          </NavLink>
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
  );
}

export default function Header() {
  const user = getUser();
  const [loggingOut, setLoggingOut] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);
  const loginRef = useRef(null);

  // Close the login dropdown on outside click or Escape.
  useEffect(() => {
    if (!loginOpen) return;
    const onPointerDown = (event) => {
      if (loginRef.current && !loginRef.current.contains(event.target)) {
        setLoginOpen(false);
      }
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") setLoginOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [loginOpen]);

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await authService.logout().catch(() => {});
    } finally {
      clearAuth();
      setLoggingOut(false);
    }
  };

  const isAdmin = Boolean(getUser()?.roles?.includes("ADMIN"));

  return (
    <header className="bg-paper-raised border-b-[3px] border-accent">
      <div className="max-w-[1040px] mx-auto px-5 sm:px-7 py-4 flex items-center justify-between gap-6 flex-wrap">
        <NavLink to="/" className="font-display font-semibold text-[22px] tracking-tight text-ink">
          Vidya<span className="text-accent-ink">Setu</span>
        </NavLink>

        <div className="flex items-center gap-3 flex-wrap">
          <nav aria-label="Site pages" className="flex items-center gap-1 flex-wrap">
            {PRIMARY_LINKS.map((link) => (
              <NavLink key={link.to} to={link.to} end={link.end} className={navClasses}>
                {link.label}
              </NavLink>
            ))}
            {isAdmin && (
              <NavLink
                to="/admin"
                className={navClasses}
                title="Administration"
              >
                <ShieldCheck className="h-4 w-4 inline mr-1 -mt-0.5" />
                Admin
              </NavLink>
            )}
            <NavLink
              to="/help"
              className="flex items-center gap-1 font-sans text-sm px-3 py-2 text-ink-soft hover:text-ink"
            >
              <HelpCircle className="h-4 w-4" />
              Help
            </NavLink>
          </nav>

          {user && <UserMenu user={user} onLogout={handleLogout} />}

          {!user && (
            <div className="flex items-center gap-2">
              <div className="relative" ref={loginRef}>
                <button
                  type="button"
                  className="font-sans text-sm px-4 py-2 rounded-sm bg-accent text-white hover:bg-accent-ink transition-colors font-medium"
                  aria-expanded={loginOpen}
                  aria-haspopup="menu"
                  onClick={() => setLoginOpen((v) => !v)}
                >
                  Login ▾
                </button>
                {loginOpen && (
                  <div
                    role="menu"
                    className="absolute right-0 mt-2 w-56 bg-paper-raised border border-line rounded-sm shadow-md z-20"
                  >
                    <NavLink
                      to="/login"
                      role="menuitem"
                      className="block px-4 py-3 text-sm text-ink hover:bg-accent-tint"
                      onClick={() => setLoginOpen(false)}
                    >
                      Citizen Login
                      <span className="block text-xs text-ink-soft mt-0.5">
                        Check schemes &amp; manage your profile
                      </span>
                    </NavLink>
                    <NavLink
                      to="/login?mode=admin"
                      role="menuitem"
                      className="block px-4 py-3 text-sm text-ink hover:bg-accent-tint border-t border-line"
                      onClick={() => setLoginOpen(false)}
                    >
                      <ShieldCheck className="h-4 w-4 inline mr-1.5 -mt-0.5" />
                      Admin Login
                      <span className="block text-xs text-ink-soft mt-0.5">
                        Platform administration dashboard
                      </span>
                    </NavLink>
                  </div>
                )}
              </div>
              <NavLink
                to="/register"
                className="font-sans text-sm px-4 py-2 rounded-sm border border-accent text-accent-ink hover:bg-accent-tint transition-colors font-medium"
              >
                Register
              </NavLink>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
