import { useRef, useState } from "react";
import {
  Activity,
  Calendar,
  Check,
  Sparkles,
  Target,
  UserRound,
} from "lucide-react";
import {
  Badge,
  Field,
  GlassButton,
  GlassCard,
  SelectField,
} from "../../design/ui";
import { auth } from "../../lib/api";
import type { Gender, User } from "../../lib/types";
import {
  calculateExactAge,
  computeBmiAndSuggestions,
  getTodayIso,
} from "./bmi";

export function ProfilePage({
  user,
  onUpdate,
}: {
  user: User;
  onUpdate: (user: User) => void;
}) {
  const [name, setName] = useState(user.display_name);
  const [gender, setGender] = useState<Gender>(user.profile.gender || "");
  const [dob, setDob] = useState(user.profile.date_of_birth || "");
  const [timezone, setTimezone] = useState(user.profile.timezone);
  const [heightCm, setHeightCm] = useState(
    user.profile.height_cm !== null && user.profile.height_cm !== undefined
      ? String(user.profile.height_cm)
      : "170",
  );
  const [weightKg, setWeightKg] = useState(
    user.profile.weight_kg !== null && user.profile.weight_kg !== undefined
      ? String(user.profile.weight_kg)
      : "65",
  );
  const [goal, setGoal] = useState(user.profile.daily_kcal_goal);
  const [protein, setProtein] = useState(user.profile.protein_goal_g);
  const [carbs, setCarbs] = useState(user.profile.carbs_goal_g);
  const [fat, setFat] = useState(user.profile.fat_goal_g);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [pictureUploading, setPictureUploading] = useState(false);
  const pictureInput = useRef<HTMLInputElement>(null);
  const [todayIso] = useState(getTodayIso);

  const exactAge = calculateExactAge(dob);
  const suggestion = computeBmiAndSuggestions(
    Number(heightCm),
    Number(weightKg),
    gender,
    exactAge ? exactAge.years : null,
  );

  function applySuggestions() {
    if (!suggestion) return;
    setGoal(suggestion.kcal);
    setProtein(suggestion.protein_g);
    setCarbs(suggestion.carbs_g);
    setFat(suggestion.fat_g);
    setMessage("Applied BMI-based suggestions below. Click Save to keep them.");
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    try {
      const parsedHeight = heightCm.trim() ? Number(heightCm) : null;
      const parsedWeight = weightKg.trim() ? Number(weightKg) : null;
      onUpdate(
        await auth.update({
          display_name: name,
          profile: {
            ...user.profile,
            timezone,
            gender,
            date_of_birth: dob || null,
            height_cm:
              parsedHeight !== null && Number.isFinite(parsedHeight)
                ? parsedHeight
                : null,
            weight_kg:
              parsedWeight !== null && Number.isFinite(parsedWeight)
                ? parsedWeight
                : null,
            daily_kcal_goal: goal,
            protein_goal_g: protein,
            carbs_goal_g: carbs,
            fat_goal_g: fat,
          },
        }),
      );
      setMessage("Profile & goals saved.");
    } catch (cause) {
      setMessage(
        cause instanceof Error ? cause.message : "Could not save profile.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function uploadPicture(event: React.ChangeEvent<HTMLInputElement>) {
    const picture = event.target.files?.[0];
    event.target.value = "";
    if (!picture) return;
    if (picture.size > 5 * 1024 * 1024) {
      setMessage("Profile picture must be 5 MB or smaller.");
      return;
    }
    setPictureUploading(true);
    setMessage("");
    try {
      onUpdate(await auth.uploadPicture(picture));
      setMessage("Profile picture updated.");
    } catch (cause) {
      setMessage(
        cause instanceof Error
          ? cause.message
          : "Could not upload profile picture.",
      );
    } finally {
      setPictureUploading(false);
    }
  }

  const bmiMarkerPercent = suggestion
    ? Math.min(100, Math.max(0, ((suggestion.bmi - 14) / (36 - 14)) * 100))
    : 0;

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">PERSONAL WELLNESS</span>
          <h1>Profile & goals</h1>
          <p>
            Manage your personal details, calculate your BMI, and tune your
            daily nutrition targets.
          </p>
        </div>
      </div>

      <div className="profile-grid">
        <GlassCard className="settings-card">
          <div className="settings-card__head">
            <span>
              <UserRound size={19} />
            </span>
            <div>
              <h2>Personal profile & targets</h2>
              <p>Your preferences, body metrics, and daily pace.</p>
            </div>
          </div>

          <form onSubmit={save}>
            <div className="settings-card__fields">
              <div className="profile-picture-field">
                <div className="avatar avatar--profile">
                  {user.profile.profile_picture_url ? (
                    <img
                      src={user.profile.profile_picture_url}
                      alt=""
                      className="avatar__image"
                    />
                  ) : (
                    (user.display_name || user.email)[0].toUpperCase()
                  )}
                </div>
                <div>
                  <strong>Profile picture</strong>
                  <p className="settings-card__disclaimer">
                    JPG, PNG, or WebP up to 5 MB.
                  </p>
                  <input
                    ref={pictureInput}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={uploadPicture}
                    hidden
                  />
                  <GlassButton
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={pictureUploading}
                    onClick={() => pictureInput.current?.click()}
                  >
                    {pictureUploading ? "Uploading..." : "Choose picture"}
                  </GlassButton>
                </div>
              </div>
            </div>

            <div className="settings-card__fields">
              <Field
                label="Display name"
                value={name}
                placeholder="Your name"
                onChange={(event) => setName(event.target.value)}
              />
              <Field label="Email address" value={user.email} disabled />
            </div>

            <div className="settings-card__fields">
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
              />
            </div>

            <div className="age-box" aria-live="polite">
              <div className="age-box__head">
                <Calendar size={15} />
                <span>Exact age from date of birth</span>
              </div>
              {exactAge ? (
                <div className="age-box__pills">
                  <div className="age-pill">
                    <strong>{exactAge.years}</strong>
                    <small>{exactAge.years === 1 ? "Year" : "Years"}</small>
                  </div>
                  <div className="age-pill">
                    <strong>{exactAge.months}</strong>
                    <small>{exactAge.months === 1 ? "Month" : "Months"}</small>
                  </div>
                  <div className="age-pill">
                    <strong>{exactAge.days}</strong>
                    <small>{exactAge.days === 1 ? "Day" : "Days"}</small>
                  </div>
                </div>
              ) : (
                <p className="age-box__empty">
                  Enter your date of birth above to calculate your exact age in
                  years, months, and days.
                </p>
              )}
            </div>

            <Field
              label="Timezone"
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
              hint="Use an IANA timezone, such as Asia/Dhaka."
            />

            <div className="settings-card__divider" />
            <div className="profile-targets-head">
              <div>
                <h3>
                  <Target size={16} /> Daily targets
                </h3>
                <p className="settings-card__disclaimer">
                  Customize manually or apply the BMI-based suggestions on the
                  right.
                </p>
              </div>
            </div>

            <div className="settings-card__fields">
              <Field
                label="Calories (kcal)"
                type="number"
                min="0"
                value={goal}
                onChange={(event) => setGoal(Number(event.target.value))}
              />
              <Field
                label="Protein (g)"
                type="number"
                min="0"
                value={protein}
                onChange={(event) => setProtein(Number(event.target.value))}
              />
              <Field
                label="Carbs (g)"
                type="number"
                min="0"
                value={carbs}
                onChange={(event) => setCarbs(Number(event.target.value))}
              />
              <Field
                label="Fats (g)"
                type="number"
                min="0"
                value={fat}
                onChange={(event) => setFat(Number(event.target.value))}
              />
            </div>

            <p className="settings-card__disclaimer">
              Goals are personal tracking targets, not dietary prescriptions.
            </p>
            {message && (
              <p className="settings-message" role="status">
                {message}
              </p>
            )}
            <GlassButton
              type="submit"
              disabled={saving}
              icon={<Check size={16} />}
            >
              {saving ? "Saving..." : "Save profile & goals"}
            </GlassButton>
          </form>
        </GlassCard>

        <div className="settings-side">
          <GlassCard className="settings-card">
            <div className="settings-card__head">
              <span>
                <Activity size={19} />
              </span>
              <div>
                <h2>BMI calculator</h2>
                <p>Enter height and weight to check your Body Mass Index.</p>
              </div>
            </div>

            <div className="settings-card__fields">
              <Field
                label="Height (cm)"
                type="number"
                min="50"
                max="260"
                step="0.1"
                placeholder="e.g. 170"
                value={heightCm}
                onChange={(event) => setHeightCm(event.target.value)}
              />
              <Field
                label="Weight (kg)"
                type="number"
                min="20"
                max="350"
                step="0.1"
                placeholder="e.g. 65"
                value={weightKg}
                onChange={(event) => setWeightKg(event.target.value)}
              />
            </div>

            {suggestion ? (
              <div className="bmi-result">
                <div className="bmi-result__top">
                  <div>
                    <span className="bmi-result__label">YOUR BMI</span>
                    <strong className="bmi-result__score">
                      {suggestion.bmi.toFixed(1)} <small>kg/m²</small>
                    </strong>
                  </div>
                  <Badge tone={suggestion.tone}>{suggestion.category}</Badge>
                </div>

                <div className="bmi-scale" aria-hidden="true">
                  <div className="bmi-scale__bar">
                    <span
                      className="bmi-scale__marker"
                      style={{ left: `${bmiMarkerPercent}%` }}
                    />
                  </div>
                  <div className="bmi-scale__legend">
                    <span>&lt;18.5 Under</span>
                    <span>18.5–24.9 Normal</span>
                    <span>25–29.9 Over</span>
                    <span>30+ Obese</span>
                  </div>
                </div>

                <p className="bmi-result__range">
                  Healthy weight range for {heightCm} cm:{" "}
                  <strong>
                    {suggestion.healthyMinKg} – {suggestion.healthyMaxKg} kg
                  </strong>
                </p>
              </div>
            ) : (
              <p className="settings-card__disclaimer">
                Enter valid height (50–260 cm) and weight (20–350 kg) to
                calculate BMI.
              </p>
            )}
          </GlassCard>

          <GlassCard className="settings-card suggestion-card">
            <div className="settings-card__head">
              <span>
                <Sparkles size={19} />
              </span>
              <div>
                <h2>Suggested daily nutrition</h2>
                <p>Recommended intake on the basis of your BMI & profile.</p>
              </div>
            </div>

            {suggestion ? (
              <div className="suggestion-box">
                <p className="suggestion-box__focus">{suggestion.focus}</p>
                <div className="suggestion-grid">
                  <div className="suggestion-item">
                    <span>Calories</span>
                    <strong>
                      {suggestion.kcal} <small>kcal</small>
                    </strong>
                  </div>
                  <div className="suggestion-item">
                    <span>Protein</span>
                    <strong>
                      {suggestion.protein_g} <small>g</small>
                    </strong>
                  </div>
                  <div className="suggestion-item">
                    <span>Carbs</span>
                    <strong>
                      {suggestion.carbs_g} <small>g</small>
                    </strong>
                  </div>
                  <div className="suggestion-item">
                    <span>Fats</span>
                    <strong>
                      {suggestion.fat_g} <small>g</small>
                    </strong>
                  </div>
                </div>
                <p className="suggestion-box__note">
                  Calculated using your BMI ({suggestion.bmi.toFixed(1)}),
                  weight ({weightKg} kg), height ({heightCm} cm)
                  {exactAge ? `, age (${exactAge.years}y)` : ""}
                  {gender ? `, and gender (${gender})` : ""}. General estimate
                  only — not medical advice.
                </p>
                <GlassButton
                  type="button"
                  variant="secondary"
                  size="sm"
                  icon={<Sparkles size={15} />}
                  onClick={applySuggestions}
                >
                  Apply suggested targets
                </GlassButton>
              </div>
            ) : (
              <p className="settings-card__disclaimer">
                Provide your height and weight in the BMI calculator above to
                see personalized calorie, protein, carb, and fat suggestions.
              </p>
            )}
          </GlassCard>
        </div>
      </div>
    </>
  );
}
