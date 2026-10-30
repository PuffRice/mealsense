import {
  ArrowRight,
  Camera,
  Flame,
  Plus,
  Sparkles,
  Utensils,
} from "lucide-react";
import { Badge, Button, Card, EmptyState, Progress } from "../../design/ui";
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
  return (
    <Card className="macro-card">
      <div className="macro-card__top">
        <span className={`macro-card__dot macro-card__dot--${tone}`} />
        <span>{label}</span>
      </div>
      <div className="macro-card__value">
        {Math.round(value)}
        <small>{goal ? ` / ${goal} ${unit}` : ` ${unit} · no goal set`}</small>
      </div>
      {goal > 0 && <Progress value={value} max={goal} color={tone} />}
      <p>{detail}</p>
    </Card>
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
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">YOUR DAILY DASHBOARD</span>
          <h1>
            Hello, {user.display_name?.split(" ")[0] || "friend"}{" "}
            <span className="wave">✳</span>
          </h1>
          <p>A little progress every day goes a long way.</p>
        </div>
        <div className="date-pill">{today}</div>
      </div>
      <div className="overview-grid">
        <Card className="hero-card">
          <div className="hero-card__copy">
            <Badge tone="green">
              <Sparkles size={14} /> TODAY'S SNAPSHOT
            </Badge>
            <h2>
              Every meal is a<br />
              fresh start.
            </h2>
            <p>
              Keep tracking to see the story your food tells. You're doing great
              just by showing up.
            </p>
            <Button
              variant="secondary"
              icon={<Plus size={18} />}
              onClick={onAdd}
            >
              Add a meal
            </Button>
          </div>
          <div className="hero-card__visual">
            <div
              className="calorie-ring"
              style={{ "--ring": `${pct}%` } as React.CSSProperties}
            >
              <div>
                <Flame size={25} />
                <strong>{Math.round(kcal)}</strong>
                <small>{goal ? `of ${goal} kcal` : "kcal logged"}</small>
              </div>
            </div>
            <span className="hero-card__ring-label">
              {goal ? `${pct}% of daily goal` : "Set a goal in Settings"}
            </span>
          </div>
        </Card>
        <Card className="scan-card">
          <div className="scan-card__icon">
            <Camera size={25} />
          </div>
          <h3>What did you eat?</h3>
          <p>Upload a photo or add foods by hand. You're always in control.</p>
          <Button
            variant="secondary"
            onClick={onAdd}
            icon={<ArrowRight size={17} />}
          >
            Log your meal
          </Button>
          <FoodArt variant="fruit" compact />
        </Card>
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
        <Card className="recent-card">
          <div className="card-heading">
            <div>
              <h2>Recent meals</h2>
              <p>Your food diary for today</p>
            </div>
            <button onClick={onMeals}>
              View all <ArrowRight size={16} />
            </button>
          </div>
          {todayMeals.length ? (
            <div>
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
              icon={<Utensils size={25} />}
              title="No meals logged yet"
              text="Start with your first meal and see your day take shape."
              action={
                <Button size="sm" onClick={onAdd} icon={<Plus size={16} />}>
                  Add a meal
                </Button>
              }
            />
          )}
        </Card>
        <Card className="week-card">
          <div className="card-heading">
            <div>
              <h2>Your week at a glance</h2>
              <p>Calories logged each day</p>
            </div>
            <button onClick={onInsights}>
              Insights <ArrowRight size={16} />
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
              const height = Number(day.totals.kcal)
                ? Math.max(
                    8,
                    Math.min(100, (Number(day.totals.kcal) / scale) * 100),
                  )
                : 0;
              return (
                <div className="week-bars__col" key={day.date}>
                  <div className="week-bars__track">
                    <span
                      style={{ height: `${height}%` }}
                      className={
                        day.date === daily?.date ? "week-bars__today" : ""
                      }
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
        </Card>
      </div>
    </>
  );
}
