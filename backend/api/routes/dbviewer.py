"""
DB Viewer — HTML interface for inspecting the PostgreSQL database.
Accessible at GET /db

Shows:
  - All jobs (id, status, filename, created_at, progress, error)
  - All graph snapshots (job_id, nodes, edges, fallacies, fact-checks, speakers)
  - Full snapshot JSON viewer (click any row)
  - Direct link to load a snapshot in the frontend
"""

import json
import logging
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from db.database import list_jobs, get_all_snapshots_meta, get_snapshot, get_job

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dbviewer"])


@router.get("/db", response_class=HTMLResponse)
async def db_viewer():
    """Render the full DB viewer as a standalone HTML page."""
    try:
        jobs = list_jobs()
        snapshots = get_all_snapshots_meta()
    except Exception as e:
        return HTMLResponse(content=_error_page(str(e)), status_code=500)

    return HTMLResponse(content=_render_page(jobs, snapshots))


@router.get("/db/snapshot/{job_id}", response_class=HTMLResponse)
async def db_snapshot_detail(job_id: str):
    """Show the full JSON of a snapshot for a given job."""
    try:
        snap = get_snapshot(job_id)
        job = get_job(job_id)
    except Exception as e:
        return HTMLResponse(content=_error_page(str(e)), status_code=500)

    if not snap:
        return HTMLResponse(content=_error_page(f"No snapshot for job {job_id}"), status_code=404)

    return HTMLResponse(content=_render_snapshot_detail(job_id, snap, job))


# ─── HTML Rendering ──────────────────────────────────────────────────────────

def _status_badge(status: str) -> str:
    colors = {
        "complete":    "background:#166534;color:#86efac;",
        "processing":  "background:#1e3a5f;color:#93c5fd;",
        "transcribing":"background:#1e3a5f;color:#93c5fd;",
        "extracting":  "background:#1e3a5f;color:#93c5fd;",
        "error":       "background:#7f1d1d;color:#fca5a5;",
    }
    style = colors.get(status, "background:#374151;color:#9ca3af;")
    return f'<span style="padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600;{style}">{status}</span>'


