import { useState } from "react";
import {
  ArrowRight,
  Calendar,
  Check,
  Eye,
  EyeOff,
  Leaf,
  ShieldCheck,
} from "lucide-react";
import { Button, Field, SelectField } from "../../design/ui";
import { FoodArt } from "../../components/FoodArt";
import { auth } from "../../lib/api";
import type { Gender, User } from "../../lib/types";
import { calculateExactAge, getTodayIso } from "../profile/bmi";

export function AuthPage({ onSuccess }: { onSuccess: (user: User) => void }) {
  const [register, setRegister] = useState(false);
  const [name, setName] = useState("");
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
      <div className="auth-panel">
        <div className="brand brand--auth">
          <span className="brand__mark">✳</span>
          <span>
            Meal<span className="brand__light">Sense</span>
          </span>
        </div>
        <div className="auth-panel__body">
          <span className="eyebrow">
            <Leaf size={15} /> YOUR WELLNESS JOURNEY
          </span>
          <h1>
            {register
              ? "Start feeling good about food."
              : "Welcome back to a healthier you."}
          </h1>
          <p>
            Log your meals, understand your nutrition, and find your own
            balance. One day at a time.
          </p>
          <form onSubmit={submit} className="auth-form">
            {register && (
              <>
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
              </>
            )}
            <Field
              label="Email address"
              type="email"
              placeholder="you@example.com"
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
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {error && (
              <div className="form-error" role="alert">
                {error}
              </div>
            )}
            <Button
              type="submit"
              disabled={busy}
              icon={<ArrowRight size={18} />}
              className="auth-form__submit"
            >
              {busy
                ? "Please wait..."
                : register
                  ? "Create account"
                  : "Sign in"}
            </Button>
          </form>
          <p className="auth-switch">
            {register ? "Already have an account?" : "New to MealSense?"}{" "}
            <button
              onClick={() => {
                setRegister(!register);
                setError("");
              }}
            >
              {register ? "Sign in" : "Create an account"}
            </button>
          </p>
        </div>
        <span className="auth-panel__foot">
          <ShieldCheck size={16} /> Your food diary stays yours.
        </span>
      </div>
      <div className="auth-visual">
        <div className="auth-visual__halo" />
        <div className="auth-visual__content">
          <div className="auth-visual__label">A FRESH PERSPECTIVE ON FOOD</div>
          <FoodArt variant="plate" />
          <h2>
            Eat with awareness.
            <br />
            Live with energy.
          </h2>
          <p>
            Small insights make big differences. See your meals in a whole new
            light.
          </p>
          <div className="auth-visual__perks">
            <span>
              <Check size={16} /> Simple meal logging
            </span>
            <span>
              <Check size={16} /> Clear daily insights
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
