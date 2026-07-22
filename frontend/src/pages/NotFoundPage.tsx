import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section className="empty-page" aria-labelledby="not-found-heading">
      <span className="eyebrow">404 · Route not found</span>
      <h1 id="not-found-heading">This workspace view does not exist.</h1>
      <p>The requested route is unavailable or has moved.</p>
      <Link to="/">Return to overview</Link>
    </section>
  );
}
