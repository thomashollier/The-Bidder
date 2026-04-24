"""
The Bidder — Web Server
=======================
Flask app that serves the UI and runs pipeline stages via Claude Code CLI.
"""

import json
import os
import queue
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
PIPELINE_DIR = ROOT / "pipeline"
PROMPTS_DIR = PIPELINE_DIR / "prompts"
SCHEMAS_DIR = PIPELINE_DIR / "schemas"
PROJECTS_DIR = ROOT / "projects"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

# Current project state — single-user local app
project_state = {
    "id": None,
    "name": "",
    "screenplay_path": None,
    "screenplay_text": None,
    "assumptions_text": "",
    "rate_card": "",
    "project_dir": None,
    "stages": {
        1: {"status": "pending", "output": None, "summary": ""},
        2: {"status": "pending", "output": None, "summary": ""},
        3: {"status": "pending", "output": None, "summary": ""},
        4: {"status": "pending", "output": None, "summary": ""},
        5: {"status": "pending", "output": None, "summary": ""},
    },
    "running": False,
}

# SSE event queue
event_queue = queue.Queue()

STAGE_NAMES = {
    1: "Script Ingestion",
    2: "Sequence Breakdown",
    3: "Shot Breakdown",
    4: "Asset Extraction",
    5: "Bid Generation",
}

STAGE_FILES = {
    1: {"prompt": "01_script_ingestion.md", "output": "stage_1_vfx_flags.json"},
    2: {"prompt": "02_sequence_breakdown.md", "output": "stage_2_sequences.json", "schema": "sequences.schema.json"},
    3: {"prompt": "03_shot_breakdown.md", "output": "stage_3_shots.json", "schema": "shots.schema.json"},
    4: {"prompt": "04_asset_extraction.md", "output": "stage_4_assets.json", "schema": "assets.schema.json"},
    5: {"prompt": "05_bid_generation.md", "output": "stage_5_bid.json", "schema": "bid.schema.json"},
}


def push_event(event_type, data):
    """Push an SSE event to all listeners."""
    event_queue.put({"type": event_type, "data": data})


# ---------------------------------------------------------------------------
# Claude CLI helpers
# ---------------------------------------------------------------------------

