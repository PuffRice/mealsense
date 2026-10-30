import {
  BarChart3,
  CircleHelp,
  ClipboardList,
  Home,
  LogOut,
  Moon,
  Plus,
  Settings,
  Sun,
} from "lucide-react";
import { Button } from "../design/ui";
import type { User } from "../lib/types";

export type Page = "overview" | "meals" | "insights" | "settings";
const nav = [
  { id: "overview" as Page, label: "Overview", icon: Home },
  { id: "meals" as Page, label: "My meals", icon: ClipboardList },
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
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__mark">✳</span>
          <span>
            Meal<span className="brand__light">Sense</span>
          </span>
        </div>
        <div className="sidebar__label">MENU</div>
        <nav className="sidebar__nav" aria-label="Main navigation">
          {nav.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => onPage(id)}
              className={`nav-item ${page === id ? "nav-item--active" : ""}`}
            >
              <Icon size={19} strokeWidth={1.9} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar__spacer" />
        <div className="sidebar__tip">
          <span className="sidebar__tip-icon">✦</span>
          <strong>Little steps add up.</strong>
          <p>Every meal you log helps you see the bigger picture.</p>
        </div>
        <button className="nav-item nav-item--muted" onClick={onToggleTheme}>
          {dark ? <Sun size={19} /> : <Moon size={19} />}
          <span>{dark ? "Light mode" : "Dark mode"}</span>
        </button>
        <button className="nav-item nav-item--muted" onClick={onLogout}>
          <LogOut size={19} />
          <span>Log out</span>
        </button>
        <div className="sidebar__user">
          <div className="avatar">
            {(user.display_name || user.email)[0].toUpperCase()}
          </div>
          <div>
            <strong>{user.display_name || "Your account"}</strong>
            <small>{user.email}</small>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="topbar__mobile-brand">
            <span className="brand__mark">✳</span>
            <strong>MealSense</strong>
          </div>
          <span className="topbar__crumb">
            Your wellness space <span>/</span>{" "}
            <strong>{nav.find((n) => n.id === page)?.label}</strong>
          </span>
          <div className="topbar__actions">
            <button
              className="help-button"
              title="About MealSense"
              onClick={() =>
                window.alert(
                  "MealSense gives nutrition estimates for your own records. It is not medical advice.",
                )
              }
            >
              <CircleHelp size={19} />
            </button>
            <Button size="sm" icon={<Plus size={18} />} onClick={onAdd}>
              Log a meal
            </Button>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
      <nav className="mobile-nav" aria-label="Mobile navigation">
        {nav.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={page === id ? "mobile-nav__active" : ""}
            onClick={() => onPage(id)}
          >
            <Icon size={21} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
