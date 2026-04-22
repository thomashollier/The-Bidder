# VFX Breakdown & Bid Pipeline

An AI-powered pipeline that reads a screenplay and produces a complete VFX shot breakdown, asset inventory, and bid estimate. Built for Claude (Anthropic's AI), it runs as a guided conversation where you feed in a script and walk through five stages to get production-ready deliverables.

## What It Does

You give it a screenplay. It gives you back:

- **VFX Flag List** — every moment in the script that needs visual effects
- **Sequence Breakdown** — scenes grouped into VFX production units with previz and LED/VP assessments
- **Shot Breakdown** — every individual VFX shot with complexity ratings, task tags, and asset references
- **Asset Inventory** — consolidated list of everything that needs to be built (CG characters, environments, FX, screen content)
- **Bid Estimate** — cost range, department breakdowns, schedule, and top cost drivers

## What You Need

1. **A Claude account** — Go to [claude.ai](https://claude.ai) and sign up. The free tier works but a Pro account ($20/month) gives longer conversations, which you'll need for a full script.
2. **A screenplay** — Plain text, PDF, or pasted into the conversation. Any format Claude can read.
3. **This pipeline folder** — The prompts, schemas, and example files in this repo.

## Quick Start (Claude Web)

### Step 1: Start a Claude Project (recommended)

Claude Projects let you upload files that persist across conversations, so you don't need to re-paste the prompts each time.

1. Go to [claude.ai](https://claude.ai) and click **Projects** in the left sidebar
2. Click **Create Project**
3. Name it something like "VFX Breakdown Pipeline"
4. In the project's **Knowledge** section, upload these files:
   - `pipeline/prompts/01_script_ingestion.md`
   - `pipeline/prompts/02_sequence_breakdown.md`
   - `pipeline/prompts/03_shot_breakdown.md`
   - `pipeline/prompts/04_asset_extraction.md`
   - `pipeline/prompts/05_bid_generation.md`
   - `pipeline/schemas/assumptions.schema.json`
   - `pipeline/schemas/sequences.schema.json`
   - `pipeline/schemas/shots.schema.json`
   - `pipeline/schemas/assets.schema.json`
   - `pipeline/schemas/bid.schema.json`
5. In the project's **Instructions** field, paste:
   ```
   You are a VFX breakdown pipeline. You have five agent prompts and their
   corresponding output schemas loaded in your knowledge base. When the user
   provides a screenplay, walk through each stage sequentially. After each
   stage, present the output for review before proceeding to the next.
   Always produce output as JSON conforming to the relevant schema.
   ```

### Step 2: Run the Pipeline

Start a new conversation inside your project. Here's exactly what to say at each step:

**Opening message:**
```
I have a screenplay I'd like to break down for VFX. Here are my production
assumptions:

1. [List your assumptions — what's practical vs. CG, LED wall plans, etc.]
2. [e.g., "The creature is full CG in all shots"]
3. [e.g., "Driving scenes will use LED wall"]
4. [e.g., "All screen/monitor content is replaced in post"]

The script is attached / pasted below.

Please begin with Stage 1: Script Ingestion using the 01_script_ingestion
prompt from your knowledge base.
```

Attach or paste your screenplay with this message.

**After Stage 1 completes**, review the VFX flags and say:
```
Looks good. [Or: "Add/remove/change X."] Proceed to Stage 2: Sequence
Breakdown using the 02_sequence_breakdown prompt.
```

**After Stage 2**, review the sequences and say:
```
Proceed to Stage 3: Shot Breakdown using the 03_shot_breakdown prompt.
```

**After Stage 3**, review the shots and say:
```
Proceed to Stage 4: Asset Extraction using the 04_asset_extraction prompt.
```

**After Stage 4**, review the assets and say:
```
Proceed to Stage 5: Bid Generation using the 05_bid_generation prompt.
Use these day rates: [your rates, or say "use the defaults"].
```

### Step 3: Export Your Results

Each stage produces JSON output. To get spreadsheet-ready formats, say:
```
Convert the sequences/shots/assets output to CSV format.
```

Or for a summary document:
```
Write a bid summary report covering the top cost drivers, schedule,
and department breakdown.
```

## Without a Claude Project (simple method)

If you don't want to set up a Project, you can run this in a single conversation:

1. Open a new chat at [claude.ai](https://claude.ai)
2. Copy the contents of `pipeline/prompts/01_script_ingestion.md` and paste it as your first message along with your screenplay
3. After it produces Stage 1 output, copy the next prompt file and paste it with "Now run this stage using the output above"
4. Repeat for each stage

This works but you'll use more of your conversation context re-pasting prompt text.

## Using Claude Code (CLI)

If you have [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed, you can run this from the terminal:

```bash
cd /path/to/vfx_breakdown
claude
```

Then say:
```
Read the pipeline orchestrator and all prompts/schemas. I want to run
the full pipeline on [screenplay name]. Here's the script: [paste or
point to file]. Start with Stage 1.
```

Claude Code can read the files directly from disk, write output files, and manage the whole pipeline in one session.

## Automated Pipeline (Python Script)

For a fully automated run with no interaction, use the included Python script. It calls `claude -p` for each stage and saves all outputs to a folder.

### Prerequisites

- **Python 3.10+** — Check with `python3 --version`
- **Claude Code CLI** — Install from [docs.anthropic.com/en/docs/claude-code](https://docs.anthropic.com/en/docs/claude-code), then run `claude login` to authenticate

### Basic Usage

```bash
# Run the full pipeline on a screenplay
python run_pipeline.py my_script.txt

# With production assumptions
python run_pipeline.py my_script.txt --assumptions assumptions.json

# Specify output directory and model
python run_pipeline.py my_script.txt -o my_project/ --model opus

# With a custom rate card for bid generation
python run_pipeline.py my_script.txt -a assumptions.json -r rates.json -o my_project/
```

### Resuming a Run

If a stage fails or you want to re-run later stages after editing an earlier output, use `--start-stage`:

```bash
# Re-run from stage 3 (uses stage 1-2 outputs already in the output dir)
python run_pipeline.py my_script.txt --start-stage 3 -o my_project/

# Re-run only the bid with a new rate card
python run_pipeline.py my_script.txt --start-stage 5 -o my_project/ -r new_rates.json
```

### What It Produces

```
output/
├── stage_1_vfx_flags.json      — Every VFX moment flagged scene by scene
├── stage_2_sequences.json      — Scenes grouped into VFX production sequences
├── stage_3_shots.json          — Individual VFX shots with complexity ratings
├── stage_4_assets.json         — Consolidated asset inventory
└── stage_5_bid.json            — Cost estimate, schedule, department breakdown
```

### All Options

```
python run_pipeline.py --help

positional arguments:
  screenplay              Path to screenplay file (plain text or PDF)

options:
  --assumptions, -a       Path to production assumptions JSON file
  --output-dir, -o        Directory for output files (default: output/)
  --rate-card, -r         Path to custom rate card JSON for bid generation
  --start-stage, -s       Stage to start from (1-5, default: 1)
  --model, -m             Claude model to use (sonnet, opus, haiku)
  --verbose, -v           Print extra debug information
```

## File Structure

```
run_pipeline.py                  — Automated pipeline runner (Python)
pipeline/
├── orchestrator.md              — Full pipeline documentation and flow
├── schemas/
│   ├── script_input.schema.json — What the pipeline expects as input
│   ├── assumptions.schema.json  — Production assumptions format
│   ├── sequences.schema.json    — Stage 2 output format
│   ├── shots.schema.json        — Stage 3 output format
│   ├── assets.schema.json       — Stage 4 output format
│   └── bid.schema.json          — Stage 5 output format
├── prompts/
│   ├── 01_script_ingestion.md   — Reads script, flags all VFX moments
│   ├── 02_sequence_breakdown.md — Groups scenes into VFX sequences
│   ├── 03_shot_breakdown.md     — Breaks sequences into individual shots
│   ├── 04_asset_extraction.md   — Builds consolidated asset inventory
│   └── 05_bid_generation.md     — Generates cost/schedule estimate
└── examples/
    └── ex_machina/              — Complete example run-through
        ├── script_input.json
        ├── assumptions.json
        ├── stage_1_vfx_flags.json
        ├── stage_2_sequences.json
        ├── stage_3_shots.json
        ├── stage_4_assets.json
        └── stage_5_bid.json
```

## The Example: Ex Machina

The `examples/ex_machina/` folder contains a complete pipeline run on Alex Garland's *Ex Machina* — a mid-budget sci-fi film with a hero CG character (Ava's robot body), screen replacements, matte paintings, and practical-to-CG transitions. Browse these files to see what the pipeline produces at each stage.

Key numbers from the example:
- 80 VFX shots across 12 sequences
- 17 active CG assets
- $2.8M–$3.9M estimated VFX budget
- 36-week recommended schedule

## Tips

- **Assumptions matter.** The single biggest thing that changes your breakdown scope is whether something is practical or CG. Spend time on your assumptions before running Stage 1.
- **Review between stages.** Don't just blast through all five stages. The output of each stage feeds the next — catch errors early.
- **Long scripts may need splitting.** If your screenplay is over 100 pages, Claude may run out of context. Split the script into acts and run Stage 1 on each section, then combine the flags before Stage 2.
- **Iterate.** Changed an assumption? You don't need to re-run everything. See the orchestrator doc for which stages need re-running based on what changed.
- **Custom rate cards.** Stage 5 has default US day rates. Override them by providing your own rates when you reach that stage.
- **CSV export.** After any stage, ask Claude to "convert this to CSV" and it will produce spreadsheet-ready output.
