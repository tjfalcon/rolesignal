"use client";

import { FormEvent, useState } from "react";

interface Evidence {
  id: string;
  claim: string;
  skill_tags: string[];
  source: string;
  source_locator: string;
  visibility: string;
  approved: boolean;
}

interface VersionSummary {
  id: string;
  version_number: number;
  label: string;
  status: string;
  source_name: string;
  evidence_count: number;
}

interface Profile {
  id: string;
  display_name: string;
  headline: string;
  active_resume_version_id: string | null;
  versions: VersionSummary[];
}

interface Version extends VersionSummary {
  profile_id: string;
  evidence: Evidence[];
}

const API_ORIGIN = process.env.NEXT_PUBLIC_API_URL
  ?? (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");

const emptyEvidence = {
  claim: "",
  tags: "",
  source: "Sanitized public resume",
  locator: "",
};

export default function ProfileManager() {
  const [token, setToken] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [version, setVersion] = useState<Version | null>(null);
  const [label, setLabel] = useState("Applied AI resume");
  const [evidenceForm, setEvidenceForm] = useState(emptyEvidence);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function api<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_ORIGIN}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Profile-Admin-Token": token,
        ...init?.headers,
      },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: "Request failed" })) as { detail?: string };
      throw new Error(payload.detail ?? `Request failed (${response.status})`);
    }
    return await response.json() as T;
  }

  async function connect() {
    setBusy(true);
    setMessage("");
    try {
      const loaded = await api<Profile>("/v1/profiles/demo-thomas");
      setProfile(loaded);
      const selected = loaded.versions.find((item) => item.id === loaded.active_resume_version_id);
      if (selected) await loadVersion(selected.id);
      setMessage("Profile loaded. The token remains only in this browser tab's memory.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load profile");
    } finally {
      setBusy(false);
    }
  }

  async function loadVersion(id: string) {
    const loaded = await api<Version>(`/v1/resume-versions/${id}`);
    setVersion(loaded);
    setEditingId(null);
    setEvidenceForm(emptyEvidence);
  }

  async function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const created = await api<Version>("/v1/profiles/demo-thomas/resume-versions", {
        method: "POST",
        body: JSON.stringify({ label, source_name: "Manual sanitized profile", copy_active_evidence: true }),
      });
      setVersion(created);
      setProfile(await api<Profile>("/v1/profiles/demo-thomas"));
      setMessage(`Draft v${created.version_number} created from the active version.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create draft");
    } finally {
      setBusy(false);
    }
  }

  function edit(item: Evidence) {
    setEditingId(item.id);
    setEvidenceForm({
      claim: item.claim,
      tags: item.skill_tags.join(", "),
      source: item.source,
      locator: item.source_locator,
    });
  }

  async function saveEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!version) return;
    setBusy(true);
    setMessage("");
    const payload = {
      claim: evidenceForm.claim,
      skill_tags: evidenceForm.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
      source: evidenceForm.source,
      source_locator: evidenceForm.locator,
      visibility: "public",
    };
    try {
      if (editingId) {
        await api(`/v1/resume-versions/${version.id}/evidence/${editingId}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
      } else {
        await api(`/v1/resume-versions/${version.id}/evidence`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      await loadVersion(version.id);
      setMessage(editingId ? "Evidence updated." : "Evidence added to the draft.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save evidence");
    } finally {
      setBusy(false);
    }
  }

  async function toggleApproval(item: Evidence) {
    if (!version) return;
    setBusy(true);
    try {
      await api(`/v1/resume-versions/${version.id}/evidence/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({ approved: !item.approved }),
      });
      await loadVersion(version.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to update review status");
    } finally {
      setBusy(false);
    }
  }

  async function activate() {
    if (!version || !window.confirm(`Activate ${version.label}? The current version will be archived.`)) return;
    setBusy(true);
    try {
      const updated = await api<Profile>(`/v1/resume-versions/${version.id}/activate`, { method: "POST" });
      setProfile(updated);
      await loadVersion(version.id);
      setMessage("Version activated. New analyses now use this evidence set.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to activate version");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="profileManager" aria-labelledby="profile-manager-title">
      <div className="panelHead">
        <div><span>03</span><h2 id="profile-manager-title">Sanitized profile versions</h2></div>
        <small>Administrator workspace</small>
      </div>
      <p className="profileIntro">
        Create a draft from the active evidence set, review every claim, then activate it atomically.
        Use sanitized information only; private résumé uploads are not enabled yet.
      </p>

      {!profile ? (
        <div className="adminConnect">
          <label htmlFor="admin-token">Profile administrator token</label>
          <input
            id="admin-token"
            type="password"
            autoComplete="off"
            value={token}
            onChange={(event) => setToken(event.target.value)}
          />
          <button className="analyze" type="button" disabled={busy || !token} onClick={connect}>Open editor</button>
        </div>
      ) : (
        <div className="profileGrid">
          <aside className="versionRail">
            <strong>{profile.display_name}</strong>
            <p>{profile.headline}</p>
            <form onSubmit={createDraft}>
              <label htmlFor="version-label">New version label</label>
              <input id="version-label" value={label} onChange={(event) => setLabel(event.target.value)} required />
              <button type="submit" disabled={busy}>Clone active version</button>
            </form>
            <div className="versionList">
              {profile.versions.map((item) => (
                <button
                  key={item.id}
                  className={version?.id === item.id ? "selected" : ""}
                  type="button"
                  onClick={() => loadVersion(item.id)}
                >
                  <b>v{item.version_number} · {item.label}</b>
                  <span>{item.status} · {item.evidence_count} claims</span>
                </button>
              ))}
            </div>
          </aside>

          <div className="evidenceEditor">
            {version && (
              <>
                <div className="editorHead">
                  <div><strong>v{version.version_number} · {version.label}</strong><span>{version.status}</span></div>
                  {version.status === "draft" && <button type="button" disabled={busy} onClick={activate}>Activate version</button>}
                </div>
                {version.status === "draft" && (
                  <form className="evidenceForm" onSubmit={saveEvidence}>
                    <label>Evidence claim<textarea value={evidenceForm.claim} onChange={(event) => setEvidenceForm({ ...evidenceForm, claim: event.target.value })} required minLength={10} /></label>
                    <label>Skill tags, comma separated<input value={evidenceForm.tags} onChange={(event) => setEvidenceForm({ ...evidenceForm, tags: event.target.value })} required /></label>
                    <div>
                      <label>Source<input value={evidenceForm.source} onChange={(event) => setEvidenceForm({ ...evidenceForm, source: event.target.value })} required /></label>
                      <label>Source locator<input value={evidenceForm.locator} onChange={(event) => setEvidenceForm({ ...evidenceForm, locator: event.target.value })} required /></label>
                    </div>
                    <button type="submit" disabled={busy}>{editingId ? "Save evidence" : "Add evidence"}</button>
                    {editingId && <button type="button" onClick={() => { setEditingId(null); setEvidenceForm(emptyEvidence); }}>Cancel edit</button>}
                  </form>
                )}
                <div className="managedEvidence">
                  {version.evidence.map((item) => (
                    <article key={item.id} className={item.approved ? "" : "unapproved"}>
                      <p>{item.claim}</p>
                      <small>{item.skill_tags.join(" · ")}</small>
                      <cite>{item.source} · {item.source_locator}</cite>
                      {version.status === "draft" && <div><button type="button" onClick={() => edit(item)}>Edit</button><button type="button" onClick={() => toggleApproval(item)}>{item.approved ? "Exclude" : "Approve"}</button></div>}
                    </article>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}
      {message && <p className="adminMessage" role="status">{message}</p>}
    </section>
  );
}
