import { useState, useEffect } from "react";
import { useNavigate, Link, useLocation, useSearchParams } from "react-router-dom";
import { ShieldCheck } from "lucide-react";

import Button from "../../components/ui/Button";
import Input from "../../components/ui/Input";
import PasswordInput from "../../components/ui/PasswordInput";
import Card from "../../components/ui/Card";
import { extractApiErrorMessage } from "../../utils/apiError";
import { authService } from "../../services/api";
import { saveToken, saveUser, getUser, clearAuth } from "../../services/auth";

import { GoogleIcon, DigiLockerIcon } from "../../components/auth/AuthIcons";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  // /login?mode=admin is reached from the header's "Admin Login" entry.
  const adminMode = new URLSearchParams(location.search).get("mode") === "admin";
  const returnTo = searchParams.get("from") || "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [infoMessage, setInfoMessage] = useState("");
  const [loadingEmail, setLoadingEmail] = useState(false);
  const [loadingGoogle, setLoadingGoogle] = useState(false);
  const [loadingDigiLocker, setLoadingDigiLocker] = useState(false);

  // If already logged in, redirect to home or returnTo
  useEffect(() => {
    const existing = getUser();
    if (existing?.user_id) {
      navigate(returnTo, { replace: true });
    }
  }, [navigate, returnTo]);

  // Handle URL errors (e.g. from cancelled OAuth)
  useEffect(() => {
    const err = searchParams.get("error");
    if (err) {
      if (err === "access_denied") {
        setError("Sign in was cancelled.");
      } else {
        setError(searchParams.get("error_description") || "Authentication could not be completed.");
      }
    }
  }, [searchParams]);

  const anyLoading = loadingEmail || loadingGoogle || loadingDigiLocker;

  // 1. Email & Password Sign In
  const handleEmailSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setInfoMessage("");
    setLoadingEmail(true);

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

      const params = new URLSearchParams(location.search);
      const from = params.get("from");

      if (!from && effectiveRoles.includes("ADMIN")) {
        navigate("/admin");
      } else {
        navigate(from || returnTo || "/");
      }

      return;
    } catch (requestError) {
      setError(
        extractApiErrorMessage(
          requestError,
          "We could not sign you in. Please check your email and password."
        )
      );
    } finally {
      setLoadingEmail(false);
    }
  };

  // 2. Continue with Google
  const handleGoogleLogin = async () => {
    setError("");
    setInfoMessage("");
    setLoadingGoogle(true);

    try {
      sessionStorage.setItem("oauth_provider", "GOOGLE");
      sessionStorage.setItem("oauth_redirect_path", returnTo);

      const response = await authService.getGoogleAuthUrl(returnTo);
      const { url, state, code_verifier } = response.data;

      sessionStorage.setItem("oauth_state", state);
      if (code_verifier) {
        sessionStorage.setItem("oauth_code_verifier", code_verifier);
      }

      window.location.href = url;
    } catch (requestError) {
      setLoadingGoogle(false);
      setError(
        extractApiErrorMessage(
          requestError,
          "Google sign-in is not configured yet. Please use email and password."
        )
      );
    }
  };

  // 3. Continue with DigiLocker
  const handleDigiLockerLogin = async () => {
    setError("");
    setInfoMessage("");
    setLoadingDigiLocker(true);

    try {
      sessionStorage.setItem("oauth_provider", "DIGILOCKER");
      sessionStorage.setItem("oauth_redirect_path", returnTo);

      const response = await authService.getDigiLockerAuthUrl(returnTo);
      const { url, state, code_verifier } = response.data;

      sessionStorage.setItem("oauth_state", state);
      if (code_verifier) {
        sessionStorage.setItem("oauth_code_verifier", code_verifier);
      }

      window.location.href = url;
    } catch (requestError) {
      setLoadingDigiLocker(false);
      setError(
        extractApiErrorMessage(
          requestError,
          "DigiLocker sign-in is not configured yet. Please use email and password."
        )
      );
    }
  };

  const handleForgotPassword = (e) => {
    e.preventDefault();
    setInfoMessage(
      "Password reset is disabled in development mode. You can create a new account or sign in with another method."
    );
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

      <div className="max-w-[440px] mx-auto">
        <Card className="p-6 sm:p-8">
          {error && (
            <div
              className="text-[13px] text-excl-ink bg-excl-tint border border-excl-tint rounded-sm px-3.5 py-2.5 mb-5"
              role="alert"
            >
              {error}
            </div>
          )}

          {infoMessage && (
            <div
              className="text-[13px] text-accent-ink bg-accent-tint border border-accent-tint rounded-sm px-3.5 py-2.5 mb-5"
              role="status"
            >
              {infoMessage}
            </div>
          )}

          {/* Social / OAuth Options */}
          <div className="space-y-3">
            <button
              type="button"
              onClick={handleGoogleLogin}
              disabled={anyLoading}
              className="w-full flex items-center justify-center gap-3 py-2.5 px-4 border border-line rounded-sm bg-white hover:bg-paper text-sm font-medium text-ink transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              <GoogleIcon />
              <span>
                {loadingGoogle ? "Connecting to Google…" : "Continue with Google"}
              </span>
            </button>

            <button
              type="button"
              onClick={handleDigiLockerLogin}
              disabled={anyLoading}
              className="w-full flex items-center justify-center gap-3 py-2.5 px-4 border border-line rounded-sm bg-white hover:bg-paper text-sm font-medium text-ink transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              <DigiLockerIcon />
              <span>
                {loadingDigiLocker ? "Connecting to DigiLocker…" : "Continue with DigiLocker"}
              </span>
            </button>
          </div>

          {/* Divider */}
          <div className="relative my-6 flex items-center justify-center">
            <div className="border-t border-line w-full" />
            <span className="bg-paper-raised px-3 text-xs uppercase font-medium tracking-wider text-ink-soft absolute">
              OR
            </span>
          </div>

          {/* Email & Password Form */}
          <form onSubmit={handleEmailSubmit} noValidate className="space-y-5">
            <Input
              id="login-email"
              label="Email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              disabled={anyLoading}
            />

            <div>
              <PasswordInput
                id="login-password"
                label="Password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                disabled={anyLoading}
              />
              <div className="flex justify-end mt-1.5">
                <button
                  type="button"
                  onClick={handleForgotPassword}
                  className="text-xs text-ink-soft hover:text-ink transition-colors"
                >
                  Forgot password?
                </button>
              </div>
            </div>

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

              <Button type="submit" disabled={anyLoading || !email || !password}>
                {loadingEmail
                  ? "Signing in..."
                  : adminMode
                    ? "Sign in as administrator"
                    : "Sign in"}
              </Button>
            </div>
          </form>
        </Card>

        <p className="mt-8 text-center text-xs text-ink-soft">
          {adminMode
            ? "Administrator accounts are provisioned by an existing admin via the Users dashboard — there is no admin self-registration."
            : "This is a demo welfare portal. Account data is stored only so you can sign in again and see your own profile."}
        </p>
      </div>
    </div>
  );
}
