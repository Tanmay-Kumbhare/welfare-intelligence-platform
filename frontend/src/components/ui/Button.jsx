import { Link } from "react-router-dom";

// Visual language matches the mockup's .btn / .btn-primary / .btn-secondary
// exactly: 2px radius, no shadow, solid borders.
const VARIANTS = {
  primary: "bg-accent text-white border border-accent hover:bg-accent-ink hover:border-accent-ink",
  secondary: "bg-transparent text-ink border border-line hover:border-ink-soft",
  ghost: "bg-transparent text-ink-soft border border-transparent hover:text-ink",
  danger: "bg-transparent text-excl-ink border border-excl hover:bg-excl-tint",
};

const SIZES = {
  sm: "px-3.5 py-2 text-[13px]",
  md: "px-[22px] py-3 text-sm",
  lg: "px-7 py-3.5 text-base",
};

export default function Button({
  as,
  to,
  href,
  variant = "primary",
  size = "md",
  className = "",
  children,
  ...props
}) {
  const classes = `inline-flex items-center justify-center gap-2 rounded-sm font-medium font-sans transition-colors duration-150 focus-visible:outline-none disabled:opacity-50 disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`;

  if (to) {
    return (
      <Link to={to} className={classes} {...props}>
        {children}
      </Link>
    );
  }
  if (href) {
    return (
      <a href={href} className={classes} {...props}>
        {children}
      </a>
    );
  }
  const Tag = as || "button";
  return (
    <Tag className={classes} {...props}>
      {children}
    </Tag>
  );
}
