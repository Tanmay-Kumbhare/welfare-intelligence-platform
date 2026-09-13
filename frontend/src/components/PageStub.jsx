export default function PageStub({ title, description, note }) {
  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      minHeight: "60vh",
      textAlign: "center",
      padding: "2rem",
      gap: "1rem",
      color: "#6b7280",
    }}>
      <div style={{ fontSize: "3rem" }}>🚧</div>
      <h1 style={{ fontSize: "1.75rem", fontWeight: 700, color: "#111827", margin: 0 }}>
        {title}
      </h1>
      {description && (
        <p style={{ maxWidth: "520px", fontSize: "1rem", lineHeight: 1.6, margin: 0 }}>
          {description}
        </p>
      )}
      {note && (
        <p style={{
          fontSize: "0.85rem",
          background: "#f3f4f6",
          borderRadius: "6px",
          padding: "0.5rem 1rem",
          color: "#9ca3af",
          margin: 0,
        }}>
          {note}
        </p>
      )}
    </div>
  );
}
