#!/usr/bin/env python3
"""
VFX Breakdown Pipeline Runner
==============================
Orchestrates the full 5-stage VFX breakdown pipeline by invoking
Claude Code CLI (`claude -p`) for each stage, passing outputs forward.

Usage:
    python run_pipeline.py screenplay.txt
    python run_pipeline.py screenplay.pdf --assumptions assumptions.json -o my_project/
    python run_pipeline.py script.txt --start-stage 3 -o my_project/  # resume from stage 3

Requirements:
    - Claude Code CLI installed and authenticated (`claude` command available)
    - Python 3.10+
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent
PIPELINE_DIR = ROOT / "pipeline"
PROMPTS_DIR = PIPELINE_DIR / "prompts"
SCHEMAS_DIR = PIPELINE_DIR / "schemas"

STAGE_FILES = {
    1: {"prompt": "01_script_ingestion.md", "output": "stage_1_vfx_flags.json"},
    2: {"prompt": "02_sequence_breakdown.md", "output": "stage_2_sequences.json",  "schema": "sequences.schema.json"},
    3: {"prompt": "03_shot_breakdown.md",    "output": "stage_3_shots.json",       "schema": "shots.schema.json"},
    4: {"prompt": "04_asset_extraction.md",  "output": "stage_4_assets.json",      "schema": "assets.schema.json"},
    5: {"prompt": "05_bid_generation.md",    "output": "stage_5_bid.json",         "schema": "bid.schema.json"},
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def save_json(data, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def extract_json(text: str):
    """Pull JSON from Claude's response, handling markdown fences and prose."""
    # Direct parse
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # ```json ... ```
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # First { … last }  or  [ … ]
    for open_c, close_c in [("{", "}"), ("[", "]")]:
        start = text.find(open_c)
        end = text.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue

    raise ValueError(
        "Could not extract JSON from Claude's response. "
        "First 500 chars:\n" + text[:500]
    )


