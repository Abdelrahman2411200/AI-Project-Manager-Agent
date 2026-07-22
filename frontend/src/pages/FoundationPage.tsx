const foundations = [
  {
    label: "API",
    title: "FastAPI service",
    description: "Versioned routing, typed configuration, request IDs, and health contracts.",
  },
  {
    label: "WEB",
    title: "React workspace",
    description: "Accessible, responsive shell guided by the approved Stitch design language.",
  },
  {
    label: "OPS",
    title: "Container runtime",
    description: "API, worker, frontend, and PostgreSQL services orchestrated with Compose.",
  },
];

export function FoundationPage() {
  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div>
          <span className="phase-pill">Phase 1 · Repository foundation</span>
          <h1>The engineering foundation is ready.</h1>
          <p>
            A calm, structured workspace for turning project intent into approved plans and
            measurable execution.
          </p>
        </div>
        <div className="hero-orbit" aria-hidden="true">
          <span className="orbit orbit-one" />
          <span className="orbit orbit-two" />
          <span className="orbit-core">AI</span>
        </div>
      </section>

      <section aria-labelledby="foundation-heading">
        <div className="section-heading">
          <div>
            <span className="eyebrow">System status</span>
            <h2 id="foundation-heading">Foundation capabilities</h2>
          </div>
          <span className="status-badge">3 services defined</span>
        </div>

        <div className="card-grid">
          {foundations.map((foundation) => (
            <article className="capability-card" key={foundation.label}>
              <span className="card-icon">{foundation.label}</span>
              <h3>{foundation.title}</h3>
              <p>{foundation.description}</p>
              <span className="card-state">
                <span className="status-dot" /> Configured
              </span>
            </article>
          ))}
        </div>
      </section>

      <section className="next-panel" aria-labelledby="next-heading">
        <div>
          <span className="eyebrow">Next milestone</span>
          <h2 id="next-heading">Identity and persistence</h2>
          <p>User sessions, project ownership, core entities, migrations, and audit events.</p>
        </div>
        <span className="phase-number" aria-label="Phase 2">
          02
        </span>
      </section>
    </div>
  );
}
