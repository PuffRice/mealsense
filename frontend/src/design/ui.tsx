import {
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  forwardRef,
  useEffect,
  useRef,
} from "react";
import { motion, type HTMLMotionProps } from "framer-motion";
import {
  buttonMotion,
  cardInteractiveMotion,
  modalMotionVariants,
  toastSlideVariants,
} from "./motion";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "md" | "sm";
  icon?: ReactNode;
};

export const GlassButton = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "primary",
      size = "md",
      icon,
      className = "",
      children,
      disabled,
      ...props
    },
    ref,
  ) => {
    return (
      <motion.button
        ref={ref}
        disabled={disabled}
        whileHover={disabled ? undefined : buttonMotion.whileHover}
        whileTap={disabled ? undefined : buttonMotion.whileTap}
        className={`button glass-button button--${variant} button--${size} ${className}`.trim()}
        {...(props as HTMLMotionProps<"button">)}
      >
        {icon}
        {children}
      </motion.button>
    );
  },
);
GlassButton.displayName = "GlassButton";

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

  if (interactive) {
    return (
      <motion.div
        whileHover={cardInteractiveMotion.whileHover}
        whileTap={cardInteractiveMotion.whileTap}
        className={modifiers}
        {...(props as HTMLMotionProps<"div">)}
      >
        {children}
      </motion.div>
    );
  }

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

  if (interactive) {
    return (
      <motion.section
        whileHover={cardInteractiveMotion.whileHover}
        whileTap={cardInteractiveMotion.whileTap}
        className={modifiers}
        {...(props as HTMLMotionProps<"section">)}
      >
        {children}
      </motion.section>
    );
  }

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
  const modalRef = useRef<HTMLDivElement | null>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const modalEl = modalRef.current;
    if (modalEl) {
      const focusable = modalEl.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length > 0) {
        focusable[0].focus();
      } else {
        modalEl.focus();
      }
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key === "Tab" && modalRef.current) {
        const focusable = Array.from(
          modalRef.current.querySelectorAll<HTMLElement>(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
          ),
        );
        if (focusable.length === 0) {
          event.preventDefault();
          return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey) {
          if (document.activeElement === first || !modalRef.current.contains(document.activeElement)) {
            event.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last || !modalRef.current.contains(document.activeElement)) {
            event.preventDefault();
            first.focus();
          }
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (previouslyFocused && typeof previouslyFocused.focus === "function") {
        previouslyFocused.focus();
      }
    };
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="modal-backdrop glass-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <motion.div
        ref={modalRef}
        tabIndex={-1}
        variants={modalMotionVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        className={`modal glass-modal ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {children}
      </motion.div>
    </motion.div>
  );
}

export function Badge({
  children,
  tone = "green",
}: {
  children: ReactNode;
  tone?: "green" | "peach" | "neutral" | "danger";
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

/**
 * 6. UI Component Transformation Checklist:
 * Alerts & Toast Notices:
 * Pin these as floating containers with elevated surface backgrounds.
 * Add a 3-pixel wide left-hand accent border using the respective status color (Error/Success),
 * and animate their entry via a slide-in trajectory from the top right quadrant.
 */
export function ToastNotice({
  type = "info",
  message,
  onDismiss,
}: {
  type?: "error" | "success" | "info";
  message: string;
  onDismiss?: () => void;
}) {
  return (
    <motion.aside
      role="status"
      variants={toastSlideVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      className={`floating-toast floating-toast--${type}`}
      onClick={onDismiss}
    >
      <div className="floating-toast__content">{message}</div>
    </motion.aside>
  );
}

/**
 * 5.2.E Toggle Switch
 * Thumb Toggles: The circular handle must compress slightly along the horizontal axis
 * during the drag or toggle action before settling into its final position.
 */
export function ToggleSwitch({
  checked,
  onChange,
  label,
  id,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  id?: string;
}) {
  return (
    <label htmlFor={id} className="toggle-switch-wrapper">
      {label && <span className="toggle-switch__label">{label}</span>}
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`toggle-track ${checked ? "toggle-track--active" : ""}`}
      >
        <motion.span
          className="toggle-thumb"
          layout
          transition={{ type: "spring", stiffness: 500, damping: 25 }}
          whileTap={{ scaleX: 1.25, scaleY: 0.85 }}
          animate={{ scale: 1 }}
        />
      </button>
    </label>
  );
}
