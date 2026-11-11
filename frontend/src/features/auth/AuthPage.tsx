import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight,
  Calendar,
  Check,
  Eye,
  EyeOff,
  Leaf,
  Moon,
  ShieldCheck,
  Sun,
  Utensils,
} from "lucide-react";
import { Field, GlassButton, GlassPanel, SelectField } from "../../design/ui";
import { auth } from "../../lib/api";
import type { Gender, User } from "../../lib/types";
import { calculateExactAge, getTodayIso } from "../profile/bmi";

export function AuthPage({
  onSuccess,
  dark = false,
  onToggleTheme,
}: {
  onSuccess: (user: User) => void;
  dark?: boolean;
  onToggleTheme?: () => void;
}) {
  const [register, setRegister] = useState(false);
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [gender, setGender] = useState<Gender>("");
  const [dob, setDob] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [todayIso] = useState(getTodayIso);

  const exactAge = register ? calculateExactAge(dob) : null;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onSuccess(
        register
          ? await auth.register(
              email,
              password,
              username,
              name,
              Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
              gender,
              dob || null,
            )
          : await auth.login(email, password),
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Something went wrong.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-layout">
      {onToggleTheme && (
        <motion.button
          type="button"
          whileHover={{ scale: 1.08 }}
          whileTap={{ scale: 0.92 }}
          onClick={onToggleTheme}
          className="auth-theme-toggle"
          title={dark ? "Switch to light mode" : "Switch to dark mode"}
          aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
        >
          {dark ? <Sun size={18} /> : <Moon size={18} />}
        </motion.button>
      )}

      <div className="auth-panel">
        <div className="brand brand--auth">
          <div className="brand__logo-glass">
            <img
              src="/MealSense_Logo.svg"
              alt="MealSense"
              className="brand__mark"
            />
          </div>
          <span>
            Meal<span className="brand__light">Sense</span>
          </span>
        </div>

        <GlassPanel elevated className="auth-panel__body">
          {/* 5.2.E Segmented Tab Switcher with Shared Layout Indicator */}
          <div className="auth-segmented-switch" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={!register}
              className={`auth-segmented-btn ${!register ? "auth-segmented-btn--active" : ""}`}
              onClick={() => {
                setRegister(false);
                setError("");
              }}
            >
              {!register && (
                <motion.span
                  layoutId="auth-segmented-indicator"
                  className="auth-segmented-pill"
                  transition={{ type: "spring", stiffness: 450, damping: 30 }}
                />
              )}
              <span className="auth-segmented-label">Sign in</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={register}
              className={`auth-segmented-btn ${register ? "auth-segmented-btn--active" : ""}`}
              onClick={() => {
                setRegister(true);
                setError("");
              }}
            >
              {register && (
                <motion.span
                  layoutId="auth-segmented-indicator"
                  className="auth-segmented-pill"
                  transition={{ type: "spring", stiffness: 450, damping: 30 }}
                />
              )}
              <span className="auth-segmented-label">Create account</span>
            </button>
          </div>

          <span className="eyebrow">
            <Leaf size={14} /> YOUR MINDFUL NUTRITION COMPANION
          </span>
          <h1>
            {register
              ? "Start feeling good about food."
              : "Welcome back to MealSense."}
          </h1>
          <p>
            Log your meals with ease, understand your nutrition, and find your
            own balance—grounded in real, familiar foods.
          </p>

          <form onSubmit={submit} className="auth-form">
            <AnimatePresence mode="wait">
              {register && (
                <motion.div
                  key="register-fields"
                  initial={{ opacity: 0, height: 0, overflow: "hidden" }}
                  animate={{ opacity: 1, height: "auto", overflow: "visible" }}
                  exit={{ opacity: 0, height: 0, overflow: "hidden" }}
                  transition={{ duration: 0.25, ease: [0.25, 0.1, 0.25, 1.0] }}
                  className="auth-extra-fields"
                >
                  <Field
                    label="Your name"
                    placeholder="e.g. Alex"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    required
                  />
                  <div className="auth-form__row">
                    <SelectField
                      label="Gender"
                      value={gender}
                      onChange={(value) => setGender(value as Gender)}
                    >
                      <option value="">Select gender</option>
                      <option value="male">Male</option>
                      <option value="female">Female</option>
                      <option value="other">Other</option>
                    </SelectField>
                    <Field
                      label="Date of birth"
                      type="date"
                      max={todayIso}
                      value={dob}
                      onChange={(event) => setDob(event.target.value)}
                      required
                    />
                  </div>
                  {exactAge && (
                    <div className="auth-age-preview" aria-live="polite">
                      <Calendar size={14} />
                      <span>
                        Age: <strong>{exactAge.years}y</strong>{" "}
                        <strong>{exactAge.months}m</strong>{" "}
                        <strong>{exactAge.days}d</strong>
                      </span>
                    </div>
                  )}
                  <Field
                    label="Username"
                    placeholder="e.g. alex_foodie"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    minLength={3}
                    maxLength={30}
                    pattern="[a-zA-Z0-9._-]+"
                    required
                  />
                </motion.div>
              )}
            </AnimatePresence>

            <Field
              label={register ? "Email address" : "Username or email"}
              type={register ? "email" : "text"}
              placeholder={register ? "you@example.com" : "Username or email"}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
            <div className="password-field">
              <Field
                label="Password"
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                minLength={8}
                required
              />
              <button
                type="button"
                aria-label={showPassword ? "Hide password" : "Show password"}
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>

            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.18 }}
                  className="form-error"
                  role="alert"
                >
                  {error}
                </motion.div>
              )}
            </AnimatePresence>

            <GlassButton
              type="submit"
              disabled={busy}
              icon={<ArrowRight size={17} />}
              className="auth-form__submit"
            >
              {busy
                ? "Please wait..."
                : register
                  ? "Create account"
                  : "Sign in"}
            </GlassButton>
          </form>

          <p className="auth-switch">
            {register ? "Already have an account?" : "New to MealSense?"}{" "}
            <button
              type="button"
              onClick={() => {
                setRegister(!register);
                setError("");
              }}
            >
              {register ? "Sign in" : "Create an account"}
            </button>
          </p>
        </GlassPanel>

        <span className="auth-panel__foot">
          <ShieldCheck size={15} /> Your food diary stays completely private and
          offline-ready.
        </span>
      </div>

      <div className="auth-visual">
        <GlassPanel className="auth-visual__content">
          <div className="auth-visual__label">A FRESH PERSPECTIVE ON FOOD</div>
          <h2>
            Eat with awareness.
            <br />
            Live with energy.
          </h2>
          <p>
            Understand your meals without rigid restrictions or guilt. Built
            specifically for real home cooking and local flavors.
          </p>

          {/* Realistic, beautiful sample meal card */}
          <div className="auth-preview-card">
            <div className="auth-preview-card__header">
              <div className="auth-preview-card__icon">
                <Utensils size={18} />
              </div>
              <div className="auth-preview-card__title">
                <strong>Lunch Plate · Bhuna Khichuri & Egg</strong>
                <small>Home prepared · 320g</small>
              </div>
              <span className="auth-preview-card__cal">485 kcal</span>
            </div>
            <div className="auth-preview-card__macros">
              <div className="auth-preview-macro">
                <span>Protein</span>
                <div className="auth-preview-bar">
                  <div
                    className="auth-preview-bar__fill"
                    style={{ width: "65%", background: "var(--brand)" }}
                  />
                </div>
                <small>22 g</small>
              </div>
              <div className="auth-preview-macro">
                <span>Carbs</span>
                <div className="auth-preview-bar">
                  <div
                    className="auth-preview-bar__fill"
                    style={{ width: "75%", background: "var(--brand-accent)" }}
                  />
                </div>
                <small>64 g</small>
              </div>
              <div className="auth-preview-macro">
                <span>Fat</span>
                <div className="auth-preview-bar">
                  <div
                    className="auth-preview-bar__fill"
                    style={{ width: "40%", background: "var(--text-soft)" }}
                  />
                </div>
                <small>14 g</small>
              </div>
            </div>
          </div>

          <div className="auth-visual__perks">
            <span>
              <Check size={15} /> 100% Traceable Nutrition
            </span>
            <span>
              <Check size={15} /> Photo & Manual Logging
            </span>
            <span>
              <Check size={15} /> Curated Bangladesh Database
            </span>
          </div>
        </GlassPanel>
      </div>
    </div>
  );
}
