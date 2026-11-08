import {
  BarChart3,
  CalendarDays,
  Flame,
  PieChart,
  TrendingUp,
} from "lucide-react";
import { Badge, EmptyState, GlassCard, Progress } from "../../design/ui";
import type { Daily, User } from "../../lib/types";

export function Insights({ user, weekly }: { user: User; weekly: Daily[] }) {
  const logged = weekly.filter((day) => day.meal_count > 0);
  const sum = weekly.reduce((total, day) => total + Number(day.totals.kcal), 0);
  const average = logged.length ? Math.round(sum / logged.length) : 0;
  const scale =
    user.profile.daily_kcal_goal ||
    Math.max(500, ...weekly.map((day) => Number(day.totals.kcal)));

  const totalProtein = weekly.reduce(
    (total, day) => total + Number(day.totals.protein_g || 0),
    0,
  );
  const totalCarbs = weekly.reduce(
    (total, day) => total + Number(day.totals.carbs_g || 0),
    0,
  );
  const totalFat = weekly.reduce(
    (total, day) => total + Number(day.totals.fat_g || 0),
    0,
  );

  const avgProtein = logged.length
    ? Math.round(totalProtein / logged.length)
    : 0;
  const avgCarbs = logged.length ? Math.round(totalCarbs / logged.length) : 0;
  const avgFat = logged.length ? Math.round(totalFat / logged.length) : 0;

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">A CLEARER PICTURE</span>
          <h1>Insights</h1>
          <p>See your patterns, celebrate your progress.</p>
        </div>
        <Badge tone="green">
          <CalendarDays size={14} /> Last 7 days
        </Badge>
      </div>

      <div className="insight-stats">
        <GlassCard interactive>
          <span className="insight-stats__icon">
            <Flame size={20} />
          </span>
          <small>Average logged calories</small>
          <strong>
            {average} <span>kcal / day</span>
          </strong>
          <p>
            Across {logged.length} day{logged.length === 1 ? "" : "s"} with
            logged meals
          </p>
        </GlassCard>

        <GlassCard interactive>
          <span className="insight-stats__icon">
            <BarChart3 size={20} />
          </span>
          <small>Meals logged</small>
          <strong>{weekly.reduce((n, day) => n + day.meal_count, 0)}</strong>
          <p>Every entry helps you learn</p>
        </GlassCard>

        <GlassCard interactive>
          <span className="insight-stats__icon">
            <TrendingUp size={20} />
          </span>
          <small>Daily goal</small>
          <strong>
            {user.profile.daily_kcal_goal || "Not set"}{" "}
            {user.profile.daily_kcal_goal > 0 && <span>kcal</span>}
          </strong>
          <p>Adjust your goal in Profile & goals</p>
        </GlassCard>
      </div>

      <div className="insights-main-grid">
        <GlassCard className="insight-chart">
          <div className="card-heading">
            <div>
              <h2>Calories over time</h2>
              <p>Your logged intake, shown day by day</p>
            </div>
            {user.profile.daily_kcal_goal > 0 && (
              <Badge tone="neutral">
                Goal: {user.profile.daily_kcal_goal} kcal
              </Badge>
            )}
          </div>
          {logged.length ? (
            <div className="insight-chart__plot">
              {weekly.map((day) => {
                const dayKcal = Math.round(Number(day.totals.kcal));
                return (
                  <div className="insight-chart__col" key={day.date}>
                    <span className="insight-chart__number">
                      {dayKcal ? dayKcal : "—"}
                    </span>
                    <div className="insight-chart__track">
                      <div
                        style={{
                          height: `${dayKcal ? Math.max(4, Math.min(100, (dayKcal / scale) * 100)) : 0}%`,
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
                );
              })}
            </div>
          ) : (
            <EmptyState
              icon={<BarChart3 size={24} />}
              title="Insights grow with you"
              text="Log a few meals and your weekly picture will appear here."
            />
          )}
          <p className="insight-chart__note">
            These numbers are estimates based on confirmed foods and portions.
            Missing logs make a day look lower than what you ate.
          </p>
        </GlassCard>

        <GlassCard className="insight-macros">
          <div className="card-heading">
            <div>
              <h2>Macronutrient breakdown</h2>
              <p>Daily average on active days vs. targets</p>
            </div>
            <span className="insight-stats__icon insight-stats__icon--sm">
              <PieChart size={17} />
            </span>
          </div>

          <div className="insight-macro-list">
            <div className="insight-macro-row">
              <div className="insight-macro-row__head">
                <span>
                  <i className="macro-card__dot macro-card__dot--brand" />
                  Protein
                </span>
                <strong>
                  {avgProtein}g
                  <small>
                    {user.profile.protein_goal_g
                      ? ` / ${user.profile.protein_goal_g}g goal`
                      : " / day"}
                  </small>
                </strong>
              </div>
              <Progress
                value={avgProtein}
                max={user.profile.protein_goal_g || 120}
                color="brand"
              />
            </div>

            <div className="insight-macro-row">
              <div className="insight-macro-row__head">
                <span>
                  <i className="macro-card__dot macro-card__dot--lime" />
                  Carbohydrates
                </span>
                <strong>
                  {avgCarbs}g
                  <small>
                    {user.profile.carbs_goal_g
                      ? ` / ${user.profile.carbs_goal_g}g goal`
                      : " / day"}
                  </small>
                </strong>
              </div>
              <Progress
                value={avgCarbs}
                max={user.profile.carbs_goal_g || 250}
                color="lime"
              />
            </div>

            <div className="insight-macro-row">
              <div className="insight-macro-row__head">
                <span>
                  <i className="macro-card__dot macro-card__dot--orange" />
                  Fats
                </span>
                <strong>
                  {avgFat}g
                  <small>
                    {user.profile.fat_goal_g
                      ? ` / ${user.profile.fat_goal_g}g goal`
                      : " / day"}
                  </small>
                </strong>
              </div>
              <Progress
                value={avgFat}
                max={user.profile.fat_goal_g || 80}
                color="orange"
              />
            </div>
          </div>

          <div className="insight-macro-summary glass-panel glass-panel--subtle">
            <div>
              <small>7-Day Protein</small>
              <strong>{Math.round(totalProtein)}g</strong>
            </div>
            <div>
              <small>7-Day Carbs</small>
              <strong>{Math.round(totalCarbs)}g</strong>
            </div>
            <div>
              <small>7-Day Fats</small>
              <strong>{Math.round(totalFat)}g</strong>
            </div>
          </div>
        </GlassCard>
      </div>
    </>
  );
}
