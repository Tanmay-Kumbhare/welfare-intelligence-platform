// Matches the mockup's .card: white "raised paper" surface, thin border,
// no drop shadow — the flat, document-like feel called for in Part 14.
export default function Card({ className = "", eligible, children, as: Tag = "div", ...props }) {
  const borderAccent = eligible ? "border-l-4 border-l-ok" : "";
  return (
    <Tag
      className={`bg-paper-raised border border-line p-[22px] ${borderAccent} ${className}`}
      {...props}
    >
      {children}
    </Tag>
  );
}