def extract_json_from_response(text):
    """Extract JSON from Claude's response."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    for open_c, close_c in [("{", "}"), ("[", "]")]:
        start = text.find(open_c)
        end = text.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("Could not extract JSON from Claude response")


def run_claude(prompt, model=None):
    """Call claude -p and return response text."""
    cmd = ["claude", "-p", prompt]
    if model:
        cmd += ["--model", model]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if result.returncode != 0:
        raise RuntimeError(f"Claude error: {result.stderr}")
    return result.stdout


def load_file(path):
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_prompt(stage_num, screenplay, assumptions, stage_outputs, rate_card=""):
    """Build the full prompt for a given stage."""
    info = STAGE_FILES[stage_num]
    agent_prompt = load_file(PROMPTS_DIR / info["prompt"])
    schema = ""
    if "schema" in info:
        schema = load_file(SCHEMAS_DIR / info["schema"])

    if stage_num == 1:
        parts = [agent_prompt, "\n\n---\n\n## SCREENPLAY\n\n", screenplay]
        if assumptions:
            parts += ["\n\n---\n\n## PRODUCTION ASSUMPTIONS\n\n", assumptions]
        parts.append(
            "\n\n---\n\n## INSTRUCTIONS\n\n"
            "Analyze the screenplay above following your role description. "
            "Produce ONLY the JSON array output. No preamble, no explanation."
        )

    elif stage_num == 2:
        parts = [
            agent_prompt,
            "\n\n---\n\n## OUTPUT SCHEMA\n\n```json\n", schema, "\n```\n",
            "\n\n---\n\n## INPUT: VFX FLAGS FROM STAGE 1\n\n```json\n", stage_outputs[1], "\n```\n",
        ]
        if assumptions:
            parts += ["\n\n---\n\n## PRODUCTION ASSUMPTIONS\n\n", assumptions]
        parts += [
            "\n\n---\n\n## SCREENPLAY (for reference)\n\n", screenplay,
            "\n\n---\n\n## INSTRUCTIONS\n\nProduce ONLY valid JSON conforming to the schema. No preamble."
        ]

    elif stage_num == 3:
        parts = [
            agent_prompt,
            "\n\n---\n\n## OUTPUT SCHEMA\n\n```json\n", schema, "\n```\n",
            "\n\n---\n\n## INPUT: SEQUENCE BREAKDOWN\n\n```json\n", stage_outputs[2], "\n```\n",
        ]
        if assumptions:
            parts += ["\n\n---\n\n## PRODUCTION ASSUMPTIONS\n\n", assumptions]
        parts += [
            "\n\n---\n\n## SCREENPLAY (for reference)\n\n", screenplay,
            "\n\n---\n\n## INSTRUCTIONS\n\nProduce ONLY valid JSON conforming to the schema. No preamble."
        ]

    elif stage_num == 4:
        parts = [
            agent_prompt,
            "\n\n---\n\n## OUTPUT SCHEMA\n\n```json\n", schema, "\n```\n",
            "\n\n---\n\n## INPUT: SHOT BREAKDOWN\n\n```json\n", stage_outputs[3], "\n```\n",
            "\n\n---\n\n## CONTEXT: SEQUENCE BREAKDOWN\n\n```json\n", stage_outputs[2], "\n```\n",
        ]
        if assumptions:
            parts += ["\n\n---\n\n## PRODUCTION ASSUMPTIONS\n\n", assumptions]
        parts.append("\n\n---\n\n## INSTRUCTIONS\n\nProduce ONLY valid JSON conforming to the schema. No preamble.")

    elif stage_num == 5:
        parts = [
            agent_prompt,
            "\n\n---\n\n## OUTPUT SCHEMA\n\n```json\n", schema, "\n```\n",
            "\n\n---\n\n## INPUT: SHOT BREAKDOWN\n\n```json\n", stage_outputs[3], "\n```\n",
            "\n\n---\n\n## INPUT: ASSET INVENTORY\n\n```json\n", stage_outputs[4], "\n```\n",
            "\n\n---\n\n## CONTEXT: SEQUENCE BREAKDOWN\n\n```json\n", stage_outputs[2], "\n```\n",
        ]
        if assumptions:
            parts += ["\n\n---\n\n## PRODUCTION ASSUMPTIONS\n\n", assumptions]
        if rate_card:
            parts += ["\n\n---\n\n## RATE CARD\n\n", rate_card]
        parts.append("\n\n---\n\n## INSTRUCTIONS\n\nProduce ONLY valid JSON conforming to the schema. No preamble.")

    return "".join(parts)


# ---------------------------------------------------------------------------
# Stage summary helpers
# ---------------------------------------------------------------------------

def summarize_stage(stage_num, data):
    """Return a human-readable summary string for a stage's output."""
    try:
        if stage_num == 1:
            total = len(data)
            with_vfx = sum(1 for s in data if s.get("has_vfx"))
            flags = sum(len(s.get("vfx_flags", [])) for s in data)
            return f"{total} scenes analyzed, {with_vfx} with VFX, {flags} flags"
        elif stage_num == 2:
            seqs = data.get("total_sequences", len(data.get("sequences", [])))
            shots = data.get("total_estimated_vfx_shots", "?")
            return f"{seqs} sequences, ~{shots} estimated VFX shots"
        elif stage_num == 3:
            shots = data.get("total_vfx_shots", len(data.get("shots", [])))
            by_tier = {}
            for s in data.get("shots", []):
                c = s.get("complexity", 0)
                by_tier[c] = by_tier.get(c, 0) + 1
            tier_str = "  ".join(f"C{k}: {v}" for k, v in sorted(by_tier.items()))
            return f"{shots} VFX shots — {tier_str}"
        elif stage_num == 4:
            assets = data.get("total_assets", len(data.get("assets", [])))
            types = {}
            for a in data.get("assets", []):
                t = a.get("asset_type", "Other")
                types[t] = types.get(t, 0) + 1
            type_str = ", ".join(f"{v} {k}" for k, v in sorted(types.items(), key=lambda x: -x[1]))
            return f"{assets} assets — {type_str}"
        elif stage_num == 5:
            summary = data.get("summary", {})
            cost = summary.get("cost_range", {})
            low = cost.get("low", 0)
            high = cost.get("high", 0)
            weeks = summary.get("total_artist_weeks", "?")
            sched = summary.get("schedule_weeks", {}).get("recommended", "?")
            return f"${low:,.0f} – ${high:,.0f}  |  {weeks} artist-weeks  |  {sched}-week schedule"
    except Exception:
        return "Output generated"
    return ""


# ---------------------------------------------------------------------------
# Pipeline runner (background thread)
# ---------------------------------------------------------------------------

