import {
  ArrowRight,
  Camera,
  Flame,
  Plus,
  Sparkles,
  Utensils,
} from "lucide-react";
import {
  Badge,
  EmptyState,
  GlassButton,
  GlassCard,
  Progress,
} from "../../design/ui";
import { FoodArt } from "../../components/FoodArt";
import type { Daily, Meal, User } from "../../lib/types";

function MacroCard({
  label,
  value,
  goal,
  unit,
  tone,
  detail,
}: {
  label: string;
  value: number;
  goal: number;
  unit: string;
  tone: "brand" | "lime" | "orange";
  detail: string;
}) {
  const pct = goal > 0 ? Math.min(100, Math.round((value / goal) * 100)) : null;

  return (
    <GlassCard interactive className="macro-card">
      <div className="macro-card__top">
        <div className="macro-card__title">
          <span className={`macro-card__dot macro-card__dot--${tone}`} />
          <span>{label}</span>
        </div>
        {pct !== null && <span className="macro-card__pct">{pct}%</span>}
      </div>
      <div className="macro-card__value">
        {Math.round(value)}
        <small>{goal ? ` / ${goal} ${unit}` : ` ${unit} · no goal set`}</small>
      </div>
      <Progress value={value} max={goal > 0 ? goal : 100} color={tone} />
      <p>{detail}</p>
    </GlassCard>
  );
}

function MealRow({ meal, timezone }: { meal: Meal; timezone: string }) {
  const variant =
    meal.meal_type === "breakfast"
      ? "fruit"
      : meal.meal_type === "dinner"
        ? "grain"
        : "salad";
  return (
    <div className="meal-row">
      <FoodArt variant={variant} compact />
      <div className="meal-row__body">
        <strong>{meal.items.map((item) => item.food_name).join(", ")}</strong>
        <span>
          {meal.meal_type} ·{" "}
          {new Date(meal.eaten_at).toLocaleTimeString([], {
            hour: "numeric",
            minute: "2-digit",
            timeZone: timezone,
          })}
        </span>
      </div>
      <div className="meal-row__calories">
        <strong>{Math.round(Number(meal.totals.kcal))}</strong>
        <span>kcal</span>
      </div>
    </div>
  );
}