def run_claude(prompt: str, model: str | None = None, verbose: bool = False) -> str:
    """Invoke `claude -p` and return the response text."""
    cmd = ["claude", "-p", prompt]
    if model:
        cmd += ["--model", model]

    if verbose:
        # Show prompt size, not the whole prompt
        print(f"    Prompt size: {len(prompt):,} chars")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,  # 15 min per stage
        )
    except FileNotFoundError:
        print(
            "Error: 'claude' command not found.\n"
            "Install Claude Code CLI: https://docs.anthropic.com/en/docs/claude-code\n"
            "Then run: claude login",
            file=sys.stderr,
        )
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Error: Claude timed out (15 min limit). Try a shorter script or split into acts.", file=sys.stderr)
        sys.exit(1)

    if result.returncode != 0:
        print(f"Claude error (exit {result.returncode}):\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    return result.stdout


# ---------------------------------------------------------------------------
# Prompt builders — one per stage
# ---------------------------------------------------------------------------

def build_stage_1_prompt(agent_prompt: str, screenplay: str, assumptions: str) -> str:
    parts = [
        agent_prompt,
        "\n\n---\n\n## SCREENPLAY\n\n",
        screenplay,
    ]
    if assumptions:
        parts += ["\n\n---\n\n## PRODUCTION ASSUMPTIONS\n\n", assumptions]
    parts.append(
        "\n\n---\n\n## INSTRUCTIONS\n\n"
        "Analyze the screenplay above following your role description. "
        "Produce ONLY the JSON array output described in your Output Format section. "
        "No preamble, no explanation — just valid JSON."
    )
    return "".join(parts)


def build_stage_2_prompt(
    agent_prompt: str, schema: str, stage_1: str, assumptions: str, screenplay: str
) -> str:
    parts = [
        agent_prompt,
        "\n\n---\n\n## OUTPUT SCHEMA\n\n```json\n", schema, "\n```\n",
        "\n\n---\n\n## INPUT: VFX FLAGS FROM STAGE 1\n\n```json\n", stage_1, "\n```\n",
    ]
    if assumptions:
        parts += ["\n\n---\n\n## PRODUCTION ASSUMPTIONS\n\n", assumptions]
    parts += [
        "\n\n---\n\n## SCREENPLAY (for reference)\n\n", screenplay,
        "\n\n---\n\n## INSTRUCTIONS\n\n"
        "Group the VFX flags into production sequences following your role description. "
        "Produce ONLY valid JSON conforming to the output schema above. "
        "No preamble, no explanation."
    ]
    return "".join(parts)


def build_stage_3_prompt(
    agent_prompt: str, schema: str, stage_2: str, assumptions: str, screenplay: str
) -> str:
    parts = [
        agent_prompt,
        "\n\n---\n\n## OUTPUT SCHEMA\n\n```json\n", schema, "\n```\n",
        "\n\n---\n\n## INPUT: SEQUENCE BREAKDOWN FROM STAGE 2\n\n```json\n", stage_2, "\n```\n",
    ]
    if assumptions:
        parts += ["\n\n---\n\n## PRODUCTION ASSUMPTIONS\n\n", assumptions]
    parts += [
        "\n\n---\n\n## SCREENPLAY (for reference)\n\n", screenplay,
        "\n\n---\n\n## INSTRUCTIONS\n\n"
        "Break each sequence into individual VFX shots following your role description. "
        "Produce ONLY valid JSON conforming to the output schema above. "
        "No preamble, no explanation."
    ]
    return "".join(parts)


def build_stage_4_prompt(
    agent_prompt: str, schema: str, stage_3: str, stage_2: str, assumptions: str
) -> str:
    parts = [
        agent_prompt,
        "\n\n---\n\n## OUTPUT SCHEMA\n\n```json\n", schema, "\n```\n",
        "\n\n---\n\n## INPUT: SHOT BREAKDOWN FROM STAGE 3\n\n```json\n", stage_3, "\n```\n",
        "\n\n---\n\n## CONTEXT: SEQUENCE BREAKDOWN FROM STAGE 2\n\n```json\n", stage_2, "\n```\n",
    ]
    if assumptions:
        parts += ["\n\n---\n\n## PRODUCTION ASSUMPTIONS\n\n", assumptions]
    parts.append(
        "\n\n---\n\n## INSTRUCTIONS\n\n"
        "Extract and consolidate all VFX assets following your role description. "
        "Produce ONLY valid JSON conforming to the output schema above. "
        "No preamble, no explanation."
    )
    return "".join(parts)


def build_stage_5_prompt(
    agent_prompt: str,
    schema: str,
    stage_3: str,
    stage_4: str,
    stage_2: str,
    assumptions: str,
    rate_card: str,
) -> str:
    parts = [
        agent_prompt,
        "\n\n---\n\n## OUTPUT SCHEMA\n\n```json\n", schema, "\n```\n",
        "\n\n---\n\n## INPUT: SHOT BREAKDOWN\n\n```json\n", stage_3, "\n```\n",
        "\n\n---\n\n## INPUT: ASSET INVENTORY\n\n```json\n", stage_4, "\n```\n",
        "\n\n---\n\n## CONTEXT: SEQUENCE BREAKDOWN\n\n```json\n", stage_2, "\n```\n",
    ]
    if assumptions:
        parts += ["\n\n---\n\n## PRODUCTION ASSUMPTIONS\n\n", assumptions]
    if rate_card:
        parts += ["\n\n---\n\n## RATE CARD\n\n", rate_card]
    parts.append(
        "\n\n---\n\n## INSTRUCTIONS\n\n"
        "Generate the VFX bid estimate following your role description. "
        "Produce ONLY valid JSON conforming to the output schema above. "
        "No preamble, no explanation."
    )
    return "".join(parts)


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

STAGE_NAMES = {
    1: "Script Ingestion & VFX Flagging",
    2: "Sequence Breakdown",
    3: "Shot Breakdown",
    4: "Asset Extraction",
    5: "Bid Generation",
}


def run_pipeline(args):
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load screenplay
    screenplay_path = Path(args.screenplay)
    if not screenplay_path.exists():
        print(f"Error: screenplay not found: {screenplay_path}", file=sys.stderr)
        sys.exit(1)
    screenplay = load(screenplay_path)
    print(f"Loaded screenplay: {screenplay_path} ({len(screenplay):,} chars)")

    # Load assumptions
    assumptions = ""
    if args.assumptions:
        assumptions_path = Path(args.assumptions)
        if not assumptions_path.exists():
            print(f"Error: assumptions file not found: {assumptions_path}", file=sys.stderr)
            sys.exit(1)
        assumptions = load(assumptions_path)
        print(f"Loaded assumptions: {assumptions_path}")

    # Load rate card
    rate_card = ""
    if args.rate_card:
        rate_card_path = Path(args.rate_card)
        if not rate_card_path.exists():
            print(f"Error: rate card not found: {rate_card_path}", file=sys.stderr)
            sys.exit(1)
        rate_card = load(rate_card_path)
        print(f"Loaded rate card: {rate_card_path}")

    # Accumulators for stage outputs (as JSON strings)
    stage_outputs: dict[int, str] = {}

    # If resuming, load prior stage outputs from disk
    if args.start_stage > 1:
        print(f"\nResuming from Stage {args.start_stage} — loading prior outputs...")
        for s in range(1, args.start_stage):
            prior_path = output_dir / STAGE_FILES[s]["output"]
            if not prior_path.exists():
                print(
                    f"Error: cannot resume from stage {args.start_stage} — "
                    f"missing {prior_path}\n"
                    f"Run earlier stages first, or start from stage 1.",
                    file=sys.stderr,
                )
                sys.exit(1)
            stage_outputs[s] = load(prior_path)
            print(f"  Loaded stage {s}: {prior_path}")

    # Run each stage
    for stage_num in range(args.start_stage, 6):
        info = STAGE_FILES[stage_num]
        print(f"\n{'='*60}")
        print(f"Stage {stage_num}: {STAGE_NAMES[stage_num]}")
        print(f"{'='*60}")

        # Load prompt template
        agent_prompt = load(PROMPTS_DIR / info["prompt"])

        # Load schema (stages 2-5)
        schema = ""
        if "schema" in info:
            schema = load(SCHEMAS_DIR / info["schema"])

        # Build the prompt
        if stage_num == 1:
            prompt = build_stage_1_prompt(agent_prompt, screenplay, assumptions)
        elif stage_num == 2:
            prompt = build_stage_2_prompt(
                agent_prompt, schema, stage_outputs[1], assumptions, screenplay
            )
        elif stage_num == 3:
            prompt = build_stage_3_prompt(
                agent_prompt, schema, stage_outputs[2], assumptions, screenplay
            )
        elif stage_num == 4:
            prompt = build_stage_4_prompt(
                agent_prompt, schema, stage_outputs[3], stage_outputs[2], assumptions
            )
        elif stage_num == 5:
            prompt = build_stage_5_prompt(
                agent_prompt, schema, stage_outputs[3], stage_outputs[4],
                stage_outputs[2], assumptions, rate_card,
            )

        # Run Claude
        print(f"  Running Claude... ({len(prompt):,} chars prompt)")
        response = run_claude(prompt, model=args.model, verbose=args.verbose)

        # Extract JSON
        try:
            data = extract_json(response)
        except ValueError as e:
            # Save raw response for debugging
            raw_path = output_dir / f"stage_{stage_num}_raw.txt"
            raw_path.write_text(response, encoding="utf-8")
            print(f"Error: {e}", file=sys.stderr)
            print(f"  Raw response saved to {raw_path} for debugging.", file=sys.stderr)
            sys.exit(1)

        # Save output
        out_path = output_dir / info["output"]
        save_json(data, out_path)

        # Store for next stage
        stage_outputs[stage_num] = json.dumps(data, indent=2, ensure_ascii=False)

        # Print summary
        print_stage_summary(stage_num, data)

    # Final summary
    print(f"\n{'='*60}")
    print("Pipeline complete!")
    print(f"{'='*60}")
    print(f"Output directory: {output_dir}/")
    for s in range(1, 6):
        print(f"  Stage {s}: {STAGE_FILES[s]['output']}")


def print_stage_summary(stage_num: int, data):
    """Print a brief summary after each stage."""
    if stage_num == 1:
        total = len(data)
        with_vfx = sum(1 for s in data if s.get("has_vfx"))
        flags = sum(len(s.get("vfx_flags", [])) for s in data)
        print(f"  {total} scenes analyzed, {with_vfx} with VFX, {flags} total flags")

    elif stage_num == 2:
        seqs = data.get("total_sequences", len(data.get("sequences", [])))
        shots = data.get("total_estimated_vfx_shots", "?")
        print(f"  {seqs} sequences, {shots} estimated VFX shots")

    elif stage_num == 3:
        shots = data.get("total_vfx_shots", len(data.get("shots", [])))
        # Count by complexity
        by_tier = {}
        for s in data.get("shots", []):
            c = s.get("complexity", 0)
            by_tier[c] = by_tier.get(c, 0) + 1
        tier_str = ", ".join(f"C{k}={v}" for k, v in sorted(by_tier.items()))
        print(f"  {shots} VFX shots  [{tier_str}]")

    elif stage_num == 4:
        assets = data.get("total_assets", len(data.get("assets", [])))
        types = {}
        for a in data.get("assets", []):
            t = a.get("asset_type", "Other")
            types[t] = types.get(t, 0) + 1
        type_str = ", ".join(f"{k}={v}" for k, v in sorted(types.items()))
        print(f"  {assets} assets  [{type_str}]")

    elif stage_num == 5:
        summary = data.get("summary", {})
        cost = summary.get("cost_range", {})
        low = cost.get("low", 0)
        high = cost.get("high", 0)
        weeks = summary.get("total_artist_weeks", "?")
        sched = summary.get("schedule_weeks", {}).get("recommended", "?")
        print(f"  Budget: ${low:,.0f} – ${high:,.0f}")
        print(f"  {weeks} artist-weeks, {sched}-week schedule")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Run the VFX breakdown pipeline on a screenplay using Claude Code CLI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py my_script.txt
  python run_pipeline.py my_script.pdf --assumptions assumptions.json -o output/
  python run_pipeline.py my_script.txt --start-stage 3 -o output/
  python run_pipeline.py my_script.txt --rate-card rates.json --model opus
        """,
    )
    parser.add_argument(
        "screenplay",
        help="Path to screenplay file (plain text or PDF)",
    )
    parser.add_argument(
        "--assumptions", "-a",
        help="Path to production assumptions JSON file (see schemas/assumptions.schema.json)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="output",
        help="Directory for output files (default: output/)",
    )
    parser.add_argument(
        "--rate-card", "-r",
        help="Path to custom rate card JSON for bid generation (uses defaults if omitted)",
    )
    parser.add_argument(
        "--start-stage", "-s",
        type=int,
        default=1,
        choices=[1, 2, 3, 4, 5],
        help="Stage to start from — requires prior stage outputs in output dir (default: 1)",
    )
    parser.add_argument(
        "--model", "-m",
        help="Claude model to use (e.g., sonnet, opus, haiku)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print extra debug information",
    )
    args = parser.parse_args()
    run_pipeline(args)


if __name__ == "__main__":
    main()
