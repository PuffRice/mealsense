import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  CalendarRange,
  Check,
  ClipboardCheck,
  Clock,
  Copy,
  Flame,
  ListChecks,
  Loader2,
  Lock,
  Search,
  Send,
  ShieldCheck,
  Stethoscope,
  Utensils,
} from "lucide-react";
import { Badge, EmptyState, GlassButton, GlassCard } from "../../design/ui";
import { ApiError, doctorPortalApi } from "../../lib/api";
import type {
  DoctorAnalytics,
  DoctorHistory,
  DoctorStatus,
} from "../../lib/types";

const POLL_MS = 15000;

type Stage = "form" | "pending" | "active" | "blocked";
type RangeKey = "30" | "90" | "365" | "all" | "custom";

function isoDaysAgo(days: number) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function todayIso() {
  const date = new Date();
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function formatWhen(value?: string | null) {
  if (!value) return "";
  return new Date(value).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function DoctorPortal() {
  const [stage, setStage] = useState<Stage>("form");
  const [identifier, setIdentifier] = useState("");
  const [doctorName, setDoctorName] = useState("");
  const [token, setToken] = useState("");
  const [statusData, setStatusData] = useState<DoctorStatus | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");

  const [rangeKey, setRangeKey] = useState<RangeKey>("30");
  const [fromDate, setFromDate] = useState(isoDaysAgo(29));
  const [toDate, setToDate] = useState(todayIso());
  const [history, setHistory] = useState<DoctorHistory | null>(null);
  const [analytics, setAnalytics] = useState<DoctorAnalytics | null>(null);
  const [dataError, setDataError] = useState("");
  const [loadingData, setLoadingData] = useState(false);
  const [copied, setCopied] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const pollRef = useRef<number | null>(null);

  const rangeParams = useMemo(() => {
    if (rangeKey === "all") return { from: undefined, to: undefined };
    if (rangeKey === "custom") return { from: fromDate, to: toDate };
    const days = rangeKey === "30" ? 29 : rangeKey === "90" ? 89 : 364;
    return { from: isoDaysAgo(days), to: todayIso() };
  }, [rangeKey, fromDate, toDate]);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const loadDashboard = useCallback(
    async (
      activeToken: string,
      params: { from?: string; to?: string },
      offset = 0,
    ) => {
      setLoadingData(true);
      try {
        const [nextHistory, nextAnalytics] = await Promise.all([
          doctorPortalApi.history(activeToken, params.from, params.to, offset),
          doctorPortalApi.analytics(activeToken, params.from, params.to),
        ]);
        setHistory((current) =>
          offset > 0 && current
            ? {
                ...nextHistory,
                offset,
                meals: [...current.meals, ...nextHistory.meals],
              }
            : nextHistory,
        );
        setAnalytics(nextAnalytics);
        setDataError("");
      } catch (cause) {
        const message =
          cause instanceof Error ? cause.message : "Could not load the record.";
        if (
          cause instanceof ApiError &&
          (cause.status === 403 || cause.status === 404)
        ) {
          setStage("blocked");
          setToken("");
        } else {
          setDataError(message);
        }
      } finally {
        setLoadingData(false);
      }
    },
    [],
  );

  const checkStatus = useCallback(
    async (activeToken: string) => {
      try {
        const next = await doctorPortalApi.status(activeToken);
        setStatusData(next);
        if (next.active) {
          stopPolling();
          setStage("active");
          void loadDashboard(activeToken, rangeParams);
        } else if (next.status === "pending") {
          setStage("pending");
        } else {
          stopPolling();
          setStage("blocked");
        }
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 404) {
          // Token may be a pending synthetic token for an unmatched account or unknown code;
          // stay in pending stage if already polling, or show notice on manual reconnect.
          setStage("pending");
        }
      }
      return;
    },
    [loadDashboard, rangeParams, stopPolling],
  );

  useEffect(() => {
    if (!token) return;
    void checkStatus(token);
    return stopPolling;
    // Run once on mount; polling is started separately below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll while the request is waiting for patient approval.
  useEffect(() => {
    if (stage !== "pending" || !token) return;
    stopPolling();
    pollRef.current = window.setInterval(() => {
      if (document.visibilityState === "visible") void checkStatus(token);
    }, POLL_MS);
    return stopPolling;
  }, [stage, token, checkStatus, stopPolling]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setFormError("");
    setNotice("");
    try {
      const result = await doctorPortalApi.request(identifier, doctorName);
      if (result.token) {
        setToken(result.token);
        setStage("pending");
        await checkStatus(result.token);
      } else {
        setNotice(result.message);
      }
    } catch (cause) {
      setFormError(
        cause instanceof Error ? cause.message : "Could not send the request.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  function forget() {
    stopPolling();
    setToken("");
    setStatusData(null);
    setHistory(null);
    setAnalytics(null);
    setStage("form");
    setNotice("");
  }

  async function copyToken() {
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  async function loadMore() {
    if (!token || !history) return;
    setLoadingMore(true);
    const nextOffset = history.meals.length;
    await loadDashboard(token, rangeParams, nextOffset);
    setLoadingMore(false);
  }

  function changeRange(next: RangeKey) {
    setRangeKey(next);
    if (token && stage === "active") {
      const params =
        next === "all"
          ? { from: undefined, to: undefined }
          : next === "custom"
            ? { from: fromDate, to: toDate }
            : {
                from: isoDaysAgo(next === "30" ? 29 : next === "90" ? 89 : 364),
                to: todayIso(),
              };
      setHistory(null);
      void loadDashboard(token, params);
    }
  }

  function applyCustom() {
    if (!fromDate || !toDate) return;
    if (token && stage === "active") {
      setHistory(null);
      void loadDashboard(token, { from: fromDate, to: toDate });
    }
  }

  const maxMonthlyKcal = Math.max(
    1,
    ...(analytics?.monthly ?? []).map((row) => Number(row.kcal)),
  );
  const maxFoodGrams = Math.max(
    1,
    ...(analytics?.most_consumed ?? []).map((row) => Number(row.grams)),
  );

  return (
    <div className="doctor-shell">
      <header className="doctor-shell__head">
        <div className="brand">
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
        <Badge tone="green">
          <Stethoscope size={13} /> Doctor access
        </Badge>
      </header>

      {stage === "form" && (
        <motion.main
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          className="doctor-shell__main"
        >
          <GlassCard className="doctor-form-card">
            <div className="card-heading">
              <div>
                <h1>Review a patient's meal history</h1>
                <p>
                  Enter the patient's MealSense email or phone. They approve the
                  request in their own app — no account or password is needed
                  from you.
                </p>
              </div>
              <span className="doctor-form-card__icon">
                <Stethoscope size={20} />
              </span>
            </div>
            <form onSubmit={submit} className="doctor-form">
              <label className="field">
                <span className="field__label">Patient email or phone</span>
                <input
                  className="field__input glass-input"
                  value={identifier}
                  onChange={(event) => setIdentifier(event.target.value)}
                  placeholder="patient@example.com or 8801712345678"
                  autoComplete="off"
                  required
                />
              </label>
              <label className="field">
                <span className="field__label">Your name</span>
                <input
                  className="field__input glass-input"
                  value={doctorName}
                  onChange={(event) => setDoctorName(event.target.value)}
                  placeholder="Dr. Ayesha Rahman"
                  maxLength={120}
                  required
                />
                <span className="field__hint">
                  The patient sees this name when deciding to grant access.
                </span>
              </label>
              {formError && (
                <p className="doctor-form__error" role="alert">
                  {formError}
                </p>
              )}
              {notice && (
                <p className="doctor-form__notice" role="status">
                  {notice}
                </p>
              )}
              <GlassButton
                type="submit"
                disabled={submitting}
                icon={<Send size={15} />}
              >
                {submitting ? "Sending request…" : "Request access"}
              </GlassButton>
            </form>
            <p className="doctor-form__privacy">
              The patient decides what happens. If they approve, you can view
              their meal list and nutrition analytics for 72 hours — never
              photos, notes, or health metrics. They can revoke access at any
              time.
            </p>
          </GlassCard>
        </motion.main>
      )}

      {stage === "pending" && (
        <motion.main
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          className="doctor-shell__main"
        >
          <GlassCard className="doctor-form-card">
            <div className="card-heading">
              <div>
                <h1>Waiting for approval</h1>
                <p>
                  This page updates automatically once the patient approves or
                  denies your request.
                </p>
              </div>
              <span className="doctor-form-card__icon doctor-form-card__icon--pulse">
                <Loader2 size={20} className="doctor-spin" />
              </span>
            </div>
            <div className="doctor-code">
              <span className="field__label">
                Access code for this device session
              </span>
              <div className="doctor-code__row">
                <code>{token}</code>
                <GlassButton
                  size="sm"
                  variant="secondary"
                  icon={copied ? <Check size={14} /> : <Copy size={14} />}
                  onClick={() => void copyToken()}
                >
                  {copied ? "Copied" : "Copy"}
                </GlassButton>
              </div>
              <p>
                Keep this tab open, or save the code — pasting it back into the
                access code box below reconnects you to the same request.
              </p>
            </div>
            <GlassButton
              variant="secondary"
              size="sm"
              icon={<Lock size={14} />}
              onClick={forget}
            >
              Cancel and clear this page
            </GlassButton>
          </GlassCard>
        </motion.main>
      )}

      {stage === "blocked" && statusData && (
        <motion.main
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          className="doctor-shell__main"
        >
          <GlassCard className="doctor-form-card">
            <div className="card-heading">
              <div>
                <h1>Access is not available</h1>
                <p>
                  {statusData.status === "denied" &&
                    "The patient denied this request. You can send a new one if they change their mind."}
                  {statusData.status === "revoked" &&
                    "The patient revoked access. Ask them to approve again if they want to continue sharing."}
                  {statusData.status === "expired" &&
                    "The approved window has ended. Send a new request to continue."}
                </p>
              </div>
              <span className="doctor-form-card__icon">
                <Lock size={20} />
              </span>
            </div>
            <GlassButton size="sm" icon={<Send size={15} />} onClick={forget}>
              Start a new request
            </GlassButton>
          </GlassCard>
        </motion.main>
      )}

      {stage === "active" && statusData?.active && (
        <motion.main
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          className="doctor-shell__main"
        >
          <GlassCard className="doctor-patient-bar">
            <div className="doctor-patient-bar__info">
              <span className="sharing-request__avatar sharing-request__avatar--active">
                <ShieldCheck size={18} />
              </span>
              <div>
                <h1>{statusData.patient_name}</h1>
                <p>
                  <Clock size={13} /> Access ends{" "}
                  {formatWhen(statusData.expires_at)} · patient time zone{" "}
                  {statusData.patient_timezone}
                </p>
              </div>
            </div>
            <div className="doctor-patient-bar__actions">
              <GlassButton
                size="sm"
                variant="secondary"
                icon={<ClipboardCheck size={14} />}
                onClick={() => void copyToken()}
              >
                {copied ? "Code copied" : "Copy access code"}
              </GlassButton>
              <GlassButton
                size="sm"
                variant="danger"
                icon={<Lock size={14} />}
                onClick={forget}
              >
                Close access view
              </GlassButton>
            </div>
          </GlassCard>

          <GlassCard className="list-card">
            <div className="list-toolbar">
              <div className="filter-tabs" role="group" aria-label="Date range">
                {(
                  [
                    ["30", "30 days"],
                    ["90", "90 days"],
                    ["365", "1 year"],
                    ["all", "All time"],
                    ["custom", "Custom"],
                  ] as [RangeKey, string][]
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={rangeKey === value ? "filter-tabs__active" : ""}
                    onClick={() => changeRange(value)}
                  >
                    {rangeKey === value && (
                      <motion.span
                        layoutId="doctor-range-pill"
                        className="filter-tabs__pill"
                        transition={{
                          type: "spring",
                          stiffness: 350,
                          damping: 28,
                        }}
                        aria-hidden="true"
                      />
                    )}
                    <span className="filter-tab__label">{label}</span>
                  </button>
                ))}
              </div>
              {rangeKey === "custom" && (
                <div className="doctor-custom-range">
                  <label className="field">
                    <span className="field__label">From</span>
                    <input
                      type="date"
                      className="field__input glass-input"
                      value={fromDate}
                      max={todayIso()}
                      onChange={(event) => setFromDate(event.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span className="field__label">To</span>
                    <input
                      type="date"
                      className="field__input glass-input"
                      value={toDate}
                      max={todayIso()}
                      onChange={(event) => setToDate(event.target.value)}
                    />
                  </label>
                  <GlassButton
                    size="sm"
                    icon={<CalendarRange size={14} />}
                    onClick={applyCustom}
                  >
                    Apply
                  </GlassButton>
                </div>
              )}
            </div>
          </GlassCard>

          {loadingData && !analytics && (
            <p className="doctor-loading">
              <Loader2 size={15} className="doctor-spin" /> Loading record…
            </p>
          )}
          {dataError && (
            <div className="error-banner" role="alert">
              {dataError}{" "}
              <button onClick={() => void loadDashboard(token, rangeParams)}>
                Retry
              </button>
            </div>
          )}

          {analytics && (
            <>
              <div className="insight-stats">
                <GlassCard interactive>
                  <span className="insight-stats__icon">
                    <Flame size={20} />
                  </span>
                  <small>Total energy</small>
                  <strong>
                    {Math.round(Number(analytics.totals.kcal))}{" "}
                    <span>kcal</span>
                  </strong>
                  <p>
                    Across {analytics.items_logged} logged food
                    {analytics.items_logged === 1 ? "" : "s"}
                  </p>
                </GlassCard>
                <GlassCard interactive>
                  <span className="insight-stats__icon">
                    <Activity size={20} />
                  </span>
                  <small>Average on logged days</small>
                  <strong>
                    {Math.round(Number(analytics.avg_kcal_per_logged_day))}{" "}
                    <span>kcal / day</span>
                  </strong>
                  <p>
                    {analytics.logged_days} day
                    {analytics.logged_days === 1 ? "" : "s"} with meals
                  </p>
                </GlassCard>
                <GlassCard interactive>
                  <span className="insight-stats__icon">
                    <Utensils size={20} />
                  </span>
                  <small>Meals logged</small>
                  <strong>{analytics.meals_logged}</strong>
                  <p>
                    {analytics.totals.grams !== "0.00" &&
                      `${Math.round(Number(analytics.totals.grams))} g of food in total`}
                  </p>
                </GlassCard>
              </div>

              <div className="doctor-analytics-grid">
                <GlassCard className="doctor-food-card">
                  <div className="card-heading">
                    <div>
                      <h2>Most consumed foods</h2>
                      <p>Top foods by total grams in the selected range.</p>
                    </div>
                    <span className="insight-stats__icon insight-stats__icon--sm">
                      <BarChart3 size={17} />
                    </span>
                  </div>
                  {analytics.most_consumed.length ? (
                    <div className="doctor-food-list">
                      {analytics.most_consumed.map((food) => (
                        <div className="doctor-food-row" key={food.food_name}>
                          <div className="doctor-food-row__head">
                            <span>{food.food_name}</span>
                            <strong>
                              {Math.round(Number(food.grams))} g
                              <small>
                                {" "}
                                · {food.times}× ·{" "}
                                {Math.round(Number(food.kcal))} kcal
                              </small>
                            </strong>
                          </div>
                          <div className="doctor-food-row__track">
                            <span
                              style={{
                                width: `${Math.max(4, (Number(food.grams) / maxFoodGrams) * 100)}%`,
                              }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      icon={<Utensils size={22} />}
                      title="No food logged"
                      text="Nothing was logged in this range."
                    />
                  )}
                </GlassCard>

                <GlassCard className="doctor-monthly-card">
                  <div className="card-heading">
                    <div>
                      <h2>Energy by month</h2>
                      <p>Monthly totals from the patient's local calendar.</p>
                    </div>
                    {analytics.by_meal_type.length > 0 && (
                      <div className="doctor-mealtype-chips">
                        {analytics.by_meal_type.map((row) => (
                          <Badge tone="neutral" key={row.meal_type}>
                            {row.meal_type} · {row.meals}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                  {analytics.monthly.length ? (
                    <div className="insight-chart__plot doctor-monthly-plot">
                      {analytics.monthly.map((row) => (
                        <div className="insight-chart__col" key={row.month}>
                          <span className="insight-chart__number">
                            {Math.round(Number(row.kcal))}
                          </span>
                          <div className="insight-chart__track">
                            <div
                              style={{
                                height: `${Math.max(4, (Number(row.kcal) / maxMonthlyKcal) * 100)}%`,
                              }}
                            />
                          </div>
                          <small>{row.month}</small>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      icon={<BarChart3 size={22} />}
                      title="No monthly data"
                      text="Months with logged meals will appear here."
                    />
                  )}
                </GlassCard>
              </div>

              <GlassCard className="list-card">
                <div className="card-heading">
                  <div>
                    <h2>Food frequency</h2>
                    <p>Every food logged in the range, most frequent first.</p>
                  </div>
                  <Badge tone="green">
                    {analytics.food_frequency.length} foods
                  </Badge>
                </div>
                {analytics.food_frequency.length ? (
                  <div className="doctor-table-wrap">
                    <table className="doctor-table">
                      <thead>
                        <tr>
                          <th scope="col">Food</th>
                          <th scope="col">Times logged</th>
                          <th scope="col">Total grams</th>
                          <th scope="col">Total kcal</th>
                        </tr>
                      </thead>
                      <tbody>
                        {analytics.food_frequency.map((food) => (
                          <tr key={food.food_name}>
                            <td>{food.food_name}</td>
                            <td>{food.times}</td>
                            <td>{Math.round(Number(food.grams))} g</td>
                            <td>{Math.round(Number(food.kcal))}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState
                    icon={<Search size={22} />}
                    title="Nothing to summarize"
                    text="Log data will appear here once meals exist in this range."
                  />
                )}
              </GlassCard>
            </>
          )}

          {history && (
            <GlassCard className="list-card">
              <div className="card-heading">
                <div>
                  <h2>Meal history</h2>
                  <p>
                    {history.count} meal{history.count === 1 ? "" : "s"} in
                    range · newest first. Photos and notes are not included.
                  </p>
                </div>
                <Badge tone="neutral">
                  <ListChecks size={13} /> {history.meals.length} shown
                </Badge>
              </div>
              {history.meals.length ? (
                <>
                  <div className="meal-list">
                    {history.meals.map((meal) => (
                      <article className="meal-list__item" key={meal.id}>
                        <div className="doctor-meal-date">
                          <strong>{meal.local_date}</strong>
                          <Badge tone="green">{meal.meal_type}</Badge>
                        </div>
                        <div className="meal-list__detail">
                          <h3>
                            {meal.items
                              .map((item) => item.food_name)
                              .join(", ")}
                          </h3>
                          <p>
                            {meal.items
                              .map(
                                (item) =>
                                  `${Number(item.grams)} g ${item.food_name}`,
                              )
                              .join(" · ")}
                          </p>
                        </div>
                        <div className="meal-list__right">
                          <strong>
                            {Math.round(Number(meal.totals.kcal))}{" "}
                            <small>kcal</small>
                          </strong>
                          <span>
                            P {Math.round(Number(meal.totals.protein_g))}g · C{" "}
                            {Math.round(Number(meal.totals.carbs_g))}g · F{" "}
                            {Math.round(Number(meal.totals.fat_g))}g
                          </span>
                        </div>
                      </article>
                    ))}
                  </div>
                  {history.meals.length < history.count && (
                    <div className="doctor-history-more">
                      <GlassButton
                        size="sm"
                        variant="secondary"
                        disabled={loadingMore}
                        icon={
                          loadingMore ? (
                            <Loader2 size={14} className="doctor-spin" />
                          ) : undefined
                        }
                        onClick={() => void loadMore()}
                      >
                        Load more meals ({history.count - history.meals.length}{" "}
                        remaining)
                      </GlassButton>
                    </div>
                  )}
                </>
              ) : (
                <EmptyState
                  icon={<Utensils size={24} />}
                  title="No meals in this range"
                  text="Try a wider date range, or choose All time."
                />
              )}
            </GlassCard>
          )}

          <p className="doctor-disclaimer">
            Nutrition values are patient-confirmed estimates from their
            MealSense logs, not medical advice. Portion accuracy depends on the
            patient's own entries. This view contains no meal photos, personal
            notes, or health metrics.
          </p>
        </motion.main>
      )}
    </div>
  );
}