def _render_page(jobs: list, snapshots: list) -> str:
    # Build jobs table rows
    job_rows = ""
    for j in jobs:
        _ca = j.get("created_at") or ""
        if hasattr(_ca, 'isoformat'):
            _ca = _ca.isoformat()
        created = str(_ca)[:19].replace("T", " ")
        filename = j.get("audio_filename") or "—"
        duration = f"{j.get('duration_s', 0) or 0:.0f}s" if j.get("duration_s") else "—"
        progress = f"{(j.get('progress') or 0) * 100:.0f}%"
        error = f'<span style="color:#fca5a5;font-size:11px">{j.get("error","")[:60]}</span>' if j.get("error") else "—"
        nodes = j.get("num_nodes") or "—"
        edges = j.get("num_edges") or "—"
        fallacies = j.get("num_fallacies") or "—"
        speakers = ", ".join(j.get("speakers") or []) or "—"

        load_btn = ""
        if j.get("status") == "complete":
            load_btn = (
                f'<a href="http://localhost:5173?job={j["id"]}" target="_blank" '
                f'style="color:#60a5fa;text-decoration:underline;margin-right:8px">🔗 Frontend</a>'
                f'<a href="/db/snapshot/{j["id"]}" '
                f'style="color:#a78bfa;text-decoration:underline">🔍 JSON</a>'
            )

        job_rows += f"""
        <tr>
          <td style="font-family:monospace;font-size:11px;color:#9ca3af">{j['id'][:8]}…</td>
          <td>{_status_badge(j.get('status','?'))}</td>
          <td style="color:#e5e7eb">{filename}</td>
          <td style="color:#9ca3af">{created}</td>
          <td style="color:#9ca3af">{duration}</td>
          <td style="color:#9ca3af">{progress}</td>
          <td style="color:#86efac">{nodes}</td>
          <td style="color:#86efac">{edges}</td>
          <td style="color:#fbbf24">{fallacies}</td>
          <td style="color:#9ca3af;font-size:11px">{speakers[:40]}</td>
          <td>{error}</td>
          <td>{load_btn}</td>
        </tr>"""

    # Build snapshots table rows
    snap_rows = ""
    for s in snapshots:
        _sca = s.get("created_at") or ""
        if hasattr(_sca, 'isoformat'):
            _sca = _sca.isoformat()
        created = str(_sca)[:19].replace("T", " ")
        speakers = ", ".join(s.get("speakers") or []) or "—"
        snap_rows += f"""
        <tr>
          <td style="font-family:monospace;font-size:11px;color:#9ca3af">{s.get('snapshot_id','')[:8]}…</td>
          <td style="font-family:monospace;font-size:11px;color:#9ca3af">{s.get('job_id','')[:8]}…</td>
          <td style="color:#9ca3af">{created}</td>
          <td style="color:#86efac">{s.get('num_nodes',0)}</td>
          <td style="color:#86efac">{s.get('num_edges',0)}</td>
          <td style="color:#fbbf24">{s.get('num_fallacies',0)}</td>
          <td style="color:#60a5fa">{s.get('num_factchecks',0)}</td>
          <td style="color:#9ca3af;font-size:11px">{speakers[:50]}</td>
          <td style="color:#e5e7eb">{s.get('audio_filename','—')}</td>
          <td>
            <a href="/db/snapshot/{s.get('job_id','')}"
               style="color:#a78bfa;text-decoration:underline">🔍 View JSON</a>
          </td>
        </tr>"""

    total_jobs = len(jobs)
    total_snaps = len(snapshots)
    complete_jobs = sum(1 for j in jobs if j.get("status") == "complete")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DebateGraph — DB Viewer</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #0f172a; color: #e5e7eb; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 24px; }}
    h1 {{ font-size: 22px; font-weight: 700; color: #f8fafc; margin-bottom: 4px; }}
    h1 span {{ color: #60a5fa; }}
    .subtitle {{ color: #6b7280; font-size: 13px; margin-bottom: 24px; }}
    .stats {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
    .stat {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 12px 20px; }}
    .stat-value {{ font-size: 28px; font-weight: 700; color: #60a5fa; }}
    .stat-label {{ font-size: 12px; color: #6b7280; margin-top: 2px; }}
    h2 {{ font-size: 15px; font-weight: 600; color: #cbd5e1; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #1e293b; }}
    .section {{ margin-bottom: 32px; }}
    .table-wrap {{ overflow-x: auto; border-radius: 8px; border: 1px solid #1e293b; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    thead tr {{ background: #1e293b; }}
    th {{ padding: 10px 12px; text-align: left; color: #94a3b8; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; white-space: nowrap; }}
    tbody tr {{ border-top: 1px solid #1e293b; transition: background 0.1s; }}
    tbody tr:hover {{ background: #1e293b55; }}
    td {{ padding: 10px 12px; vertical-align: middle; }}
    .empty {{ text-align: center; padding: 32px; color: #4b5563; font-size: 14px; }}
    .refresh {{ float: right; background: #1e293b; border: 1px solid #334155; color: #94a3b8; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; text-decoration: none; }}
    .refresh:hover {{ background: #334155; color: #e5e7eb; }}
  </style>
</head>
<body>
  <h1><span>Debate</span>Graph — DB Viewer</h1>
  <p class="subtitle">PostgreSQL live view · Auto-refresh: <a href="/db" class="refresh">↻ Refresh</a></p>

  <div class="stats">
    <div class="stat"><div class="stat-value">{total_jobs}</div><div class="stat-label">Total Jobs</div></div>
    <div class="stat"><div class="stat-value">{complete_jobs}</div><div class="stat-label">Completed</div></div>
    <div class="stat"><div class="stat-value">{total_snaps}</div><div class="stat-label">Snapshots</div></div>
    <div class="stat"><div class="stat-value">{sum(s.get('num_nodes',0) for s in snapshots)}</div><div class="stat-label">Total Nodes</div></div>
    <div class="stat"><div class="stat-value">{sum(s.get('num_fallacies',0) for s in snapshots)}</div><div class="stat-label">Total Fallacies</div></div>
  </div>

  <div class="section">
    <h2>📋 Jobs Table ({total_jobs} rows)</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>ID</th><th>Status</th><th>Filename</th><th>Created</th>
            <th>Duration</th><th>Progress</th><th>Nodes</th><th>Edges</th>
            <th>Fallacies</th><th>Speakers</th><th>Error</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {job_rows if job_rows else '<tr><td colspan="12" class="empty">No jobs yet</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>

  <div class="section">
    <h2>📊 Graph Snapshots ({total_snaps} rows)</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Snapshot ID</th><th>Job ID</th><th>Created</th>
            <th>Nodes</th><th>Edges</th><th>Fallacies</th><th>Fact-checks</th>
            <th>Speakers</th><th>File</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {snap_rows if snap_rows else '<tr><td colspan="10" class="empty">No snapshots yet</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>

  <script>
    // Auto-refresh every 10s if any job is processing
    const statuses = {json.dumps([j.get('status') for j in jobs])};
    if (statuses.some(s => ['processing','transcribing','extracting'].includes(s))) {{
      setTimeout(() => location.reload(), 10000);
      document.querySelector('.subtitle').innerHTML += ' <span style="color:#fbbf24;font-size:12px">⟳ Auto-refreshing (job in progress)…</span>';
    }}
  </script>
</body>
</html>"""


def _render_snapshot_detail(job_id: str, snap: dict, job: dict) -> str:
    snapshot_json = snap.get("snapshot_json", {})
    transcription_json = snap.get("transcription_json", {})

    nodes = snapshot_json.get("nodes", [])
    edges = snapshot_json.get("edges", [])
    rigor = snapshot_json.get("rigor_scores", [])
    fallacies_all = [f for n in nodes for f in n.get("fallacies", [])]
    factchecked = [n for n in nodes if n.get("factcheck_verdict") not in (None, "pending")]

    # Build nodes table
    node_rows = ""
    for n in nodes:
        fc = n.get("factcheck_verdict", "pending")
        fc_colors = {"supported": "#86efac", "refuted": "#fca5a5", "partially_true": "#fbbf24", "unverifiable": "#9ca3af", "pending": "#4b5563"}
        fc_color = fc_colors.get(fc, "#9ca3af")
        fallacy_count = len(n.get("fallacies", []))
        fallacy_types = ", ".join(set(f.get("fallacy_type","") for f in n.get("fallacies",[]))) or "—"
        fc_explanation = ""
        if n.get("factcheck"):
            fc_explanation = (n["factcheck"].get("explanation") or "")[:80]
        node_rows += f"""
        <tr>
          <td style="font-family:monospace;font-size:11px;color:#9ca3af">{n['id']}</td>
          <td style="color:#9ca3af;font-size:11px">{n.get('speaker','')}</td>
          <td style="color:#94a3b8;font-size:11px">{n.get('claim_type','')}</td>
          <td style="color:#e5e7eb;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{n.get('label','').replace('"','&quot;')}">{n.get('label','')[:80]}</td>
          <td style="color:#9ca3af;font-size:11px">{n.get('timestamp_start',0):.1f}s</td>
          <td style="color:{'#86efac' if n.get('is_factual') else '#4b5563'}">{('✓' if n.get('is_factual') else '—')}</td>
          <td style="color:{fc_color};font-size:11px">{fc}</td>
          <td style="color:#9ca3af;font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis" title="{fc_explanation}">{fc_explanation[:60] if fc_explanation else '—'}</td>
          <td style="color:{'#fca5a5' if fallacy_count > 0 else '#4b5563'}">{fallacy_count if fallacy_count else '—'}</td>
          <td style="color:#fbbf24;font-size:11px">{fallacy_types[:40]}</td>
          <td style="color:#9ca3af;font-size:11px">{n.get('confidence',0):.2f}</td>
        </tr>"""

    # Build edges table
    edge_rows = ""
    edge_colors = {"support": "#86efac", "attack": "#fca5a5", "undercut": "#c084fc", "implication": "#60a5fa", "reformulation": "#9ca3af"}
    for e in edges:
        color = edge_colors.get(e.get("relation_type",""), "#9ca3af")
        edge_rows += f"""
        <tr>
          <td style="font-family:monospace;font-size:11px;color:#9ca3af">{e.get('source','')}</td>
          <td style="font-family:monospace;font-size:11px;color:#9ca3af">{e.get('target','')}</td>
          <td style="color:{color};font-weight:600">{e.get('relation_type','')}</td>
          <td style="color:#9ca3af">{e.get('confidence',0):.2f}</td>
        </tr>"""

    # Rigor scores
    rigor_rows = ""
    for r in rigor:
        score_pct = int(r.get("overall_score", 0) * 100)
        color = "#86efac" if score_pct >= 70 else "#fbbf24" if score_pct >= 40 else "#fca5a5"
        rigor_rows += f"""
        <tr>
          <td style="color:#e5e7eb">{r.get('speaker','')}</td>
          <td style="color:{color};font-weight:700;font-size:16px">{score_pct}%</td>
          <td style="color:#9ca3af">{int(r.get('supported_ratio',0)*100)}%</td>
          <td style="color:{'#fca5a5' if r.get('fallacy_count',0) > 0 else '#9ca3af'}">{r.get('fallacy_count',0)}</td>
          <td style="color:#9ca3af">{int(r.get('factcheck_positive_rate',0)*100)}%</td>
          <td style="color:#9ca3af">{int(r.get('internal_consistency',0)*100)}%</td>
          <td style="color:#9ca3af">{int(r.get('direct_response_rate',0)*100)}%</td>
        </tr>"""

    # Fallacies table
    fallacy_rows = ""
    for f in fallacies_all:
        sev = f.get("severity", 0)
        sev_color = "#fca5a5" if sev >= 0.7 else "#fbbf24" if sev >= 0.4 else "#fde68a"
        fallacy_rows += f"""
        <tr>
          <td style="font-family:monospace;font-size:11px;color:#9ca3af">{f.get('claim_id','')}</td>
          <td style="color:#fbbf24;font-weight:600">{f.get('fallacy_type','').replace('_',' ').title()}</td>
          <td style="color:{sev_color}">{sev:.2f}</td>
          <td style="color:#9ca3af;font-size:12px;max-width:300px">{f.get('explanation','')[:100]}</td>
          <td style="color:#93c5fd;font-size:12px;font-style:italic;max-width:250px">{f.get('socratic_question','')[:80]}</td>
        </tr>"""

    filename = (job or {}).get("audio_filename", "unknown")
    _created_raw = (job or {}).get("created_at") or snap.get("job_created_at", "")
    # Handle both datetime objects and ISO strings
    if hasattr(_created_raw, 'isoformat'):
        _created_raw = _created_raw.isoformat()
    created = str(_created_raw)[:19].replace("T", " ")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Snapshot — {job_id[:8]}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #0f172a; color: #e5e7eb; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 24px; }}
    h1 {{ font-size: 20px; font-weight: 700; color: #f8fafc; margin-bottom: 4px; }}
    h1 span {{ color: #60a5fa; }}
    .back {{ color: #60a5fa; text-decoration: none; font-size: 13px; display: inline-block; margin-bottom: 16px; }}
    .back:hover {{ text-decoration: underline; }}
    .meta {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
    .meta-item {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 10px 16px; }}
    .meta-value {{ font-size: 22px; font-weight: 700; color: #60a5fa; }}
    .meta-label {{ font-size: 11px; color: #6b7280; margin-top: 2px; }}
    h2 {{ font-size: 14px; font-weight: 600; color: #cbd5e1; margin: 24px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #1e293b; }}
    .table-wrap {{ overflow-x: auto; border-radius: 8px; border: 1px solid #1e293b; margin-bottom: 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    thead tr {{ background: #1e293b; }}
    th {{ padding: 8px 10px; text-align: left; color: #94a3b8; font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; white-space: nowrap; }}
    tbody tr {{ border-top: 1px solid #1e293b; }}
    tbody tr:hover {{ background: #1e293b55; }}
    td {{ padding: 8px 10px; vertical-align: middle; }}
    .json-toggle {{ background: #1e293b; border: 1px solid #334155; color: #94a3b8; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 12px; margin-top: 8px; }}
    .json-block {{ display: none; background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; margin-top: 8px; overflow-x: auto; font-family: monospace; font-size: 11px; color: #94a3b8; white-space: pre; max-height: 400px; overflow-y: auto; }}
  </style>
</head>
<body>
  <a href="/db" class="back">← Back to DB Viewer</a>
  <h1><span>Debate</span>Graph — Snapshot Detail</h1>
  <p style="color:#6b7280;font-size:13px;margin-bottom:16px">Job: <code style="color:#9ca3af">{job_id}</code> · File: <strong style="color:#e5e7eb">{filename}</strong> · Analyzed: {created}</p>

  <div class="meta">
    <div class="meta-item"><div class="meta-value">{len(nodes)}</div><div class="meta-label">Nodes (Claims)</div></div>
    <div class="meta-item"><div class="meta-value">{len(edges)}</div><div class="meta-label">Edges (Relations)</div></div>
    <div class="meta-item"><div class="meta-value">{len(fallacies_all)}</div><div class="meta-label">Fallacies</div></div>
    <div class="meta-item"><div class="meta-value">{len(factchecked)}</div><div class="meta-label">Fact-checked</div></div>
    <div class="meta-item"><div class="meta-value">{len(rigor)}</div><div class="meta-label">Speakers</div></div>
  </div>

  <a href="http://localhost:5173/?job={job_id}" target="_blank"
     style="display:inline-block;background:#1d4ed8;color:#fff;padding:8px 18px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600;margin-bottom:24px">
    🔗 Open in Frontend
  </a>

  <h2>🏆 Rigor Scores</h2>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Speaker</th><th>Overall</th><th>Supported</th><th>Fallacies</th><th>Fact-check+</th><th>Consistency</th><th>Response Rate</th></tr></thead>
      <tbody>{rigor_rows if rigor_rows else '<tr><td colspan="7" style="text-align:center;padding:20px;color:#4b5563">No rigor scores</td></tr>'}</tbody>
    </table>
  </div>

  <h2>🔴 Fallacies ({len(fallacies_all)})</h2>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Claim ID</th><th>Type</th><th>Severity</th><th>Explanation</th><th>Socratic Question</th></tr></thead>
      <tbody>{fallacy_rows if fallacy_rows else '<tr><td colspan="5" style="text-align:center;padding:20px;color:#4b5563">No fallacies</td></tr>'}</tbody>
    </table>
  </div>

  <h2>🔵 Nodes / Claims ({len(nodes)})</h2>
  <div class="table-wrap">
    <table>
      <thead><tr><th>ID</th><th>Speaker</th><th>Type</th><th>Text</th><th>Time</th><th>Factual</th><th>Verdict</th><th>FC Explanation</th><th>Fallacies</th><th>Fallacy Types</th><th>Conf.</th></tr></thead>
      <tbody>{node_rows if node_rows else '<tr><td colspan="11" style="text-align:center;padding:20px;color:#4b5563">No nodes</td></tr>'}</tbody>
    </table>
  </div>

  <h2>🟢 Edges / Relations ({len(edges)})</h2>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Source</th><th>Target</th><th>Relation</th><th>Confidence</th></tr></thead>
      <tbody>{edge_rows if edge_rows else '<tr><td colspan="4" style="text-align:center;padding:20px;color:#4b5563">No edges</td></tr>'}</tbody>
    </table>
  </div>

  <h2>📄 Raw JSON</h2>
  <button class="json-toggle" onclick="toggleJson('snapshot')">Show Snapshot JSON</button>
  <div id="snapshot-json" class="json-block">{json.dumps(snapshot_json, indent=2, ensure_ascii=False)[:50000]}</div>

  <button class="json-toggle" onclick="toggleJson('transcription')" style="margin-top:8px">Show Transcription JSON</button>
  <div id="transcription-json" class="json-block">{json.dumps(transcription_json, indent=2, ensure_ascii=False)[:20000]}</div>

  <script>
    function toggleJson(type) {{
      const el = document.getElementById(type + '-json');
      el.style.display = el.style.display === 'block' ? 'none' : 'block';
    }}
  </script>
</body>
</html>"""


def _error_page(message: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><title>DB Error</title>
<style>body{{background:#0f172a;color:#fca5a5;font-family:monospace;padding:40px;}}
h1{{color:#ef4444;margin-bottom:16px;}}pre{{background:#1e293b;padding:16px;border-radius:8px;color:#e5e7eb;}}</style>
</head><body>
<h1>Database Error</h1>
<pre>{message}</pre>
<p style="margin-top:16px;color:#6b7280">Make sure PostgreSQL is running and DATABASE_URL is set correctly in .env</p>
<a href="/db" style="color:#60a5fa">← Try again</a>
</body></html>"""