def run_pipeline_stages(start_stage, end_stage):
    """Run pipeline stages in a background thread."""
    global project_state
    project_state["running"] = True

    screenplay = project_state["screenplay_text"]
    assumptions = project_state["assumptions_text"]
    rate_card = project_state["rate_card"]
    proj_dir = Path(project_state["project_dir"])

    # Collect prior stage outputs
    stage_outputs = {}
    for s in range(1, start_stage):
        out = project_state["stages"][s].get("output")
        if out:
            stage_outputs[s] = json.dumps(out, indent=2, ensure_ascii=False)

    for stage_num in range(start_stage, end_stage + 1):
        info = STAGE_FILES[stage_num]
        project_state["stages"][stage_num]["status"] = "running"
        push_event("stage_update", {
            "stage": stage_num,
            "status": "running",
            "message": f"Running {STAGE_NAMES[stage_num]}..."
        })

        try:
            prompt = build_prompt(stage_num, screenplay, assumptions, stage_outputs, rate_card)

            push_event("stage_update", {
                "stage": stage_num,
                "status": "running",
                "message": f"Waiting for Claude ({len(prompt):,} chars)..."
            })

            response = run_claude(prompt)
            data = extract_json_from_response(response)

            # Save to disk
            out_path = proj_dir / info["output"]
            out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

            # Update state
            stage_outputs[stage_num] = json.dumps(data, indent=2, ensure_ascii=False)
            summary = summarize_stage(stage_num, data)
            project_state["stages"][stage_num]["status"] = "complete"
            project_state["stages"][stage_num]["output"] = data
            project_state["stages"][stage_num]["summary"] = summary

            push_event("stage_update", {
                "stage": stage_num,
                "status": "complete",
                "summary": summary,
            })

        except Exception as e:
            project_state["stages"][stage_num]["status"] = "error"
            project_state["stages"][stage_num]["summary"] = str(e)
            push_event("stage_update", {
                "stage": stage_num,
                "status": "error",
                "message": str(e),
            })
            break

    project_state["running"] = False
    push_event("pipeline_done", {"success": project_state["stages"][end_stage]["status"] == "complete"})


# ---------------------------------------------------------------------------
# Routes — Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------

