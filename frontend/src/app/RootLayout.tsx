import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { logout } from "../api/auth";
import type { UserView } from "../api/types";
import { ThemeToggle } from "../features/theme/ThemeToggle";
import { ProductLogo, SidebarIcon } from "./SidebarIcons";

interface RootLayoutProps {
  user: UserView;
}

function initials(email: string): string {
  return email.slice(0, 2).toUpperCase();
}

export function RootLayout({ user }: RootLayoutProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: () => {
      queryClient.clear();
      void navigate("/sign-in", { replace: true });
    },
  });

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <aside className="sidebar" aria-label="Application sidebar">
        <div className="brand">
          <ProductLogo />
          <div><strong>AI Project Manager</strong><span>Project intelligence</span></div>
        </div>
        <nav className="nav-list" aria-label="Primary navigation">
          <NavLink to="/projects" end><SidebarIcon name="projects" />Projects</NavLink>
          <NavLink to="/projects/new"><SidebarIcon name="new-project" />New project</NavLink>
          <NavLink to="/my-tasks"><SidebarIcon name="tasks" />My tasks</NavLink>
          <NavLink to="/reports" end><SidebarIcon name="reports" />Reports</NavLink>
        </nav>
        <div className="sidebar-status">
          <span className="status-dot" />
          <div><strong>Full-version experience</strong><span>Phase 12 of 13</span></div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div><span className="eyebrow">Owner workspace</span><strong>{user.email}</strong></div>
          <div className="account-actions">
            <ThemeToggle />
            <div className="avatar" aria-label={`Signed in as ${user.email}`}>{initials(user.email)}</div>
            <button type="button" className="text-button" disabled={logoutMutation.isPending} onClick={() => logoutMutation.mutate()}>
              {logoutMutation.isPending ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </header>
        <main id="main-content"><Outlet /></main>
      </div>
    </div>
  );
}
