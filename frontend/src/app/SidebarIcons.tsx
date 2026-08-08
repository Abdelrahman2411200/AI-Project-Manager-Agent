type SidebarIconName = "projects" | "new-project" | "tasks" | "reports";

interface SidebarIconProps {
  name: SidebarIconName;
}

export function ProductLogo() {
  return (
    <span className="product-mark" aria-hidden="true" data-icon="product-logo">
      <svg viewBox="0 0 24 24" focusable="false">
        <path d="M7.25 6.75h3.25a3.5 3.5 0 0 1 3.5 3.5v3.5a3.5 3.5 0 0 0 3.5 3.5" />
        <path d="M7.25 17.25h3.25a3.5 3.5 0 0 0 3.5-3.5" />
        <circle cx="5.25" cy="6.75" r="2" />
        <circle cx="5.25" cy="17.25" r="2" />
        <circle cx="18.75" cy="17.25" r="2" />
        <path className="product-spark" d="M18 3.25v4.5M15.75 5.5h4.5" />
      </svg>
    </span>
  );
}

export function SidebarIcon({ name }: SidebarIconProps) {
  return (
    <span className="nav-glyph" aria-hidden="true">
      <svg viewBox="0 0 24 24" focusable="false" data-icon={name}>
        {name === "projects" ? (
          <>
            <path d="M3.5 7.5h6l2 2H20.5v9.25a1.75 1.75 0 0 1-1.75 1.75H5.25a1.75 1.75 0 0 1-1.75-1.75z" />
            <path d="M3.5 7.5V5.25A1.75 1.75 0 0 1 5.25 3.5h3.5l2 2h8a1.75 1.75 0 0 1 1.75 1.75V9.5" />
          </>
        ) : null}
        {name === "new-project" ? (
          <>
            <path d="M6 3.5h8l4 4v13H6z" />
            <path d="M14 3.5v4h4M12 11v6M9 14h6" />
          </>
        ) : null}
        {name === "tasks" ? (
          <>
            <rect x="3.5" y="3.5" width="17" height="17" rx="3" />
            <path d="m7.5 12 3 3 6-7" />
          </>
        ) : null}
        {name === "reports" ? (
          <>
            <path d="M4 20.5h16" />
            <rect x="5" y="11.5" width="3" height="6" rx="1" />
            <rect x="10.5" y="7.5" width="3" height="10" rx="1" />
            <rect x="16" y="3.5" width="3" height="14" rx="1" />
          </>
        ) : null}
      </svg>
    </span>
  );
}
