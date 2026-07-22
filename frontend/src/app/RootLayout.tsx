import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { logout } from "../api/auth";
import type { UserView } from "../api/types";

function ProductMark() {
  return (
    <span className="product-mark" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  );
}

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
          <ProductMark />
          <div><strong>AI Project Manager</strong><span>Project intelligence</span></div>
        </div>
        <nav className="nav-list" aria-label="Primary navigation">
          <NavLink to="/projects" end><span className="nav-glyph" aria-hidden="true">P</span>Projects</NavLink>
          <NavLink to="/projects/new"><span className="nav-glyph" aria-hidden="true">+</span>New project</NavLink>
          <span className="nav-item-disabled" aria-disabled="true"><span className="nav-glyph" aria-hidden="true">T</span>My tasks</span>
          <span className="nav-item-disabled" aria-disabled="true"><span className="nav-glyph" aria-hidden="true">R</span>Reports</span>
        </nav>
        <div className="sidebar-status">
          <span className="status-dot" />
          <div><strong>Identity secured</strong><span>Phase 2 of 13</span></div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div><span className="eyebrow">Owner workspace</span><strong>{user.email}</strong></div>
          <div className="account-actions">
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
