import { useState } from "react";
import { Check, Moon, ShieldCheck, Sun, Trash2, UserRound } from "lucide-react";
import { Button, Card, Field } from "../../design/ui";
import { auth } from "../../lib/api";
import type { User } from "../../lib/types";

export function Settings({
  user,
  onUpdate,
  onDelete,
  dark,
  onToggleTheme,
}: {
  user: User;
  onUpdate: (user: User) => void;
  onDelete: () => void;
  dark: boolean;
  onToggleTheme: () => void;
}) {
  const [name, setName] = useState(user.display_name);
  const [goal, setGoal] = useState(user.profile.daily_kcal_goal);
  const [protein, setProtein] = useState(user.profile.protein_goal_g);
  const [carbs, setCarbs] = useState(user.profile.carbs_goal_g);
  const [fat, setFat] = useState(user.profile.fat_goal_g);
  const [timezone, setTimezone] = useState(user.profile.timezone);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    try {
      onUpdate(
        await auth.update({
          display_name: name,
          profile: {
            ...user.profile,
            timezone,
            daily_kcal_goal: goal,
            protein_goal_g: protein,
            carbs_goal_g: carbs,
            fat_goal_g: fat,
          },
        }),
      );
      setMessage("Settings saved.");
    } catch (cause) {
      setMessage(
        cause instanceof Error ? cause.message : "Could not save settings.",
      );
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">MAKE IT YOURS</span>
          <h1>Settings</h1>
          <p>Set the goals that feel right for you.</p>
        </div>
      </div>
      <div className="settings-grid">
        <Card className="settings-card">
          <div className="settings-card__head">
            <span>
              <UserRound size={20} />
            </span>
            <div>
              <h2>Profile & goals</h2>
              <p>Your preferences, your pace.</p>
            </div>
          </div>
          <form onSubmit={save}>
            <Field
              label="Display name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <Field label="Email address" value={user.email} disabled />
            <Field
              label="Timezone"
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
              hint="Use an IANA timezone, such as Asia/Dhaka."
            />
            <div className="settings-card__divider" />
            <h3>Daily targets</h3>
            <div className="settings-card__fields">
              <Field
                label="Calories (kcal)"
                type="number"
                min="1"
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
            <Button type="submit" disabled={saving} icon={<Check size={17} />}>
              {saving ? "Saving..." : "Save settings"}
            </Button>
          </form>
        </Card>
        <div className="settings-side">
          <Card className="settings-card">
            <div className="settings-card__head">
              <span>{dark ? <Moon size={20} /> : <Sun size={20} />}</span>
              <div>
                <h2>Appearance</h2>
                <p>Choose your viewing comfort.</p>
              </div>
            </div>
            <button className="setting-row" onClick={onToggleTheme}>
              <span>{dark ? "Dark theme" : "Light theme"}</span>
              <strong>Change</strong>
            </button>
          </Card>
          <Card className="settings-card">
            <div className="settings-card__head">
              <span>
                <ShieldCheck size={20} />
              </span>
              <div>
                <h2>Privacy & data</h2>
                <p>Your diary belongs to you.</p>
              </div>
            </div>
            <p>
              Meal photos and records stay private to your account. Sample food
              values are illustrative and should be checked against reliable
              sources.
            </p>
            <button
              className="setting-row setting-row--danger"
              onClick={onDelete}
            >
              <span>
                <Trash2 size={17} /> Delete my account
              </span>
              <strong>Delete</strong>
            </button>
          </Card>
        </div>
      </div>
    </>
  );
}
