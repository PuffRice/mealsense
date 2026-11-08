import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "md" | "sm";
  icon?: ReactNode;
};

export function GlassButton({
  variant = "primary",
  size = "md",
  icon,
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={`button glass-button button--${variant} button--${size} ${className}`.trim()}
      {...props}
    >
      {icon}
      {children}
    </button>
  );
}

export const Button = GlassButton;

export type GlassSurfaceProps = HTMLAttributes<HTMLElement> & {
  elevated?: boolean;
  subtle?: boolean;
  interactive?: boolean;
  as?: "section" | "div" | "article";
};

export function GlassPanel({
  elevated = false,
  subtle = false,
  interactive = false,
  as: Tag = "div",
  className = "",
  children,
  ...props
}: GlassSurfaceProps) {
  const modifiers = [
    "glass-panel",
    elevated ? "glass-panel--elevated" : "",
    subtle ? "glass-panel--subtle" : "",
    interactive ? "glass-panel--interactive" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <Tag className={modifiers} {...props}>
      {children}
    </Tag>
  );
}

export function GlassCard({
  elevated = false,
  subtle = false,
  interactive = false,
  className = "",
  children,
  ...props
}: GlassSurfaceProps) {
  const modifiers = [
    "card",
    "glass-card",
    elevated ? "glass-card--elevated" : "",
    subtle ? "glass-card--subtle" : "",
    interactive ? "glass-card--interactive" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section className={modifiers} {...props}>
      {children}
    </section>
  );
}

export const Card = GlassCard;

export function GlassSidebar({
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLElement>) {
  return (
    <aside className={`sidebar glass-sidebar ${className}`.trim()} {...props}>
      {children}
    </aside>
  );
}

export function GlassNavbar({
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLElement>) {
  return (
    <header className={`topbar glass-navbar ${className}`.trim()} {...props}>
      {children}
    </header>
  );
}

export function GlassModal({
  titleId,
  onClose,
  className = "",
  children,
}: {
  titleId?: string;
  onClose: () => void;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className="modal-backdrop glass-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className={`modal glass-modal ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        {children}
      </div>
    </div>
  );
}

export function Badge({
  children,
  tone = "green",
}: {
  children: ReactNode;
  tone?: "green" | "peach" | "neutral";
}) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

export function GlassInput({
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`field__input glass-input ${className}`.trim()}
      {...props}
    />
  );
}

export function Field({
  label,
  hint,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      <GlassInput {...props} />
      {hint && <span className="field__hint">{hint}</span>}
    </label>
  );
}

export function GlassDropdown({
  className = "",
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="glass-select-wrap">
      <select
        className={`field__input glass-dropdown ${className}`.trim()}
        {...props}
      >
        {children}
      </select>
    </div>
  );
}

export function SelectField({
  label,
  children,
  value,
  onChange,
}: {
  label: string;
  children: ReactNode;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="field">
      <span className="field__label">{label}</span>
      <GlassDropdown
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {children}
      </GlassDropdown>
    </label>
  );
}

export function EmptyState({
  icon,
  title,
  text,
  action,
}: {
  icon: ReactNode;
  title: string;
  text: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-state__icon">{icon}</span>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}

export function Progress({
  value,
  max,
  color = "brand",
}: {
  value: number;
  max: number;
  color?: "brand" | "orange" | "lime";
}) {
  return (
    <div
      className="progress"
      role="progressbar"
      aria-valuenow={Math.min(value, max)}
      aria-valuemin={0}
      aria-valuemax={max}
    >
      <span
        className={`progress__fill progress__fill--${color}`}
        style={{
          width: `${Math.min(100, Math.max(0, (value / Math.max(max, 1)) * 100))}%`,
        }}
      />
    </div>
  );
}
