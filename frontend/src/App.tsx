import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { WifiOff, X } from "lucide-react";
import { Layout, type Page } from "./components/Layout";
import { pageRevealVariants } from "./design/motion";
import { Field, GlassButton, GlassModal, ToastNotice } from "./design/ui";
import { LandingPage } from "./features/landing/LandingPage";
import { Overview } from "./features/overview/Overview";
import { MealsPage } from "./features/meals/MealsPage";
import { MealEditor } from "./features/meals/MealEditor";
import { Insights } from "./features/insights/Insights";
import { SharingPage } from "./features/sharing/SharingPage";
import { ProfilePage } from "./features/profile/ProfilePage";
import { Settings } from "./features/settings/Settings";
import { auth, doctorAccessApi, foodsApi, mealsApi } from "./lib/api";
import { clearLocalData, loadSnapshot, saveSnapshot } from "./lib/offline";
import type { Daily, Food, Meal, User } from "./lib/types";

function dateInZone(zone: string) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const part = (name: string) =>
    parts.find((item) => item.type === name)?.value || "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}
export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState<Page>("overview");
  const [meals, setMeals] = useState<Meal[]>([]);
  const [foods, setFoods] = useState<Food[]>([]);
  const [daily, setDaily] = useState<Daily | null>(null);
  const [weekly, setWeekly] = useState<Daily[]>([]);
  const [editing, setEditing] = useState<Meal | null | "new" | "camera">(null);
  const [dark, setDark] = useState(
    () => localStorage.getItem("mealsense-theme") === "dark",
  );
  const [online, setOnline] = useState(navigator.onLine);
  const [dataError, setDataError] = useState("");
  const [lastSynced, setLastSynced] = useState("");
  const [pendingRequests, setPendingRequests] = useState(0);
  const [toast, setToast] = useState<{
    type: "error" | "success" | "info";
    message: string;
  } | null>(null);
  const [mealToDelete, setMealToDelete] = useState<Meal | null>(null);
  const [deleteAccountOpen, setDeleteAccountOpen] = useState(false);
  const [deleteAccountPassword, setDeleteAccountPassword] = useState("");
  const [confirmBusy, setConfirmBusy] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("mealsense-theme", dark ? "dark" : "light");
  }, [dark]);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  useEffect(() => {
    const onUnauthorized = () => {
      setUser(null);
      setMeals([]);
      setDaily(null);
      setWeekly([]);
      setEditing(null);
      setPage("overview");
      if (window.location.pathname !== "/") {
        window.history.replaceState(null, "", "/");
      }
    };
    window.addEventListener("mealsense:unauthorized", onUnauthorized);
    return () =>
      window.removeEventListener("mealsense:unauthorized", onUnauthorized);
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 5000);
    return () => window.clearTimeout(timer);
  }, [toast]);
  const refresh = useCallback(async (activeUser: User) => {
    const [mealsRes, foodsRes, dailyRes, weeklyRes] = await Promise.allSettled([
      mealsApi.list(),
      foodsApi.list(),
      mealsApi.daily(dateInZone(activeUser.profile.timezone)),
      mealsApi.weekly(),
    ]);
    let nextMeals: Meal[] | undefined;
    let nextFoods: Food[] | undefined;
    let nextDaily: Daily | undefined;
    let nextWeekly: Daily[] | undefined;
    const errors: string[] = [];

    if (mealsRes.status === "fulfilled") {
      nextMeals = mealsRes.value;
      setMeals(nextMeals);
    } else {
      errors.push(
        mealsRes.reason instanceof Error
          ? mealsRes.reason.message
          : "Could not load meals.",
      );
    }
    if (foodsRes.status === "fulfilled") {
      nextFoods = foodsRes.value;
      setFoods(nextFoods);
    } else {
      errors.push(
        foodsRes.reason instanceof Error
          ? foodsRes.reason.message
          : "Could not load foods.",
      );
    }
    if (dailyRes.status === "fulfilled") {
      nextDaily = dailyRes.value;
      setDaily(nextDaily);
    } else {
      errors.push(
        dailyRes.reason instanceof Error
          ? dailyRes.reason.message
          : "Could not load daily summary.",
      );
    }
    if (weeklyRes.status === "fulfilled") {
      nextWeekly = weeklyRes.value;
      setWeekly(nextWeekly);
    } else {
      errors.push(
        weeklyRes.reason instanceof Error
          ? weeklyRes.reason.message
          : "Could not load weekly summary.",
      );
    }

    if (errors.length === 0 && nextMeals && nextFoods && nextDaily && nextWeekly) {
      setDataError("");
      const savedAt = new Date().toISOString();
      setLastSynced(savedAt);
      void saveSnapshot({
        user: activeUser,
        meals: nextMeals,
        foods: nextFoods,
        daily: nextDaily,
        weekly: nextWeekly,
        savedAt,
      }).catch(() => {});
    } else if (errors.length > 0) {
      setDataError(errors[0]);
    }
  }, []);
  useEffect(() => {
    auth
      .me()
      .then((active) => {
        setUser(active);
        return refresh(active);
      })
      .catch(async (cause) => {
        if (
          !navigator.onLine ||
          (cause instanceof Error &&
            cause.message.startsWith("Connection lost"))
        ) {
          const cached = await loadSnapshot().catch(() => null);
          if (cached) {
            setUser(cached.user);
            setMeals(cached.meals);
            setFoods(cached.foods);
            setDaily(cached.daily);
            setWeekly(cached.weekly);
            setLastSynced(cached.savedAt);
          }
        }
      })
      .finally(() => setLoading(false));
  }, [refresh]);
  useEffect(() => {
    if (!user) return;
    const sync = () => void refresh(user);
    window.addEventListener("online", sync);
    return () => window.removeEventListener("online", sync);
  }, [user, refresh]);
  useEffect(() => {
    if (!user) return;
    const checkRequests = () => {
      doctorAccessApi
        .list()
        .then((requests) =>
          setPendingRequests(
            requests.filter((request) => request.status === "pending").length,
          ),
        )
        .catch(() => {});
    };
    checkRequests();
    const timer = window.setInterval(checkRequests, 30000);
    return () => window.clearInterval(timer);
  }, [user, page]);
  useEffect(() => {
    if (!loading && !user && window.location.pathname !== "/") {
      window.history.replaceState(null, "", "/");
    }
  }, [loading, user]);
  async function logout() {
    if (!online) {
      setToast({
        type: "error",
        message: "Connect to the internet to securely log out.",
      });
      return;
    }
    try {
      await auth.logout();
      await clearLocalData();
      setUser(null);
      setMeals([]);
      setDaily(null);
      setWeekly([]);
      setEditing(null);
      setDataError("");
      setPage("overview");
      if (window.location.pathname !== "/") {
        window.history.replaceState(null, "", "/");
      }
    } catch (cause) {
      setToast({
        type: "error",
        message: cause instanceof Error ? cause.message : "Could not log out.",
      });
    }
  }
  async function confirmDeleteMeal() {
    if (!mealToDelete) return;
    setConfirmBusy(true);
    try {
      await mealsApi.remove(mealToDelete.id);
      setMealToDelete(null);
      if (user) await refresh(user);
      setToast({ type: "success", message: "Meal deleted." });
    } catch (cause) {
      setToast({
        type: "error",
        message:
          cause instanceof Error ? cause.message : "Could not delete meal.",
      });
    } finally {
      setConfirmBusy(false);
    }
  }
  async function confirmDeleteAccount(event: React.FormEvent) {
    event.preventDefault();
    if (!deleteAccountPassword) return;
    setConfirmBusy(true);
    try {
      await auth.remove(deleteAccountPassword);
      await clearLocalData();
      setDeleteAccountOpen(false);
      setDeleteAccountPassword("");
      setUser(null);
      setMeals([]);
      setDaily(null);
      setWeekly([]);
      setEditing(null);
      setPage("overview");
      if (window.location.pathname !== "/") {
        window.history.replaceState(null, "", "/");
      }
    } catch (cause) {
      setToast({
        type: "error",
        message:
          cause instanceof Error ? cause.message : "Could not delete account.",
      });
    } finally {
      setConfirmBusy(false);
    }
  }
  if (loading)
    return (
      <div className="boot-screen">
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
        <p>Preparing your space...</p>
      </div>
    );
  if (!user)
    return (
      <LandingPage
        onSuccess={(active) => {
          setUser(active);
          void refresh(active);
        }}
        dark={dark}
        onToggleTheme={() => setDark(!dark)}
      />
    );
  return (
    <>
      <Layout
        user={user}
        page={page}
        onPage={setPage}
        onAdd={() => setEditing("new")}
        onScanCamera={() => setEditing("camera")}
        onLogout={() => void logout()}
        dark={dark}
        onToggleTheme={() => setDark(!dark)}
        sharingBadge={pendingRequests}
      >
        <AnimatePresence>
          {toast && (
            <ToastNotice
              type={toast.type}
              message={toast.message}
              onDismiss={() => setToast(null)}
            />
          )}
          {!online && (
            <motion.div
              initial={{ x: 80, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 60, opacity: 0 }}
              transition={{ type: "spring", stiffness: 350, damping: 26 }}
              className="offline-banner"
            >
              <WifiOff size={17} /> You're offline. Showing saved data
              {lastSynced
                ? ` from ${new Date(lastSynced).toLocaleString()}`
                : ""}
              . Meal drafts stay on this device; saving needs a connection.
            </motion.div>
          )}
          {dataError && (
            <motion.div
              initial={{ x: 80, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 60, opacity: 0 }}
              transition={{ type: "spring", stiffness: 350, damping: 26 }}
              className="error-banner"
              role="alert"
            >
              {dataError}{" "}
              <button onClick={() => void refresh(user)}>Retry</button>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence mode="wait">
          <motion.div
            key={page}
            variants={pageRevealVariants}
            initial="initial"
            animate="animate"
            exit="exit"
          >
            {page === "overview" && (
              <Overview
                user={user}
                daily={daily}
                weekly={weekly}
                meals={meals}
                onAdd={() => setEditing("new")}
                onMeals={() => setPage("meals")}
                onInsights={() => setPage("insights")}
              />
            )}
            {page === "meals" && (
              <MealsPage
                meals={meals}
                timezone={user.profile.timezone}
                onAdd={() => setEditing("new")}
                onEdit={setEditing}
                onDelete={(meal) => setMealToDelete(meal)}
              />
            )}
            {page === "insights" && <Insights user={user} weekly={weekly} />}
            {page === "sharing" && (
              <SharingPage
                onDecided={() => {
                  doctorAccessApi
                    .list()
                    .then((requests) =>
                      setPendingRequests(
                        requests.filter(
                          (request) => request.status === "pending",
                        ).length,
                      ),
                    )
                    .catch(() => {});
                }}
              />
            )}
            {page === "profile" && (
              <ProfilePage
                user={user}
                onUpdate={(active) => {
                  setUser(active);
                  void refresh(active);
                }}
              />
            )}
            {page === "settings" && (
              <Settings
                user={user}
                onDelete={() => {
                  setDeleteAccountPassword("");
                  setDeleteAccountOpen(true);
                }}
                dark={dark}
                onToggleTheme={() => setDark(!dark)}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </Layout>
      <AnimatePresence>
        {editing && (
          <MealEditor
            meal={editing === "new" || editing === "camera" ? null : editing}
            initialCameraOpen={editing === "camera"}
            userId={user.id}
            timezone={user.profile.timezone}
            foods={foods}
            onClose={() => setEditing(null)}
            onFoodCreated={(food) => setFoods((current) => [...current, food])}
            onSaved={async () => {
              await refresh(user);
              setEditing(null);
            }}
          />
        )}
        {mealToDelete && (
          <GlassModal
            titleId="delete-meal-title"
            onClose={() => !confirmBusy && setMealToDelete(null)}
          >
            <div className="modal__head">
              <div>
                <span className="eyebrow">CONFIRM DELETION</span>
                <h2 id="delete-meal-title">Delete this meal?</h2>
                <p>
                  Delete{" "}
                  <strong>
                    {mealToDelete.items
                      .map((item) => item.food_name)
                      .join(", ")}
                  </strong>
                  ? This cannot be undone.
                </p>
              </div>
              <button
                type="button"
                className="icon-button"
                disabled={confirmBusy}
                onClick={() => setMealToDelete(null)}
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>
            <div className="modal__foot">
              <GlassButton
                type="button"
                variant="secondary"
                disabled={confirmBusy}
                onClick={() => setMealToDelete(null)}
              >
                Cancel
              </GlassButton>
              <GlassButton
                type="button"
                variant="danger"
                disabled={confirmBusy}
                onClick={() => void confirmDeleteMeal()}
              >
                {confirmBusy ? "Deleting..." : "Delete meal"}
              </GlassButton>
            </div>
          </GlassModal>
        )}
        {deleteAccountOpen && (
          <GlassModal
            titleId="delete-account-title"
            onClose={() => !confirmBusy && setDeleteAccountOpen(false)}
          >
            <div className="modal__head">
              <div>
                <span className="eyebrow">ACCOUNT DELETION</span>
                <h2 id="delete-account-title">Delete your account?</h2>
                <p>
                  This permanently deletes your account, meals, and meal images.
                  Enter your current password to confirm.
                </p>
              </div>
              <button
                type="button"
                className="icon-button"
                disabled={confirmBusy}
                onClick={() => setDeleteAccountOpen(false)}
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>
            <form onSubmit={confirmDeleteAccount} className="modal__body">
              <Field
                label="Current password"
                type="password"
                value={deleteAccountPassword}
                onChange={(event) =>
                  setDeleteAccountPassword(event.target.value)
                }
                required
              />
              <div className="modal__foot">
                <GlassButton
                  type="button"
                  variant="secondary"
                  disabled={confirmBusy}
                  onClick={() => setDeleteAccountOpen(false)}
                >
                  Cancel
                </GlassButton>
                <GlassButton
                  type="submit"
                  variant="danger"
                  disabled={confirmBusy || !deleteAccountPassword}
                >
                  {confirmBusy ? "Deleting..." : "Delete account permanently"}
                </GlassButton>
              </div>
            </form>
          </GlassModal>
        )}
      </AnimatePresence>
    </>
  );
}
