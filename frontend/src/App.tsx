import { useCallback, useEffect, useState } from "react";
import { WifiOff } from "lucide-react";
import { Layout, type Page } from "./components/Layout";
import { AuthPage } from "./features/auth/AuthPage";
import { Overview } from "./features/overview/Overview";
import { MealsPage } from "./features/meals/MealsPage";
import { MealEditor } from "./features/meals/MealEditor";
import { Insights } from "./features/insights/Insights";
import { ProfilePage } from "./features/profile/ProfilePage";
import { Settings } from "./features/settings/Settings";
import { auth, foodsApi, mealsApi } from "./lib/api";
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
  const [editing, setEditing] = useState<Meal | null | "new">(null);
  const [dark, setDark] = useState(
    () => localStorage.getItem("mealsense-theme") === "dark",
  );
  const [bgVersion, setBgVersion] = useState(() => Date.now());
  const [online, setOnline] = useState(navigator.onLine);
  const [dataError, setDataError] = useState("");
  const [lastSynced, setLastSynced] = useState("");
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("mealsense-theme", dark ? "dark" : "light");
  }, [dark]);
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty(
      "--app-bg-light",
      `url("/bg-light.svg?v=${bgVersion}"), url("/bg.svg?v=${bgVersion}")`,
    );
    root.style.setProperty(
      "--app-bg-dark",
      `url("/bg-dark.svg?v=${bgVersion}"), url("/bg.svg?v=${bgVersion}")`,
    );
  }, [bgVersion]);
  useEffect(() => {
    if (import.meta.hot) {
      const handleSvgUpdate = (payload: { timestamp?: number }) => {
        setBgVersion(payload?.timestamp || Date.now());
      };
      import.meta.hot.on("public-svg-updated", handleSvgUpdate);
      return () => {
        import.meta.hot?.off("public-svg-updated", handleSvgUpdate);
      };
    }
  }, []);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  const refresh = useCallback(async (activeUser: User) => {
    try {
      const [nextMeals, nextFoods, nextDaily, nextWeekly] = await Promise.all([
        mealsApi.list(),
        foodsApi.list(),
        mealsApi.daily(dateInZone(activeUser.profile.timezone)),
        mealsApi.weekly(),
      ]);
      setMeals(nextMeals);
      setFoods(nextFoods);
      setDaily(nextDaily);
      setWeekly(nextWeekly);
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
    } catch (cause) {
      setDataError(
        cause instanceof Error ? cause.message : "Could not load your data.",
      );
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
  async function logout() {
    if (!online) {
      window.alert("Connect to the internet to securely log out.");
      return;
    }
    try {
      await auth.logout();
      await clearLocalData();
      setUser(null);
      setMeals([]);
      setDaily(null);
      setWeekly([]);
      setPage("overview");
    } catch (cause) {
      window.alert(
        cause instanceof Error ? cause.message : "Could not log out.",
      );
    }
  }
  async function deleteMeal(meal: Meal) {
    if (
      !window.confirm(
        `Delete ${meal.items.map((item) => item.food_name).join(", ")}? This cannot be undone.`,
      )
    )
      return;
    try {
      await mealsApi.remove(meal.id);
      if (user) await refresh(user);
    } catch (cause) {
      window.alert(
        cause instanceof Error ? cause.message : "Could not delete meal.",
      );
    }
  }
  async function deleteAccount() {
    if (
      !window.confirm(
        "Delete your account, meals, and meal images permanently?",
      )
    )
      return;
    const password = window.prompt(
      "Enter your current password to confirm account deletion:",
    );
    if (!password) return;
    try {
      await auth.remove(password);
      await clearLocalData();
      setUser(null);
      setMeals([]);
      setPage("overview");
    } catch (cause) {
      window.alert(
        cause instanceof Error ? cause.message : "Could not delete account.",
      );
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
      <AuthPage
        onSuccess={(active) => {
          setUser(active);
          void refresh(active);
        }}
      />
    );
  return (
    <>
      <Layout
        user={user}
        page={page}
        onPage={setPage}
        onAdd={() => setEditing("new")}
        onLogout={() => void logout()}
        dark={dark}
        onToggleTheme={() => setDark(!dark)}
      >
        {!online && (
          <div className="offline-banner">
            <WifiOff size={17} /> You're offline. Showing saved data
            {lastSynced ? ` from ${new Date(lastSynced).toLocaleString()}` : ""}
            . Meal drafts stay on this device; saving needs a connection.
          </div>
        )}
        {dataError && (
          <div className="error-banner" role="alert">
            {dataError}{" "}
            <button onClick={() => void refresh(user)}>Retry</button>
          </div>
        )}
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
            onDelete={(meal) => void deleteMeal(meal)}
          />
        )}
        {page === "insights" && <Insights user={user} weekly={weekly} />}
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
            onDelete={() => void deleteAccount()}
            dark={dark}
            onToggleTheme={() => setDark(!dark)}
          />
        )}
      </Layout>
      {editing && (
        <MealEditor
          meal={editing === "new" ? null : editing}
          userId={user.id}
          foods={foods}
          onClose={() => setEditing(null)}
          onFoodCreated={(food) => setFoods((current) => [...current, food])}
          onSaved={async () => {
            await refresh(user);
            setEditing(null);
          }}
        />
      )}
    </>
  );
}
