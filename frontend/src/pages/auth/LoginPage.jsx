import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import Button from "../../components/ui/Button";
import Input from "../../components/ui/Input";
import PasswordInput from "../../components/ui/PasswordInput";
import { extractApiErrorMessage } from "../../utils/apiError";
import Card from "../../components/ui/Card";
import { ErrorState, LoadingState } from "../../components/ui/StatusStates";
import { authService } from "../../services/api";
import { saveToken, saveUser } from "../../services/auth";

export default function LoginPage() {
  const navigate = useNavigate();
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
      const { token, user_id, email: loggedInEmail } = response.data;
      saveToken(token);
      saveUser({ user_id, email: loggedInEmail });
      navigate("/");
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
        <h1 className="text-[30px] mb-3">Sign in</h1>
        <p className="max-w-[56ch]">
          Welcome back. Sign in with the email and password you used when you
          created your account.
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
              <Link to="/register" className="text-sm text-ink-soft hover:text-ink">
                Don’t have an account? Sign up
              </Link>
              <Button type="submit" disabled={loading || !email || !password}>
                {loading ? "Signing in..." : "Sign in"}
              </Button>
            </div>
          </form>
        </div>
      </Card>

      <p className="mt-8 text-center text-xs text-ink-soft">
        This is a demo welfare portal. Account data is stored only so you can
        sign in again and see your own profile.
      </p>
    </div>
  );
}
