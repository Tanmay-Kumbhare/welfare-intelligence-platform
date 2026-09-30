import { useEffect, useState, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import { LoadingState } from "../../components/ui/StatusStates";
import { authService } from "../../services/api";
import { saveToken, saveUser } from "../../services/auth";
import { extractApiErrorMessage } from "../../utils/apiError";

export default function OAuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [providerName, setProviderName] = useState("External");
  const processedRef = useRef(false);

  useEffect(() => {
    // Avoid double-execution in React 19 StrictMode
    if (processedRef.current) return;
    processedRef.current = true;

    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const oauthError = searchParams.get("error");
    const oauthErrorDesc = searchParams.get("error_description");

    if (oauthError) {
      if (oauthError === "access_denied") {
        setError("Sign-in was cancelled or access was not granted.");
      } else {
        setError(oauthErrorDesc || `Authentication failed: ${oauthError}`);
      }
      return;
    }

    if (!code || !state) {
      setError("Missing authorization code or state parameter from provider.");
      return;
    }

    // Identify provider: prefer sessionStorage, fallback to inspecting state payload
    let provider = sessionStorage.getItem("oauth_provider");
    let redirectPath = sessionStorage.getItem("oauth_redirect_path") || "/";
    const codeVerifier = sessionStorage.getItem("oauth_code_verifier");

    if (!provider && state && state.includes(".")) {
      try {
        const b64 = state.split(".")[0];
        const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
        const parsed = JSON.parse(atob(padded));
        if (parsed.provider) provider = parsed.provider;
        if (parsed.path) redirectPath = parsed.path;
      } catch {
        // ignore decode failure
      }
    }

    const normalizedProvider = (provider || "GOOGLE").toUpperCase();
    setProviderName(normalizedProvider === "DIGILOCKER" ? "DigiLocker" : "Google");

    const exchangeAuth = async () => {
      try {
        let response;
        if (normalizedProvider === "DIGILOCKER") {
          response = await authService.digilockerCallback({
            code,
            state,
            code_verifier: codeVerifier || undefined,
          });
        } else {
          response = await authService.googleCallback({
            code,
            state,
            code_verifier: codeVerifier || undefined,
          });
        }

        const { token, user_id, email } = response.data;
        saveToken(token);
        saveUser({ user_id, email });

        // Clean up OAuth session storage
        sessionStorage.removeItem("oauth_provider");
        sessionStorage.removeItem("oauth_state");
        sessionStorage.removeItem("oauth_code_verifier");
        sessionStorage.removeItem("oauth_redirect_path");

        navigate(redirectPath, { replace: true });
      } catch (err) {
        setError(
          extractApiErrorMessage(
            err,
            "Could not complete sign-in. Please try again or use email and password."
          )
        );
      }
    };

    exchangeAuth();
  }, [searchParams, navigate]);

  if (error) {
    return (
      <div className="max-w-[480px] mx-auto py-12">
        <Card className="text-center py-8">
          <div className="w-12 h-12 rounded-full bg-excl-tint text-excl-ink flex items-center justify-center mx-auto mb-4 text-xl font-bold">
            !
          </div>
          <h2 className="text-xl font-semibold mb-2">Authentication Failed</h2>
          <p className="text-sm text-ink-soft mb-6 px-4">{error}</p>
          <div className="flex justify-center gap-3">
            <Button to="/login" variant="primary">
              Return to Sign in
            </Button>
            <Button to="/" variant="secondary">
              Home
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-[480px] mx-auto py-16">
      <Card className="text-center py-10">
        <LoadingState label={`Verifying with ${providerName}…`} />
        <p className="text-xs text-ink-soft mt-4">
          Please wait while we complete your sign-in securely.
        </p>
      </Card>
    </div>
  );
}
