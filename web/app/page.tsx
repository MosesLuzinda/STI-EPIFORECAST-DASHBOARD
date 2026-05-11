function apiBaseUrl(): string {
  const u =
    process.env.API_URL?.trim() ||
    process.env.NEXT_PUBLIC_API_URL?.trim() ||
    "http://127.0.0.1:8000";
  return u.replace(/\/$/, "");
}

function dashboardUrl(): string {
  return (process.env.NEXT_PUBLIC_DASHBOARD_URL || "").trim();
}

function siteTagline(): string {
  return (
    process.env.NEXT_PUBLIC_SITE_TAGLINE?.trim() ||
    "Epidemic intelligence + forecasts"
  );
}

type HealthOk = { status: string; service: string };

async function fetchHealth(): Promise<
  | { ok: true; data: HealthOk }
  | { ok: false; detail: string }
> {
  const base = apiBaseUrl();
  try {
    const res = await fetch(`${base}/health`, {
      next: { revalidate: 15 },
    });
    if (!res.ok) {
      return { ok: false, detail: `HTTP ${res.status}` };
    }
    const data = (await res.json()) as HealthOk;
    return { ok: true, data };
  } catch {
    return { ok: false, detail: "Could not reach API (check API_URL and CORS)." };
  }
}

export default async function HomePage() {
  const health = await fetchHealth();
  const base = apiBaseUrl();
  const docsUrl = `${base}/docs`;
  const dash = dashboardUrl();
  const tagline = siteTagline();

  return (
    <main>
      <h1>Pathogen Economy Epiforecast</h1>
      <p className="muted">{tagline}</p>

      {dash ? (
        <div className="card cta">
          <h2>Live dashboard</h2>
          <p className="muted">
            The full interactive dashboard (validated signals, 3D skyline, forecasts,
            Coolio AI assistant) runs on its own host.
          </p>
          <a className="cta-btn" href={dash} rel="noreferrer" target="_blank">
            Open live dashboard →
          </a>
        </div>
      ) : (
        <div className="card">
          <h2>Live dashboard</h2>
          <p className="muted">
            Set <code>NEXT_PUBLIC_DASHBOARD_URL</code> in Vercel → Project Settings →
            Environment Variables to display a button that opens the Streamlit
            dashboard (e.g. on Streamlit Community Cloud, Render, Fly, or Hugging
            Face Spaces). Vercel cannot host the Streamlit process itself.
          </p>
        </div>
      )}

      <div className="card">
        <h2>API status</h2>
        <p>
          Target:{" "}
          <a href={base} rel="noreferrer" target="_blank">
            {base}
          </a>
        </p>
        {health.ok ? (
          <p className="status-ok">
            {health.data.status} — {health.data.service}
          </p>
        ) : (
          <p className="status-bad">{health.detail}</p>
        )}
        <p className="muted">
          The FastAPI backend (<code>backend/api_server.py</code>) must run on a
          host that supports long-lived Python processes. Set <code>API_URL</code>
          to its public URL and add this Vercel deployment to its
          <code> API_CORS_ORIGINS</code>.
        </p>
      </div>

      <div className="card">
        <h2>Reference</h2>
        <ul>
          <li>
            <a href={docsUrl} rel="noreferrer" target="_blank">
              OpenAPI docs (live when the API is reachable)
            </a>
          </li>
          <li>
            <a href="/DEVELOPER_BRIEF.md" rel="noreferrer">
              Developer brief (vendor-neutral spec)
            </a>
          </li>
        </ul>
      </div>
    </main>
  );
}
