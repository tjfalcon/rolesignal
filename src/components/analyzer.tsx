"use client";

import { FormEvent, useMemo, useState } from "react";

type AssessmentStatus = "supported" | "adjacent" | "missing" | "unknown";

interface Evidence {
  id: string;
  claim: string;
  source: string;
  source_locator: string;
}

interface Requirement {
  id: string;
  text: string;
  category: string;
  importance: string;
}

interface Assessment {
  requirement_id: string;
  status: AssessmentStatus;
  evidence_ids: string[];
  explanation: string;
  confidence: number;
}

interface FitAnalysis {
  analysis_id: string;
  requirements: Requirement[];
  assessments: Assessment[];
  primary_strengths: string[];
  ranked_gaps: string[];
  interview_prompts: string[];
  limitations: string[];
  evidence: Evidence[];
  metrics: {
    mode: string;
    latency_ms: number;
    estimated_cost_usd: number;
    evidence_coverage: number;
  };
}

const sampleJob = `Senior Applied AI Engineer
Required: 6+ years building production web applications with TypeScript and React.
Build APIs and backend services using Python and FastAPI.
Design retrieval-augmented generation systems using embeddings and vector search.
Establish evaluation, testing, observability, and cost controls for LLM features.
Lead ambiguous cross-functional initiatives and mentor other engineers.
Experience with Kubernetes is preferred.
This is a remote role in the United States.`;

const API_ORIGIN = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Analyzer() {
  const [jobText, setJobText] = useState(sampleJob);
  const [analysis, setAnalysis] = useState<FitAnalysis | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const evidence = useMemo(
    () => new Map(analysis?.evidence.map((item) => [item.id, item]) ?? []),
    [analysis],
  );
  const assessments = useMemo(
    () => new Map(analysis?.assessments.map((item) => [item.requirement_id, item]) ?? []),
    [analysis],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await fetch(`${API_ORIGIN}/v1/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_text: jobText, candidate_profile_id: "demo-thomas" }),
      });
      if (!response.ok) throw new Error(`Analysis failed (${response.status})`);
      setAnalysis(await response.json() as FitAnalysis);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="workspace" aria-label="Role analysis workspace">
      <form className="inputPanel" onSubmit={submit}>
        <div className="panelHead">
          <div><span>01</span><h2>Job description</h2></div>
          <button type="button" onClick={() => setJobText(sampleJob)}>Reset example</button>
        </div>
        <label htmlFor="job-text">Paste a role to compare with the sanitized Thomas profile</label>
        <textarea
          id="job-text"
          minLength={80}
          maxLength={30000}
          value={jobText}
          onChange={(event) => setJobText(event.target.value)}
          required
        />
        <div className="formFoot">
          <span>{jobText.length.toLocaleString()} characters</span>
          <button className="analyze" disabled={loading} type="submit">
            {loading ? "Analyzing…" : "Analyze evidence"}<b aria-hidden="true">→</b>
          </button>
        </div>
        {error && <p className="error" role="alert">{error}. Start the Python API or configure the hosted API URL.</p>}
      </form>

      <section className="results" aria-live="polite">
        <div className="panelHead resultHead">
          <div><span>02</span><h2>Evidence map</h2></div>
          {analysis && <small>{analysis.metrics.latency_ms} ms · ${analysis.metrics.estimated_cost_usd.toFixed(4)}</small>}
        </div>

        {!analysis ? (
          <div className="empty">
            <strong>Run the preloaded example.</strong>
            <p>The result will show supported, adjacent, missing, and human-confirmation items with citations.</p>
          </div>
        ) : (
          <>
            <div className="scorecard">
              <strong>{Math.round(analysis.metrics.evidence_coverage * 100)}%</strong>
              <span>supported or adjacent evidence coverage</span>
              <div className="bar"><i style={{ width: `${analysis.metrics.evidence_coverage * 100}%` }} /></div>
            </div>
            <div className="requirementList">
              {analysis.requirements.map((requirement) => {
                const assessment = assessments.get(requirement.id);
                if (!assessment) return null;
                return (
                  <article key={requirement.id} className={`requirement ${assessment.status}`}>
                    <div className="requirementMeta">
                      <span className="status">{assessment.status}</span>
                      <span>{requirement.category} · {Math.round(assessment.confidence * 100)}% confidence</span>
                    </div>
                    <h3>{requirement.text}</h3>
                    <p>{assessment.explanation}</p>
                    {assessment.evidence_ids.map((id) => {
                      const item = evidence.get(id);
                      return item ? (
                        <blockquote key={id}>
                          “{item.claim}”
                          <cite>{item.source} · {item.source_locator}</cite>
                        </blockquote>
                      ) : null;
                    })}
                  </article>
                );
              })}
            </div>
            <details>
              <summary>Limitations and interpretation notes</summary>
              <ul>{analysis.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
            </details>
          </>
        )}
      </section>
    </section>
  );
}
