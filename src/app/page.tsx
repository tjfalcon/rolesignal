import Analyzer from "@/components/analyzer";

export default function Home() {
  return (
    <main>
      <header className="topbar">
        <a className="brand" href="/">RoleSignal<span>/</span></a>
        <div className="toplinks">
          <span className="mode"><i /> deterministic demo</span>
          <a href="https://github.com/tjfalcon/rolesignal">Source</a>
        </div>
      </header>

      <section className="intro">
        <p className="eyebrow">Evidence-grounded job analysis</p>
        <h1>Know what you can prove.<br /><em>See what to build next.</em></h1>
        <p>
          RoleSignal turns a job description into a requirement-by-requirement evidence map.
          It cites every positive conclusion and keeps adjacent or missing experience honest.
        </p>
      </section>

      <Analyzer />

      <footer>
        <p>No résumé uploads or job descriptions are retained in this public demo.</p>
        <p>Built by <a href="https://github.com/tjfalcon">Thomas Falcon</a>.</p>
      </footer>
    </main>
  );
}
