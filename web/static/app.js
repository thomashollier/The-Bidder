// ===================================================================
// The Bidder — Frontend Application
// ===================================================================

const STAGE_NAMES = {
    1: "Script Ingestion",
    2: "Sequence Breakdown",
    3: "Shot Breakdown",
    4: "Asset Extraction",
    5: "Bid Generation",
};

let selectedFile = null;
let eventSource = null;

// -------------------------------------------------------------------
// Initialization
// -------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    setupDropZone();
    setupSSE();
    fetchStatus();
});

// -------------------------------------------------------------------
// Drop Zone
// -------------------------------------------------------------------

function setupDropZone() {
    const zone = document.getElementById("drop-zone");
    const input = document.getElementById("file-input");

    zone.addEventListener("click", () => input.click());
    zone.addEventListener("dragover", (e) => {
        e.preventDefault();
        zone.classList.add("dragover");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", (e) => {
        e.preventDefault();
        zone.classList.remove("dragover");
        if (e.dataTransfer.files.length) {
            handleFile(e.dataTransfer.files[0]);
        }
    });
    input.addEventListener("change", () => {
        if (input.files.length) handleFile(input.files[0]);
    });
}

function handleFile(file) {
    selectedFile = file;
    const zone = document.getElementById("drop-zone");
    zone.classList.add("has-file");
    zone.innerHTML = `
        <div class="drop-zone-file">${file.name}</div>
        <div style="color: var(--text-muted); font-size: 13px; margin-top: 8px;">
            ${(file.size / 1024).toFixed(0)} KB — click to change
        </div>
    `;
    document.getElementById("btn-upload").disabled = false;
}

// -------------------------------------------------------------------
// Upload & Project Setup
// -------------------------------------------------------------------

async function uploadScreenplay() {
    if (!selectedFile) return;

    const form = new FormData();
    form.append("screenplay", selectedFile);
    form.append("project_name", document.getElementById("project-name").value || selectedFile.name);
    form.append("assumptions", document.getElementById("assumptions").value);
    form.append("rate_card", document.getElementById("rate-card").value);

    const btn = document.getElementById("btn-upload");
    btn.disabled = true;
    btn.textContent = "Uploading...";

    try {
        const res = await fetch("/api/upload", { method: "POST", body: form });
        const data = await res.json();
        if (data.error) {
            alert("Upload error: " + data.error);
            btn.disabled = false;
            btn.textContent = "Upload & Create Project";
            return;
        }

        // Show pipeline section
        document.getElementById("setup-panel").style.display = "none";
        document.getElementById("pipeline-panel").style.display = "block";
        document.getElementById("project-title").textContent = data.project_name;
        document.getElementById("screenplay-info").textContent =
            `${selectedFile.name} — ${(data.screenplay_chars / 1000).toFixed(0)}K chars`;

        resetStageCards();
    } catch (err) {
        alert("Upload failed: " + err.message);
        btn.disabled = false;
        btn.textContent = "Upload & Create Project";
    }
}

// -------------------------------------------------------------------
// Pipeline Control
// -------------------------------------------------------------------

async function runAllStages() {
    await runStages(1, 5);
}

async function runSingleStage(stage) {
    await runStages(stage, stage);
}

async function runStages(start, end) {
    const btn = document.getElementById("btn-run-all");
    btn.disabled = true;

    try {
        const res = await fetch("/api/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ start_stage: start, end_stage: end }),
        });
        const data = await res.json();
        if (data.error) {
            alert(data.error);
            btn.disabled = false;
        }
    } catch (err) {
        alert("Error starting pipeline: " + err.message);
        btn.disabled = false;
    }
}

function goBack() {
    document.getElementById("setup-panel").style.display = "block";
    document.getElementById("pipeline-panel").style.display = "none";
    const btn = document.getElementById("btn-upload");
    btn.disabled = false;
    btn.textContent = "Upload & Create Project";
}

// -------------------------------------------------------------------
// SSE — Real-time Updates
// -------------------------------------------------------------------

function setupSSE() {
    eventSource = new EventSource("/api/events");
    eventSource.onmessage = (e) => {
        const event = JSON.parse(e.data);
        handleEvent(event);
    };
    eventSource.onerror = () => {
        // Reconnect after a delay
        setTimeout(() => {
            if (eventSource.readyState === EventSource.CLOSED) setupSSE();
        }, 3000);
    };
}

function handleEvent(event) {
    if (event.type === "stage_update") {
        updateStageCard(event.data.stage, event.data);
    } else if (event.type === "pipeline_done") {
        document.getElementById("btn-run-all").disabled = false;
        // Enable individual stage buttons
        document.querySelectorAll(".btn-run-stage").forEach(b => b.disabled = false);
    }
}

// -------------------------------------------------------------------
// Stage Cards
// -------------------------------------------------------------------

function resetStageCards() {
    for (let s = 1; s <= 5; s++) {
        const card = document.getElementById(`stage-${s}`);
        card.className = "stage-card";
        card.querySelector(".stage-summary").textContent = "Pending";
        card.querySelector(".stage-body").style.display = "none";
    }
}

function updateStageCard(stage, data) {
    const card = document.getElementById(`stage-${stage}`);
    const summary = card.querySelector(".stage-summary");
    const number = card.querySelector(".stage-number");

    // Remove old status classes
    card.classList.remove("pending", "running", "complete", "error");
    card.classList.add(data.status);

    if (data.status === "running") {
        summary.innerHTML = `<span class="spinner"></span> ${data.message || "Running..."}`;
    } else if (data.status === "complete") {
        summary.textContent = data.summary || "Complete";
        number.textContent = "✓";
        // Show action buttons
        const actions = card.querySelector(".stage-actions");
        actions.innerHTML = `
            <button class="btn btn-secondary btn-sm" onclick="toggleOutput(${stage})">View</button>
            <button class="btn btn-secondary btn-sm" onclick="exportCSV(${stage})">CSV</button>
        `;
        loadStageOutput(stage);
    } else if (data.status === "error") {
        summary.textContent = data.message || "Error";
        number.textContent = "✗";
    }
}

function toggleOutput(stage) {
    const card = document.getElementById(`stage-${stage}`);
    card.classList.toggle("expanded");
}

async function loadStageOutput(stage) {
    try {
        const res = await fetch(`/api/output/${stage}`);
        const data = await res.json();
        const viewer = document.querySelector(`#stage-${stage} .output-viewer`);
        viewer.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
        // Silently fail — output viewer will be empty
    }
}

function exportCSV(stage) {
    window.open(`/api/export/${stage}/csv`, "_blank");
}

// -------------------------------------------------------------------
// Fetch initial status (for page reloads)
// -------------------------------------------------------------------

async function fetchStatus() {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();

        if (data.has_screenplay) {
            document.getElementById("setup-panel").style.display = "none";
            document.getElementById("pipeline-panel").style.display = "block";
            document.getElementById("project-title").textContent = data.project_name;

            for (let s = 1; s <= 5; s++) {
                const st = data.stages[s];
                if (st.status !== "pending") {
                    updateStageCard(s, { status: st.status, summary: st.summary, message: st.summary });
                }
            }

            if (!data.running) {
                document.getElementById("btn-run-all").disabled = false;
            }
        }
    } catch (err) {
        // Server not ready yet — ignore
    }
}