export function Overview({
  user,
  daily,
  weekly,
  meals,
  onAdd,
  onMeals,
  onInsights,
}: {
  user: User;
  daily: Daily | null;
  weekly: Daily[];
  meals: Meal[];
  onAdd: () => void;
  onMeals: () => void;
  onInsights: () => void;
}) {
  const today = daily?.date
    ? new Date(`${daily.date}T12:00:00`).toLocaleDateString("en-US", {
        weekday: "long",
        month: "long",
        day: "numeric",
      })
    : "Today";
  const todayMeals = meals.filter(
    (meal) =>
      new Intl.DateTimeFormat("en-CA", {
        timeZone: user.profile.timezone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(new Date(meal.eaten_at)) === daily?.date,
  );
  const kcal = Number(daily?.totals.kcal || 0),
    goal = user.profile.daily_kcal_goal;
  const pct = goal ? Math.min(100, Math.round((kcal / goal) * 100)) : 0;
  const remaining = goal ? Math.max(0, Math.round(goal - kcal)) : null;

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            <Sparkles size={13} /> YOUR DAILY DASHBOARD
          </span>
          <h1>Hello, {user.display_name?.split(" ")[0] || "friend"}</h1>
          <p>Review your meals and nutrition for today.</p>
        </div>
        <div className="date-pill glass-panel glass-panel--subtle">{today}</div>
      </div>

      <div className="overview-grid">
        <GlassCard elevated className="hero-card">
          <div className="hero-card__copy">
            <Badge tone="green">TODAY'S SUMMARY</Badge>
            <h2>Calories logged today</h2>
            <p>
              Estimated from the meals you saved. Add a meal to update your
              total.
            </p>
            <div className="hero-card__metrics">
              <div className="hero-metric">
                <span>Logged</span>
                <strong>{Math.round(kcal)} kcal</strong>
              </div>
              <div className="hero-metric">
                <span>{remaining !== null ? "Remaining" : "Meals today"}</span>
                <strong>
                  {remaining !== null
                    ? `${remaining} kcal`
                    : `${todayMeals.length}`}
                </strong>
              </div>
            </div>
            <GlassButton
              variant="primary"
              icon={<Plus size={17} />}
              onClick={onAdd}
            >
              Add a meal
            </GlassButton>
          </div>
          <div className="hero-card__visual">
            <div
              className="calorie-ring"
              style={{ "--ring": `${pct}%` } as React.CSSProperties}
            >
              <div>
                <Flame size={22} />
                <strong>{Math.round(kcal)}</strong>
                <small>{goal ? `of ${goal} kcal` : "kcal logged"}</small>
              </div>
            </div>
            <span className="hero-card__ring-label">
              {goal ? `${pct}% of daily goal` : "Set a goal in Settings"}
            </span>
          </div>
        </GlassCard>

        <GlassCard interactive className="scan-card">
          <div className="scan-card__top">
            <div className="scan-card__icon">
              <Camera size={22} />
            </div>
            <Badge tone="neutral">AI & Manual</Badge>
          </div>
          <h3>What did you eat?</h3>
          <p>Upload a photo or add foods by hand. You're always in control.</p>
          <GlassButton
            variant="secondary"
            onClick={onAdd}
            icon={<ArrowRight size={16} />}
          >
            Log your meal
          </GlassButton>
        </GlassCard>
      </div>

      <div className="section-title">
        <div>
          <h2>Today's nutrition</h2>
          <p>Based on the meals you've logged</p>
        </div>
        <span className="section-title__hint">
          Estimates, not medical advice
        </span>
      </div>

      <div className="macro-grid">
        <MacroCard
          label="Protein"
          value={Number(daily?.totals.protein_g || 0)}
          goal={user.profile.protein_goal_g}
          unit="g"
          tone="brand"
          detail="Helps build and repair"
        />
        <MacroCard
          label="Carbs"
          value={Number(daily?.totals.carbs_g || 0)}
          goal={user.profile.carbs_goal_g}
          unit="g"
          tone="lime"
          detail="Fuel for your day"
        />
        <MacroCard
          label="Fats"
          value={Number(daily?.totals.fat_g || 0)}
          goal={user.profile.fat_goal_g}
          unit="g"
          tone="orange"
          detail="Part of a balanced diet"
        />
      </div>

      <div className="lower-grid">
        <GlassCard className="recent-card">
          <div className="card-heading">
            <div>
              <h2>Recent meals</h2>
              <p>Your food diary for today</p>
            </div>
            <button type="button" onClick={onMeals}>
              View all <ArrowRight size={15} />
            </button>
          </div>
          {todayMeals.length ? (
            <div className="meal-row-list">
              {todayMeals.slice(0, 3).map((meal) => (
                <MealRow
                  key={meal.id}
                  meal={meal}
                  timezone={user.profile.timezone}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<Utensils size={23} />}
              title="No meals logged yet"
              text="Start with your first meal and see your day take shape."
              action={
                <GlassButton
                  size="sm"
                  onClick={onAdd}
                  icon={<Plus size={15} />}
                >
                  Add a meal
                </GlassButton>
              }
            />
          )}
        </GlassCard>

        <GlassCard className="week-card">
          <div className="card-heading">
            <div>
              <h2>Your week at a glance</h2>
              <p>Calories logged each day</p>
            </div>
            <button type="button" onClick={onInsights}>
              Insights <ArrowRight size={15} />
            </button>
          </div>
          <div className="week-bars">
            {weekly.map((day) => {
              const scale =
                goal ||
                Math.max(
                  500,
                  ...weekly.map((value) => Number(value.totals.kcal)),
                );
              const dayKcal = Math.round(Number(day.totals.kcal));
              const height = dayKcal
                ? Math.max(8, Math.min(100, (dayKcal / scale) * 100))
                : 0;
              const isToday = day.date === daily?.date;
              return (
                <div
                  className={`week-bars__col ${isToday ? "week-bars__col--today" : ""}`}
                  key={day.date}
                  title={`${day.date}: ${dayKcal} kcal`}
                >
                  <span className="week-bars__val">
                    {dayKcal ? dayKcal : "—"}
                  </span>
                  <div className="week-bars__track">
                    <span
                      style={{ height: `${height}%` }}
                      className={isToday ? "week-bars__today" : ""}
                    />
                  </div>
                  <small>
                    {new Date(`${day.date}T12:00:00`).toLocaleDateString(
                      "en-US",
                      { weekday: "short" },
                    )}
                  </small>
                </div>
              );
            })}
          </div>
        </GlassCard>
      </div>
    </>
  );
}
