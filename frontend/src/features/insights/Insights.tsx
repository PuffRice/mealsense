import { BarChart3, CalendarDays, Flame, TrendingUp } from "lucide-react";
import { Badge, Card, EmptyState } from "../../design/ui";
import type { Daily, User } from "../../lib/types";

export function Insights({ user, weekly }: { user: User; weekly: Daily[] }) {
  const logged = weekly.filter((day) => day.meal_count > 0);
  const sum = weekly.reduce((total, day) => total + Number(day.totals.kcal), 0);
  const average = logged.length ? Math.round(sum / logged.length) : 0;
  const scale =
    user.profile.daily_kcal_goal ||
    Math.max(500, ...weekly.map((day) => Number(day.totals.kcal)));
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">A CLEARER PICTURE</span>
          <h1>Insights</h1>
          <p>See your patterns, celebrate your progress.</p>
        </div>
        <Badge tone="green">
          <CalendarDays size={15} /> Last 7 days
        </Badge>
      </div>
      <div className="insight-stats">
        <Card>
          <span className="insight-stats__icon">
            <Flame size={21} />
          </span>
          <small>Average logged calories</small>
          <strong>
            {average} <span>kcal / day</span>
          </strong>
          <p>
            Across {logged.length} day{logged.length === 1 ? "" : "s"} with
            logged meals
          </p>
        </Card>
        <Card>
          <span className="insight-stats__icon">
            <BarChart3 size={21} />
          </span>
          <small>Meals logged</small>
          <strong>{weekly.reduce((n, day) => n + day.meal_count, 0)}</strong>
          <p>Every entry helps you learn</p>
        </Card>
        <Card>
          <span className="insight-stats__icon">
            <TrendingUp size={21} />
          </span>
          <small>Daily goal</small>
          <strong>
            {user.profile.daily_kcal_goal || "Not set"}{" "}
            {user.profile.daily_kcal_goal > 0 && <span>kcal</span>}
          </strong>
          <p>Adjust your goal in Settings</p>
        </Card>
      </div>
      <Card className="insight-chart">
        <div className="card-heading">
          <div>
            <h2>Calories over time</h2>
            <p>Your logged intake, shown day by day</p>
          </div>
        </div>
        {logged.length ? (
          <div className="insight-chart__plot">
            {weekly.map((day) => (
              <div className="insight-chart__col" key={day.date}>
                <span className="insight-chart__number">
                  {Number(day.totals.kcal)
                    ? Math.round(Number(day.totals.kcal))
                    : "—"}
                </span>
                <div className="insight-chart__track">
                  <div
                    style={{
                      height: `${Number(day.totals.kcal) ? Math.max(3, Math.min(100, (Number(day.totals.kcal) / scale) * 100)) : 0}%`,
                    }}
                  />
                </div>
                <small>
                  {new Date(`${day.date}T12:00:00`).toLocaleDateString(
                    "en-US",
                    { weekday: "short" },
                  )}
                </small>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<BarChart3 size={26} />}
            title="Insights grow with you"
            text="Log a few meals and your weekly picture will appear here."
          />
        )}
        <p className="insight-chart__note">
          These numbers are estimates based on confirmed foods and portions.
          Missing logs make a day look lower than what you ate.
        </p>
      </Card>
    </>
  );
}
