// Two shapes from the mockup:
//  - status badge: mono font, sharp corners (.badge / .badge-ok / .badge-excl)
//  - chip: sans font, fully rounded (.chip) -- used for document/category tags
const STATUS_VARIANTS = {
  ok: "bg-ok-tint text-ok-ink",
  excl: "bg-excl-tint text-excl-ink",
  neutral: "bg-accent-tint text-accent-ink",
};

export default function Badge({ variant = "neutral", pill = false, className = "", children }) {
  if (pill) {
    return (
      <span
        className={`inline-flex items-center rounded-full border border-line bg-paper px-2.5 py-1 text-xs text-ink-soft font-sans ${className}`}
      >
        {children}
      </span>
    );
  }
  return (
    <span
      className={`inline-flex items-center rounded-sm px-2 py-1 text-xs font-mono whitespace-nowrap ${STATUS_VARIANTS[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
