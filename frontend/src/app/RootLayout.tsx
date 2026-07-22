import { NavLink, Outlet } from "react-router-dom";

function ProductMark() {
  return (
    <span className="product-mark" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  );
}

export function RootLayout() {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>

      <aside className="sidebar" aria-label="Application sidebar">
        <div className="brand">
          <ProductMark />
          <div>
            <strong>AI Project Manager</strong>
            <span>Project intelligence</span>
          </div>
        </div>

        <nav className="nav-list" aria-label="Primary navigation">
          <NavLink to="/" end>
            <span aria-hidden="true">⌂</span>
            Overview
          </NavLink>
          <span className="nav-item-disabled" aria-disabled="true">
            <span aria-hidden="true">◇</span>
            Projects
          </span>
          <span className="nav-item-disabled" aria-disabled="true">
            <span aria-hidden="true">✓</span>
            My tasks
          </span>
          <span className="nav-item-disabled" aria-disabled="true">
            <span aria-hidden="true">↗</span>
            Reports
          </span>
        </nav>

        <div className="sidebar-status">
          <span className="status-dot" />
          <div>
            <strong>Foundation online</strong>
            <span>Phase 1 of 13</span>
          </div>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">Workspace</span>
            <strong>Engineering foundation</strong>
          </div>
          <div className="avatar" aria-label="Signed in user placeholder">
            AP
          </div>
        </header>

        <main id="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
