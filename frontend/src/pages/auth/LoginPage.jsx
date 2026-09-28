import { useState } from "react";
import { useNavigate, Link, useLocation } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import Button from "../../components/ui/Button";
import Input from "../../components/ui/Input";
import PasswordInput from "../../components/ui/PasswordInput";
import { extractApiErrorMessage } from "../../utils/apiError";
import Card from "../../components/ui/Card";
import { ErrorState, LoadingState } from "../../components/ui/StatusStates";
import { authService } from "../../services/api";
import { saveToken, saveUser, clearAuth } from "../../services/auth";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  // /login?mode=admin is reached from the header's "Admin Login" entry.
  const adminMode = new URLSearchParams(location.search).get("mode") === "admin";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const response = await authService.login({ email, password });
      const { token, user_id, email: loggedInEmail, roles } = response.data;
      const effectiveRoles = roles || [];

      // Administrator sign-in is a UX hint only — the backend still decides.
      // A non-admin account that uses this form is signed out again with a
      // clear message rather than being silently dropped into the citizen area.
      if (adminMode && !effectiveRoles.includes("ADMIN")) {
        clearAuth();
        setError(
          "This account does not have administrator privileges. Use Citizen Login instead."
        );
        return;
      }

      saveToken(token);
      saveUser({ user_id, email: loggedInEmail, roles: effectiveRoles });
      // Admins land on their dashboard; citizens go home (or back to the
      // page that bounced them to login).
      const params = new URLSearchParams(location.search);
      const from = params.get("from");
      if (!from && effectiveRoles.includes("ADMIN")) {
        navigate("/admin");
      } else {
        navigate(from || "/");
      }
      return;
    } catch (requestError) {
      setError(
        extractApiErrorMessage(
          requestError,
          "We could not sign you in. Please check your email and password."
        )
      );
      return;
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="mb-9 border-b border-line pb-7">
        <h1 className="text-[30px] mb-3 flex items-center gap-2">
          {adminMode && <ShieldCheck className="h-6 w-6 text-accent-ink" />}
          {adminMode ? "Administrator sign in" : "Sign in"}
        </h1>
        <p className="max-w-[56ch]">
          {adminMode
            ? "Restricted area for platform administrators. Regular users should use Citizen Login."
            : "Welcome back. Sign in with the email and password you used when you created your account."}
        </p>
      </div>

      <Card>
        <div className="max-w-[420px] mx-auto">
          <form onSubmit={submit} noValidate className="space-y-6">
            <Input
              id="login-email"
              label="Email address"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
            />

            <PasswordInput
              id="login-password"
              label="Password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />

            {error && (
              <div className="text-[13px] text-excl-ink bg-excl-tint border border-excl-tint rounded-sm px-3 py-2">
                {error}
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2">
              {adminMode ? (
                <Link to="/login" className="text-sm text-ink-soft hover:text-ink">
                  Citizen Login
                </Link>
              ) : (
                <Link to="/register" className="text-sm text-ink-soft hover:text-ink">
                  Don’t have an account? Sign up
                </Link>
              )}
              <Button type="submit" disabled={loading || !email || !password}>
                {loading
                  ? "Signing in..."
                  : adminMode
                    ? "Sign in as administrator"
                    : "Sign in"}
              </Button>
            </div>
          </form>
        </div>
      </Card>

      <p className="mt-8 text-center text-xs text-ink-soft">
        {adminMode
          ? "Administrator accounts are provisioned by an existing admin via the Users dashboard — there is no admin self-registration."
          : "This is a demo welfare portal. Account data is stored only so you can sign in again and see your own profile."}
      </p>
    </div>
  );
}
