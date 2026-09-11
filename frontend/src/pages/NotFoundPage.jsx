import Button from "../components/ui/Button";

export default function NotFoundPage() {
  return (
    <div className="text-center py-20">
      <h1 className="text-[30px] mb-3">Page not found</h1>
      <p className="mb-6">The page you're looking for doesn't exist.</p>
      <Button to="/" variant="primary">
        Back to Home
      </Button>
    </div>
  );
}
