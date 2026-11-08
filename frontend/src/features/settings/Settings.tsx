import {
  Check,
  Moon,
  Palette,
  ShieldAlert,
  ShieldCheck,
  Sun,
  Trash2,
} from "lucide-react";
import { Badge, GlassButton, GlassCard } from "../../design/ui";
import type { User } from "../../lib/types";

export function Settings({
  user,
  onDelete,
  dark,
  onToggleTheme,
}: {
  user: User;
  onDelete: () => void;
  dark: boolean;
  onToggleTheme: () => void;
}) {
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">PREFERENCES & PRIVACY</span>
          <h1>Settings</h1>
          <p>Customize your visual theme and manage your account privacy.</p>
        </div>
      </div>

      <div className="settings-clean-grid">
        <GlassCard className="settings-card">
          <div className="settings-card__head">
            <span>
              <Palette size={19} />
            </span>
            <div>
              <h2>Appearance</h2>
              <p>Choose the Liquid Glass theme that feels most comfortable.</p>
            </div>
          </div>

          <div className="theme-selector" role="radiogroup" aria-label="Theme">
            <button
              type="button"
              role="radio"
              aria-checked={!dark}
              className={`theme-option ${!dark ? "theme-option--active" : ""}`}
              onClick={() => {
                if (dark) onToggleTheme();
              }}
            >
              <div className="theme-option__icon">
                <Sun size={19} />
              </div>
              <div className="theme-option__body">
                <strong>Light Liquid Glass</strong>
                <small>
                  Soft atmospheric mint & translucent white surfaces
                </small>
              </div>
              {!dark && (
                <Badge tone="green">
                  <Check size={12} /> Active
                </Badge>
              )}
            </button>

            <button
              type="button"
              role="radio"
              aria-checked={dark}
              className={`theme-option ${dark ? "theme-option--active" : ""}`}
              onClick={() => {
                if (!dark) onToggleTheme();
              }}
            >
              <div className="theme-option__icon">
                <Moon size={19} />
              </div>
              <div className="theme-option__body">
                <strong>Dark Liquid Glass</strong>
                <small>
                  Deep forest charcoal & luminous emerald glass surfaces
                </small>
              </div>
              {dark && (
                <Badge tone="green">
                  <Check size={12} /> Active
                </Badge>
              )}
            </button>
          </div>
        </GlassCard>

        <GlassCard className="settings-card">
          <div className="settings-card__head">
            <span>
              <ShieldCheck size={19} />
            </span>
            <div>
              <h2>Delete account & privacy</h2>
              <p>Your food diary and photos belong strictly to you.</p>
            </div>
          </div>

          <div className="privacy-summary">
            <p>
              Signed in as <strong>{user.email}</strong>. Meal photos and
              nutrition records are stored privately and never shared publicly.
            </p>
          </div>

          <div className="danger-zone">
            <div className="danger-zone__head">
              <ShieldAlert size={18} />
              <div>
                <strong>Permanent account deletion</strong>
                <p>
                  Deleting your account permanently removes your profile, logged
                  meals, and uploaded meal photos. This action cannot be undone.
                </p>
              </div>
            </div>
            <GlassButton
              type="button"
              variant="danger"
              size="sm"
              icon={<Trash2 size={15} />}
              onClick={onDelete}
            >
              Delete my account
            </GlassButton>
          </div>
        </GlassCard>
      </div>
    </>
  );
}
