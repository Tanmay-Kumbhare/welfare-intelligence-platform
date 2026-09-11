import Card from "../components/ui/Card";

export default function HelpPage() {
  return (
    <div>
      <h1 className="text-[30px] mb-4">Help &amp; About</h1>
      <p className="max-w-[62ch]">
        VidyaSetu helps citizens discover government welfare schemes and check
        their eligibility using structured, deterministic scheme rules stored
        in a real database — not estimates or AI-generated guesses.
      </p>
      <div className="grid gap-4 mt-6">
        <Card>
          <h3 className="mb-2">How eligibility is decided</h3>
          <p className="mb-0 text-sm">
            Every scheme has eligibility rules written by hand from official
            sources. When you check your eligibility, your profile is
            compared against those exact rules — the same result, every
            time, for the same profile.
          </p>
        </Card>
        <Card>
          <h3 className="mb-2">Is my data stored?</h3>
          <p className="mb-0 text-sm">
            Your profile is stored so you can revisit your results and
            re-check eligibility later. There is no account/login system yet
            — your browser remembers which profile is yours.
          </p>
        </Card>
        <Card>
          <h3 className="mb-2">What VidyaSetu doesn't do yet</h3>
          <p className="mb-0 text-sm">
            This version does not diagnose stuck or rejected applications
            after submission — it only evaluates eligibility before you
            apply. That deeper diagnosis is planned for a future version.
          </p>
        </Card>
      </div>
    </div>
  );
}
