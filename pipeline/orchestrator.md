# VFX Breakdown Pipeline — Orchestrator

## Overview

This pipeline reads a screenplay and produces a complete VFX breakdown and bid estimate through five sequential agent stages. Each stage has a defined input schema, output schema, system prompt, and validation rules.

```
┌─────────────┐     ┌────────────────┐     ┌───────────────┐     ┌──────────────────┐     ┌────────────────┐
│   Stage 1   │     │    Stage 2     │     │    Stage 3    │     │     Stage 4      │     │    Stage 5     │
│   Script    │────▶│   Sequence     │────▶│     Shot      │────▶│     Asset        │────▶│      Bid       │
│  Ingestion  │     │   Breakdown    │     │   Breakdown   │     │   Extraction     │     │   Generation   │
└─────────────┘     └────────────────┘     └───────────────┘     └──────────────────┘     └────────────────┘
      ▲                                                                                         │
      │                                                                                         │
      │              ┌──────────────────┐                                                       │
      └──────────────│   Assumptions    │───────────────────────────────────────────────────────▶│
                     │   (provided at   │   (fed into every stage)                              │
                     │    any point)    │                                                       ▼
                     └──────────────────┘                                              Final Deliverables
```

## Prerequisites

Before running the pipeline, you need:

1. **The screenplay** — Full text, PDF, or URL
2. **Production assumptions** (optional but recommended) — Key decisions about what is practical vs. CG, what locations are available, LED wall plans, etc. These can be established during Stage 1 or provided upfront.

## Pipeline Stages

### Stage 1: Script Ingestion & VFX Flagging

| | |
|---|---|
| **Prompt** | `prompts/01_script_ingestion.md` |
| **Input** | Screenplay text + Assumptions (optional) |
| **Output** | Scene-by-scene VFX flag list (JSON array) |
| **Schema** | Input: `schemas/script_input.schema.json` / Output: inline (array of flagged scenes) |
| **Purpose** | Read the script and flag every moment requiring VFX |

**Validation checks before proceeding:**
- Every scene in the script has been processed (even if `has_vfx: false`)
- VFX flags include both explicit and implied work
- LED stage opportunities are noted where applicable

---

### Stage 2: Sequence Breakdown

| | |
|---|---|
| **Prompt** | `prompts/02_sequence_breakdown.md` |
| **Input** | VFX flag list from Stage 1 + Assumptions + Screenplay |
| **Output** | `sequences.schema.json` |
| **Purpose** | Group VFX scenes into production sequences with previz/LED assessments |

**Validation checks before proceeding:**
- All flagged VFX scenes from Stage 1 are accounted for in a sequence
- `total_estimated_vfx_shots` equals the sum of all `estimated_shot_count` values
- Previz complexity ratings are consistent with requirements described
- LED stage recommendations include specific benefit descriptions

---

### Stage 3: Shot Breakdown

| | |
|---|---|
| **Prompt** | `prompts/03_shot_breakdown.md` |
| **Input** | Sequence breakdown from Stage 2 + Assumptions + Screenplay |
| **Output** | `shots.schema.json` |
| **Purpose** | Decompose each sequence into individual VFX shots with complexity and asset refs |

**Validation checks before proceeding:**
- `total_vfx_shots` equals the length of the `shots` array
- Shot numbers are sequential and unique
- Every shot references at least one asset
- Complexity ratings are justified by the description
- `work_type` is consistent with `vfx_tasks` (e.g., `cg_character` tasks should not have `work_type: "2D"`)
- Shot counts per sequence are within ±20% of the sequence estimates from Stage 2

---

### Stage 4: Asset Extraction

| | |
|---|---|
| **Prompt** | `prompts/04_asset_extraction.md` |
| **Input** | Shot breakdown from Stage 3 + Sequence breakdown + Assumptions |
| **Output** | `assets.schema.json` |
| **Purpose** | Consolidate all referenced assets into a deduplicated inventory |

**Validation checks before proceeding:**
- Every asset referenced in any shot exists in the asset inventory
- `shot_count` matches the length of `shots_used_in` for every asset
- No duplicate assets (same CG element listed twice under different names)
- Asset complexity ratings are consistent with requirements described
- Asset types are correctly categorized

---

### Stage 5: Bid Generation

