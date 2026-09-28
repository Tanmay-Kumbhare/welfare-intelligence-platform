import { useEffect, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import { LoadingState, ErrorState } from "../../components/ui/StatusStates";
import { authService, citizenService } from "../../services/api";
import { getUser } from "../../services/auth";

export default function ProfileCompletionGate() {
  const navigate = useNavigate();
  const [status, setStatus] = useState("loading"); // loading | guest | error | needs-profile | ready

  useEffect(() => {
    const user = getUser();
    if (!user?.user_id) {
      setStatus("guest");
      return;
    }
    authService
      .me()
      .then((response) => {
        const data = response.data;
        if (!data.citizen_id) {
          setStatus("needs-profile");
          return;
        }
        return citizenService
          .get(data.citizen_id)
          .then(() => setStatus("ready"))
          .catch(() => setStatus("error"));
      })
      .catch(() => setStatus("guest"));
  }, []);

  if (status === "loading") {
    return <LoadingState />;
  }

  if (status === "guest") {
    // Not signed in — AuthLayout's AuthGate normally redirects first, but if
    // we end up here anyway, just render the nested routes.
    return <Outlet />;
  }

  if (status === "error") {
    return (
      <ErrorState
        title="Could not load your profile"
        message="Your account exists, but we could not load your profile right now."
        action={<Button onClick={() => navigate("/profile")}>Go to profile</Button>}
      />
    );
  }

  if (status === "needs-profile") {
    return (
      <div>
        <div className="mb-8 border-b border-line pb-7">
          <h1 className="text-[30px] mb-3">Complete your profile</h1>
          <p className="max-w-[60ch]">
            You have an account, but your profile is not ready yet. Please fill
            in your details so we can check your eligibility and save your
            results.
          </p>
        </div>
        <Card>
          <div className="max-w-[520px] mx-auto text-sm text-ink-soft">
            <p className="mb-4">
              Your profile lets you check welfare schemes, save your answers,
              and return later. You can still browse public schemes, but
              eligibility checks require a completed profile.
            </p>
            <Button to="/profile" variant="primary" size="lg">
              Fill in my profile
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  return <Outlet />;
}
