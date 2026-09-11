export default function SectionHeader({ title, count, action, className = "" }) {
  return (
    <div
      className={`flex items-baseline justify-between gap-3 flex-wrap border-b border-line pb-2.5 mb-4.5 ${className}`}
    >
      <h2 className="text-2xl mb-0">
        {title}
        {count !== undefined && (
          <span className="ml-2 font-sans text-sm font-normal text-ink-soft">({count})</span>
        )}
      </h2>
      {action}
    </div>
  );
}