| | |
|---|---|
| **Prompt** | `prompts/05_bid_generation.md` |
| **Input** | Shots + Assets + Sequences + Assumptions + Rate Card (optional) |
| **Output** | `bid.schema.json` |
| **Purpose** | Translate the breakdown into hours, headcount, and cost estimates |

**Validation checks on final output:**
- `summary.total_vfx_shots` matches the shot breakdown count
- `summary.total_assets` matches the asset inventory count
- Department artist-weeks sum to `summary.total_artist_weeks` (within rounding)
- Cost range low < high
- Schedule minimum < recommended

---

## Running the Pipeline

### Option A: Sequential (Single Conversation)

Run each stage in order within one conversation. After each stage, review the output before proceeding. This allows for human-in-the-loop review and assumption refinement.

```
1. Load screenplay text into conversation
2. Load assumptions (if available)
3. Run Stage 1 prompt → review VFX flags → adjust
4. Feed Stage 1 output + run Stage 2 prompt → review sequences → adjust
5. Feed Stage 2 output + run Stage 3 prompt → review shots → adjust
6. Feed Stage 3 output + run Stage 4 prompt → review assets → adjust
7. Feed all outputs + run Stage 5 prompt → review bid → finalize
```

### Option B: Agentic (Multi-Agent)

Use a framework (Claude Agent SDK, LangGraph, CrewAI, etc.) to orchestrate as a multi-agent pipeline:

```python
# Pseudocode
assumptions = load_assumptions("assumptions.json")
script = load_script("screenplay.txt")

# Stage 1
vfx_flags = agent_1_ingest(script, assumptions)
validate(vfx_flags, stage=1)

# Stage 2  
sequences = agent_2_sequences(vfx_flags, assumptions, script)
validate(sequences, "sequences.schema.json")

# Stage 3
shots = agent_3_shots(sequences, assumptions, script)
validate(shots, "shots.schema.json")

# Stage 4
assets = agent_4_assets(shots, sequences, assumptions)
validate(assets, "assets.schema.json")

# Stage 5
bid = agent_5_bid(shots, assets, sequences, assumptions)
validate(bid, "bid.schema.json")

# Output
export_csv(sequences, "Sequences.csv")
export_csv(shots, "Shots.csv")
export_csv(assets, "Assets.csv")
export_bid_report(bid, "Bid_Report.pdf")
```

### Option C: Hybrid

Run Stages 1-2 interactively (assumptions need human input), then batch Stages 3-5 automatically once sequences are locked.

---

## Output Formats

The pipeline produces JSON conforming to the schemas. For client delivery, convert to:

| Deliverable | Format | Source |
|------------|--------|--------|
| Sequence Overview | CSV or Google Sheet | `sequences.schema.json` |
| Shot Breakdown | CSV or Google Sheet | `shots.schema.json` |
| Asset Inventory | CSV or Google Sheet | `assets.schema.json` |
| Bid Summary | PDF report | `bid.schema.json` |
| Assumptions | Document | `assumptions.schema.json` |

---

## Iteration & Revision

The pipeline is designed for iteration:

- **Assumption changes** (e.g., "character X is now full CG instead of practical") → re-run from Stage 1 or 2
- **Shot count changes** (editorial feedback) → re-run from Stage 3
- **Rate card changes** → re-run Stage 5 only
- **Creative scope changes** (new sequences added) → re-run from Stage 2

Each stage's output is a standalone JSON file that can be version-controlled and diffed between iterations.

---

## File Reference

```
pipeline/
├── orchestrator.md                    ← This file
├── schemas/
│   ├── script_input.schema.json       ← Entry point schema
│   ├── assumptions.schema.json        ← Production assumptions
│   ├── sequences.schema.json          ← Stage 2 output
│   ├── shots.schema.json              ← Stage 3 output
│   ├── assets.schema.json             ← Stage 4 output
│   └── bid.schema.json                ← Stage 5 output
├── prompts/
│   ├── 01_script_ingestion.md         ← Agent 1 system prompt
│   ├── 02_sequence_breakdown.md       ← Agent 2 system prompt
│   ├── 03_shot_breakdown.md           ← Agent 3 system prompt
│   ├── 04_asset_extraction.md         ← Agent 4 system prompt
│   └── 05_bid_generation.md           ← Agent 5 system prompt
└── examples/
    └── ex_machina/                    ← Example run-through
```
