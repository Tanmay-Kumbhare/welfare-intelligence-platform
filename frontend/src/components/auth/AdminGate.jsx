import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import Button from "../ui/Button";
import { ErrorState, LoadingState } from "../ui/StatusStates";
import { authService } from "../../services/api";
import { getUser, saveUser } from "../../services/auth";

/**
 * UX gate for the /admin route subtree. The real security boundary is the
 * backend require_admin dependency (403 for citizens) — this gate just
 * renders a friendly "not authorized" state instead of letting admins-only
 * pages fail on their first API call.
 */
export default function AdminGate() {
  const [status, setStatus] = useState("loading"); // loading | admin | forbidden

  useEffect(() => {
    const cached = getUser();
    if (cached?.roles?.includes("ADMIN")) {
      setStatus("admin");
      return;
    }
    authService
      .me()
      .then((response) => {
        const data = response.data;
        saveUser({
          user_id: data.user_id,
          email: data.email,
          roles: data.roles || [],
        });
        setStatus(data.roles?.includes("ADMIN") ? "admin" : "forbidden");
      })
      .catch(() => setStatus("forbidden"));
  }, []);

  if (status === "loading") {
    return <LoadingState label="Checking your access..." />;
  }

  if (status === "forbidden") {
    return (
      <ErrorState
        title="Not authorized"
        message="This area is restricted to platform administrators. If you believe you should have access, ask an existing admin to grant your account the ADMIN role."
        action={<Button to="/" variant="secondary">Back to home</Button>}
      />
    );
  }

  return <Outlet />;
}
