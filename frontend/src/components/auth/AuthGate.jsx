import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { authService } from "../../services/api";
import { getUser, saveUser } from "../../services/auth";

export default function AuthGate({ children, allowPublic = false }) {
  const location = useLocation();
  const [status, setStatus] = useState("loading"); // loading | guest | user | error
  const [me, setMe] = useState(null);

  useEffect(() => {
    const existing = getUser();
    if (!existing) {
      setStatus("guest");
      return;
    }
    authService
      .me()
      .then((response) => {
        const data = response.data;
        setMe({ user_id: data.user_id, email: data.email });
        saveUser({ user_id: data.user_id, email: data.email });
        setStatus("user");
      })
      .catch(() => {
        // token is invalid or expired — clear stored auth and treat as guest
        saveUser(null);
        setStatus("guest");
      });
  }, []);

  if (status === "loading") {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-sm text-ink-soft">Loading account…</div>
      </div>
    );
  }

  if (status === "error") {
    return <Navigate to="/login" replace />;
  }

  if (!allowPublic && status === "guest") {
    // Save the page the user tried to reach so we can redirect back after login.
    const from = location.pathname + location.search;
    return <Navigate to={`/login?from=${encodeURIComponent(from)}`} replace />;
  }

  return children;
}
