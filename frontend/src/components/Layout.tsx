import {
  BarChart3,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  Home,
  LogOut,
  Moon,
  Plus,
  Settings,
  Sun,
  UserRound,
} from "lucide-react";
import { GlassButton, GlassNavbar, GlassSidebar } from "../design/ui";
import type { User } from "../lib/types";

export type Page = "overview" | "meals" | "insights" | "settings" | "profile";

const nav = [
  { id: "overview" as Page, label: "Overview", icon: Home },
  { id: "meals" as Page, label: "My Meals", icon: ClipboardList },
  { id: "insights" as Page, label: "Insights", icon: BarChart3 },
  { id: "settings" as Page, label: "Settings", icon: Settings },
];

export function Layout({
  user,
  page,
  onPage,
  onAdd,
  onLogout,
  dark,
  onToggleTheme,
  children,
}: {
  user: User;
  page: Page;
  onPage: (page: Page) => void;
  onAdd: () => void;
  onLogout: () => void;
  dark: boolean;
  onToggleTheme: () => void;
  children: React.ReactNode;
}) {
  const currentLabel =
    page === "profile"
      ? "Profile & Goals"
      : nav.find((n) => n.id === page)?.label;

  return (
    <div className="app-shell">
      <GlassSidebar aria-label="Primary sidebar">
        <div className="sidebar__top">
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
        </div>

        <div className="sidebar__label">NAVIGATION</div>
        <nav className="sidebar__nav" aria-label="Main navigation">
          {nav.map(({ id, label, icon: Icon }) => {
            const active = page === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => onPage(id)}
                aria-current={active ? "page" : undefined}
                className={`nav-item ${active ? "nav-item--active" : ""}`}
              >
                <span className="nav-item__icon">
                  <Icon size={17} strokeWidth={active ? 2.1 : 1.8} />
                </span>
                <span className="nav-item__text">{label}</span>
                {active && (
                  <span className="nav-item__indicator" aria-hidden="true" />
                )}
              </button>
            );
          })}
        </nav>

        <div className="sidebar__spacer" />

        <div className="sidebar__footer">
          <div className="sidebar__utilities">
            <button
              type="button"
              className="nav-item nav-item--muted"
              onClick={onToggleTheme}
            >
              <span className="nav-item__icon">
                {dark ? <Sun size={16} /> : <Moon size={16} />}
              </span>
              <span className="nav-item__text">
                {dark ? "Light mode" : "Dark mode"}
              </span>
              <span className="sidebar__theme-pill">
                {dark ? "Dark" : "Light"}
              </span>
            </button>
            <button
              type="button"
              className="nav-item nav-item--muted nav-item--logout"
              onClick={onLogout}
            >
              <span className="nav-item__icon">
                <LogOut size={16} />
              </span>
              <span className="nav-item__text">Log out</span>
            </button>
          </div>

          <button
            type="button"
            className={`sidebar__user ${page === "profile" ? "sidebar__user--active" : ""}`}
            onClick={() => onPage("profile")}
            title="Open Profile & goals"
          >
            <div className="avatar">
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
            <div className="sidebar__user-info">
              <strong>{user.display_name || "Your account"}</strong>
              <small>{user.email}</small>
            </div>
            <ChevronRight size={15} className="sidebar__user-chevron" />
          </button>
        </div>
      </GlassSidebar>

      <div className="main-shell">
        <GlassNavbar>
          <div className="topbar__mobile-brand">
            <div className="brand__logo-glass brand__logo-glass--sm">
              <img
                src="/MealSense_Logo.svg"
                alt="MealSense"
                className="brand__mark"
              />
            </div>
            <strong>
              Meal<span className="brand__light">Sense</span>
            </strong>
          </div>

          <nav className="topbar__crumb" aria-label="Breadcrumb">
            <span className="topbar__crumb-root">MealSense</span>
            <span className="topbar__crumb-sep" aria-hidden="true">
              /
            </span>
            <strong>{currentLabel}</strong>
          </nav>

          <div className="topbar__actions">
            <button
              type="button"
              className="topbar__icon-btn topbar__mobile-only"
              title={dark ? "Switch to light mode" : "Switch to dark mode"}
              aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
              onClick={onToggleTheme}
            >
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <button
              type="button"
              className="topbar__icon-btn help-button"
              title="About MealSense"
              aria-label="About MealSense"
              onClick={() =>
                window.alert(
                  "MealSense gives nutrition estimates for your own records. It is not medical advice.",
                )
              }
            >
              <CircleHelp size={16} />
            </button>
            <button
              type="button"
              className="topbar__icon-btn topbar__mobile-only"
              title="Log out"
              aria-label="Log out"
              onClick={onLogout}
            >
              <LogOut size={16} />
            </button>
            <GlassButton
              size="sm"
              className="topbar__cta"
              icon={<Plus size={15} strokeWidth={2.3} />}
              onClick={onAdd}
            >
              Log a meal
            </GlassButton>
          </div>
        </GlassNavbar>

        <main className="content">{children}</main>
      </div>

      <nav className="mobile-nav glass-panel" aria-label="Mobile navigation">
        {nav.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className={page === id ? "mobile-nav__active" : ""}
            onClick={() => onPage(id)}
          >
            <Icon size={19} />
            <span>{label}</span>
          </button>
        ))}
        <button
          type="button"
          className={page === "profile" ? "mobile-nav__active" : ""}
          onClick={() => onPage("profile")}
        >
          <UserRound size={19} />
          <span>Profile</span>
        </button>
      </nav>
    </div>
  );
}