@app.route("/api/upload", methods=["POST"])
def upload_screenplay():
    """Upload a screenplay file and create a project."""
    if "screenplay" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["screenplay"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400

    project_name = request.form.get("project_name", f.filename.rsplit(".", 1)[0])
    assumptions = request.form.get("assumptions", "")
    rate_card = request.form.get("rate_card", "")

    # Create project directory
    proj_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + project_name.replace(" ", "_")
    proj_dir = PROJECTS_DIR / proj_id
    proj_dir.mkdir(parents=True, exist_ok=True)

    # Save screenplay
    screenplay_path = proj_dir / f.filename
    f.save(str(screenplay_path))
    screenplay_text = screenplay_path.read_text(encoding="utf-8", errors="replace")

    # Save assumptions if provided
    if assumptions.strip():
        (proj_dir / "assumptions.txt").write_text(assumptions, encoding="utf-8")

    # Reset state
    project_state.update({
        "id": proj_id,
        "name": project_name,
        "screenplay_path": str(screenplay_path),
        "screenplay_text": screenplay_text,
        "assumptions_text": assumptions,
        "rate_card": rate_card,
        "project_dir": str(proj_dir),
        "stages": {
            1: {"status": "pending", "output": None, "summary": ""},
            2: {"status": "pending", "output": None, "summary": ""},
            3: {"status": "pending", "output": None, "summary": ""},
            4: {"status": "pending", "output": None, "summary": ""},
            5: {"status": "pending", "output": None, "summary": ""},
        },
        "running": False,
    })

    return jsonify({
        "project_id": proj_id,
        "project_name": project_name,
        "screenplay_chars": len(screenplay_text),
        "has_assumptions": bool(assumptions.strip()),
    })


@app.route("/api/assumptions", methods=["POST"])
def update_assumptions():
    """Update assumptions for the current project."""
    data = request.get_json()
    project_state["assumptions_text"] = data.get("assumptions", "")
    project_state["rate_card"] = data.get("rate_card", "")
    return jsonify({"ok": True})


@app.route("/api/run", methods=["POST"])
def run_stages():
    """Start running pipeline stages."""
    if project_state["running"]:
        return jsonify({"error": "Pipeline is already running"}), 409
    if not project_state["screenplay_text"]:
        return jsonify({"error": "No screenplay uploaded"}), 400

    data = request.get_json() or {}
    start = data.get("start_stage", 1)
    end = data.get("end_stage", 5)

    # Check prerequisites for resuming
    for s in range(1, start):
        if project_state["stages"][s]["status"] != "complete":
            return jsonify({"error": f"Stage {s} must be complete before starting stage {start}"}), 400

    # Reset stages being run
    for s in range(start, end + 1):
        project_state["stages"][s] = {"status": "pending", "output": None, "summary": ""}

    thread = threading.Thread(target=run_pipeline_stages, args=(start, end), daemon=True)
    thread.start()

    return jsonify({"started": True, "start_stage": start, "end_stage": end})


@app.route("/api/status")
def get_status():
    """Get current pipeline state."""
    stages = {}
    for s in range(1, 6):
        st = project_state["stages"][s]
        stages[str(s)] = {
            "status": st["status"],
            "summary": st["summary"],
            "has_output": st["output"] is not None,
        }
    return jsonify({
        "project_name": project_state["name"],
        "has_screenplay": project_state["screenplay_text"] is not None,
        "running": project_state["running"],
        "stages": stages,
    })


@app.route("/api/output/<int:stage>")
def get_output(stage):
    """Get the full JSON output for a stage."""
    if stage < 1 or stage > 5:
        return jsonify({"error": "Invalid stage"}), 400
    output = project_state["stages"][stage].get("output")
    if output is None:
        return jsonify({"error": "Stage not complete"}), 404
    return jsonify(output)


@app.route("/api/export/<int:stage>/csv")
def export_csv(stage):
    """Export a stage's output as CSV."""
    if stage < 1 or stage > 5:
        return jsonify({"error": "Invalid stage"}), 400
    output = project_state["stages"][stage].get("output")
    if output is None:
        return jsonify({"error": "Stage not complete"}), 404

    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)

    if stage == 1:
        writer.writerow(["Scene", "Heading", "Pages", "Has VFX", "Flag Count", "Summary"])
        for scene in output:
            writer.writerow([
                scene.get("scene_number", ""),
                scene.get("scene_heading", ""),
                scene.get("page_range", ""),
                scene.get("has_vfx", ""),
                len(scene.get("vfx_flags", [])),
                scene.get("scene_summary", ""),
            ])
    elif stage == 2:
        writer.writerow(["Seq #", "Name", "Scenes", "Pages", "Est. Shots", "VFX Requirements", "Previz Needed", "Previz Complexity", "LED Recommended", "Assumptions"])
        for seq in output.get("sequences", []):
            writer.writerow([
                seq.get("sequence_number", ""),
                seq.get("sequence_name", ""),
                seq.get("scenes", ""),
                seq.get("page_range", ""),
                seq.get("estimated_shot_count", ""),
                seq.get("vfx_requirements", ""),
                seq.get("previz", {}).get("needed", ""),
                seq.get("previz", {}).get("complexity", ""),
                seq.get("led_stage", {}).get("recommended", ""),
                seq.get("assumptions", ""),
            ])
    elif stage == 3:
        writer.writerow(["Shot #", "Seq #", "Sequence", "Scene", "Page", "Description", "Complexity", "Type", "Assets", "VFX Tasks", "Notes"])
        for shot in output.get("shots", []):
            writer.writerow([
                shot.get("shot_number", ""),
                shot.get("sequence_number", ""),
                shot.get("sequence_name", ""),
                shot.get("scene_number", ""),
                shot.get("page_number", ""),
                shot.get("description", ""),
                shot.get("complexity", ""),
                shot.get("work_type", ""),
                "; ".join(shot.get("assets_required", [])),
                "; ".join(shot.get("vfx_tasks", [])),
                shot.get("notes", ""),
            ])
    elif stage == 4:
        writer.writerow(["Asset #", "Name", "Type", "Description", "Requirements", "Complexity", "Shot Count", "Notes"])
        for asset in output.get("assets", []):
            writer.writerow([
                asset.get("asset_number", ""),
                asset.get("asset_name", ""),
                asset.get("asset_type", ""),
                asset.get("description", ""),
                asset.get("requirements", ""),
                asset.get("complexity", ""),
                asset.get("shot_count", ""),
                asset.get("notes", ""),
            ])
    elif stage == 5:
        # Summary + department breakdown
        summary = output.get("summary", {})
        writer.writerow(["VFX Bid Summary"])
        writer.writerow(["Total VFX Shots", summary.get("total_vfx_shots", "")])
        writer.writerow(["Total Assets", summary.get("total_assets", "")])
        writer.writerow(["Total Artist-Weeks", summary.get("total_artist_weeks", "")])
        cost = summary.get("cost_range", {})
        writer.writerow(["Cost Low", f"${cost.get('low', 0):,.0f}"])
        writer.writerow(["Cost High", f"${cost.get('high', 0):,.0f}"])
        writer.writerow([])
        writer.writerow(["Department", "Artist-Weeks", "Peak Headcount", "Est. Cost"])
        for dept in output.get("department_breakdown", []):
            writer.writerow([
                dept.get("department", ""),
                dept.get("artist_weeks", ""),
                dept.get("peak_headcount", ""),
                f"${dept.get('estimated_cost', 0):,.0f}",
            ])

    csv_text = buf.getvalue()
    stage_name = STAGE_NAMES[stage].lower().replace(" ", "_")
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={stage_name}.csv"},
    )


@app.route("/api/events")
def sse_events():
    """Server-Sent Events endpoint for real-time updates."""
    def stream():
        # Send current state on connect
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        while True:
            try:
                event = event_queue.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

    return Response(stream(), mimetype="text/event-stream")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    PROJECTS_DIR.mkdir(exist_ok=True)
    app.run(host="127.0.0.1", port=5050, debug=False)
