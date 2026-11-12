// AI-Driven Network Automation Frontend Logic
let currentProposalId = null;
let selectedFile = null;
let pollInterval = null;

document.addEventListener("DOMContentLoaded", () => {
    initUpload();
    initButtons();
    startJobPolling();
});

function initUpload() {
    const fileInput = document.getElementById("diagram-upload");
    const previewImg = document.getElementById("diagram-preview-img");
    const previewPlaceholder = document.getElementById("preview-placeholder");
    const filenameLabel = document.getElementById("selected-filename");
    const btnGenerate = document.getElementById("btn-generate");

    fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files[0]) {
            selectedFile = e.target.files[0];
            filenameLabel.textContent = selectedFile.name;
            btnGenerate.disabled = false;

            const reader = new FileReader();
            reader.onload = (re) => {
                previewImg.src = re.target.result;
                previewImg.classList.remove("hidden");
                previewPlaceholder.classList.add("hidden");
            };
            reader.readAsDataURL(selectedFile);
        }
    });
}

function initButtons() {
    const btnGenerate = document.getElementById("btn-generate");
    const btnReconfigure = document.getElementById("btn-reconfigure");
    const btnApprove = document.getElementById("btn-approve");

    btnGenerate.addEventListener("click", uploadAndAnalyze);
    btnReconfigure.addEventListener("click", reconfigureProposal);
    btnApprove.addEventListener("click", approveAndDeploy);
}

async function uploadAndAnalyze() {
    if (!selectedFile) return;

    const loading = document.getElementById("ai-loading");
    const analysisSection = document.getElementById("analysis-section");
    const btnGenerate = document.getElementById("btn-generate");

    loading.classList.remove("hidden");
    analysisSection.classList.add("hidden");
    btnGenerate.disabled = true;

    updateStepNav(2);

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
        const response = await fetch("/api/upload", {
            method: "POST",
            body: formData
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Upload & Analysis failed");
        }

        const data = await response.json();
        currentProposalId = data.proposal_id;

        renderAnalysisData(data);
        loading.classList.add("hidden");
        analysisSection.classList.remove("hidden");
        updateStepNav(3);
    } catch (err) {
        loading.classList.add("hidden");
        btnGenerate.disabled = false;
        alert("Error analyzing diagram: " + err.message);
    }
}

function renderAnalysisData(data) {
    // 1. Ambiguities Banner
    const ambCard = document.getElementById("ambiguities-card");
    const ambList = document.getElementById("ambiguity-list");
    ambList.innerHTML = "";
    if (data.ambiguities && data.ambiguities.length > 0) {
        data.ambiguities.forEach(a => {
            const li = document.createElement("li");
            li.textContent = a;
            ambList.appendChild(li);
        });
        ambCard.classList.remove("hidden");
    } else {
        ambCard.classList.add("hidden");
    }

    // 2. Structured JSON View
    document.getElementById("topology-json-view").textContent = JSON.stringify(data.topology, null, 2);

    // 3. Configurations
    document.getElementById("r1-config-preview").textContent = data.configurations["R1"] || "";
    document.getElementById("r2-config-preview").textContent = data.configurations["R2"] || "";

    // 4. Interface inputs
    if (data.interfaces) {
        document.getElementById("r1_lan_int").value = data.interfaces.r1_lan || "FastEthernet0/1";
        document.getElementById("r1_wan_int").value = data.interfaces.r1_wan || "FastEthernet0/0";
        document.getElementById("r2_wan_int").value = data.interfaces.r2_wan || "FastEthernet0/0";
        document.getElementById("r2_lan_int").value = data.interfaces.r2_lan || "FastEthernet0/1";
        document.getElementById("r1_mgmt_ip").value = data.interfaces.r1_mgmt_ip || "192.168.122.111";
        document.getElementById("r2_mgmt_ip").value = data.interfaces.r2_mgmt_ip || "192.168.122.102";
    }

    // 5. Validation Checks
    renderValidationChecks(data.validation);
}

function renderValidationChecks(validation) {
    const container = document.getElementById("validation-checks-container");
    container.innerHTML = "";

    if (!validation || !validation.checks) return;

    validation.checks.forEach(c => {
        const div = document.createElement("div");
        let badgeColor = "bg-emerald-100 text-emerald-800 border-emerald-300";
        let icon = "fa-check";

        if (c.status === "WARNING") {
            badgeColor = "bg-amber-100 text-amber-800 border-amber-300";
            icon = "fa-triangle-exclamation";
        } else if (c.status === "FAILED") {
            badgeColor = "bg-rose-100 text-rose-800 border-rose-300";
            icon = "fa-xmark";
        }

        div.className = `p-3 rounded-xl border flex items-start gap-3 bg-white shadow-xs`;
        div.innerHTML = `
            <span class="p-1.5 rounded-lg border text-xs font-bold ${badgeColor} flex-shrink-0">
                <i class="fa-solid ${icon}"></i>
            </span>
            <div>
                <p class="text-xs font-bold text-slate-800">${c.name}</p>
                <p class="text-[11px] text-slate-600 mt-0.5">${c.message}</p>
            </div>
        `;
        container.appendChild(div);
    });
}

async function reconfigureProposal() {
    if (!currentProposalId) return;

    const payload = {
        r1_lan_int: document.getElementById("r1_lan_int").value.trim(),
        r1_wan_int: document.getElementById("r1_wan_int").value.trim(),
        r2_wan_int: document.getElementById("r2_wan_int").value.trim(),
        r2_lan_int: document.getElementById("r2_lan_int").value.trim(),
        r1_mgmt_ip: document.getElementById("r1_mgmt_ip").value.trim(),
        r2_mgmt_ip: document.getElementById("r2_mgmt_ip").value.trim()
    };

    try {
        const resp = await fetch(`/api/proposals/${currentProposalId}/reconfigure`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!resp.ok) throw new Error("Reconfiguration failed");

        const data = await resp.json();
        document.getElementById("r1-config-preview").textContent = data.configurations["R1"] || "";
        document.getElementById("r2-config-preview").textContent = data.configurations["R2"] || "";
        renderValidationChecks(data.validation);
        alert("Configurations updated and re-validated successfully!");
    } catch (err) {
        alert("Error reconfiguring: " + err.message);
    }
}

async function approveAndDeploy() {
    if (!currentProposalId) return;

    const confirmApprove = confirm("ADMIN APPROVAL CONFIRMATION:\n\nAre you sure you want to approve the OSPF configurations and dispatch deployment jobs to Kafka (network-config-jobs)?");
    if (!confirmApprove) return;

    updateStepNav(4);

    try {
        const resp = await fetch(`/api/proposals/${currentProposalId}/approve-and-deploy`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ approved_by: "Instructor / Admin" })
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Approval failed");
        }

        const data = await resp.json();
        alert("Approved! Jobs dispatched to Kafka topic 'network-config-jobs'. The Python Worker is executing deployment.");
        updateStepNav(5);
        fetchJobs();
    } catch (err) {
        alert("Approval/Dispatch error: " + err.message);
    }
}

async function fetchJobs() {
    try {
        const resp = await fetch("/api/jobs");
        if (!resp.ok) return;
        const jobs = await resp.json();
        renderJobs(jobs);
    } catch (err) {
        console.error("Failed to fetch jobs:", err);
    }
}

function renderJobs(jobs) {
    const emptyEl = document.getElementById("jobs-empty");
    const listEl = document.getElementById("jobs-list");

    if (!jobs || jobs.length === 0) {
        emptyEl.classList.remove("hidden");
        listEl.classList.add("hidden");
        return;
    }

    emptyEl.classList.add("hidden");
    listEl.classList.remove("hidden");
    listEl.innerHTML = "";

    jobs.forEach(j => {
        const card = document.createElement("div");
        card.className = "bg-white border rounded-xl p-4 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4";

        let statusBadge = "";
        if (j.status === "PENDING") {
            statusBadge = `<span class="bg-amber-100 text-amber-800 border border-amber-300 text-xs px-2.5 py-1 rounded-full font-bold flex items-center gap-1.5"><i class="fa-solid fa-clock"></i> PENDING (In Kafka)</span>`;
        } else if (j.status === "RUNNING") {
            statusBadge = `<span class="bg-blue-100 text-blue-800 border border-blue-300 text-xs px-2.5 py-1 rounded-full font-bold flex items-center gap-1.5 pulse-running"><i class="fa-solid fa-spinner fa-spin"></i> RUNNING (Worker SSH)</span>`;
        } else if (j.status === "SUCCESS") {
            statusBadge = `<span class="bg-emerald-100 text-emerald-800 border border-emerald-300 text-xs px-2.5 py-1 rounded-full font-bold flex items-center gap-1.5"><i class="fa-solid fa-circle-check"></i> SUCCESS</span>`;
        } else {
            statusBadge = `<span class="bg-rose-100 text-rose-800 border border-rose-300 text-xs px-2.5 py-1 rounded-full font-bold flex items-center gap-1.5"><i class="fa-solid fa-circle-xmark"></i> FAILED</span>`;
        }

        let verifyBadge = "";
        if (j.verification_status === "PASSED") {
            verifyBadge = `<span class="text-xs bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded border border-emerald-200 font-semibold"><i class="fa-solid fa-check"></i> OSPF FULL & Remote Route Learned</span>`;
        } else if (j.verification_status === "FAILED") {
            verifyBadge = `<span class="text-xs bg-rose-50 text-rose-700 px-2 py-0.5 rounded border border-rose-200 font-semibold"><i class="fa-solid fa-xmark"></i> OSPF Verification Incomplete</span>`;
        }

        card.innerHTML = `
            <div class="space-y-1">
                <div class="flex items-center gap-3">
                    <span class="font-bold text-sm text-slate-900">${j.device_id}</span>
                    <span class="text-xs font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded">${j.mgmt_ip}</span>
                    ${statusBadge}
                </div>
                <div class="flex items-center gap-3 text-xs text-slate-500">
                    <span>Job ID: <code class="font-mono text-slate-700">${j.job_id}</code></span>
                    <span>•</span>
                    <span>Created: ${new Date(j.created_at).toLocaleTimeString()}</span>
                    ${j.completed_at ? `<span>• Completed: ${new Date(j.completed_at).toLocaleTimeString()}</span>` : ""}
                </div>
                ${verifyBadge ? `<div class="mt-1">${verifyBadge}</div>` : ""}
                ${j.status === "FAILED" && j.error_message ? `<p class="text-xs text-rose-600 font-semibold mt-1">${j.error_message}</p>` : ""}
            </div>
            <div class="flex items-center gap-2">
                <button onclick="viewJobLogs('${j.job_id}')" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition">
                    <i class="fa-solid fa-terminal"></i> View Logs
                </button>
                <button onclick="reverifyJob('${j.job_id}')" class="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition border border-blue-200">
                    <i class="fa-solid fa-arrows-rotate"></i> Re-verify
                </button>
            </div>
        `;

        listEl.appendChild(card);
    });
}

async function viewJobLogs(jobId) {
    try {
        const resp = await fetch(`/api/jobs/${jobId}`);
        if (!resp.ok) return;
        const job = await resp.json();

        document.getElementById("modal-title").innerHTML = `<i class="fa-solid fa-terminal text-blue-400"></i> ${job.device_id} (${job.mgmt_ip}) — Job Logs [${job.status}]`;
        document.getElementById("modal-verification-log").textContent = job.verification_log || "No verification logs recorded yet.";
        document.getElementById("modal-deployment-log").textContent = job.deployment_log || "No deployment output recorded.";

        document.getElementById("log-modal").classList.remove("hidden");
    } catch (err) {
        alert("Failed to load logs: " + err.message);
    }
}

async function reverifyJob(jobId) {
    try {
        const resp = await fetch(`/api/jobs/${jobId}/reverify`, { method: "POST" });
        if (!resp.ok) throw new Error("Re-verify call failed");
        const data = await resp.json();
        alert(`OSPF Re-verification for ${data.device_id}: ${data.verification_status}`);
        fetchJobs();
    } catch (err) {
        alert("Error during reverification: " + err.message);
    }
}

function closeModal() {
    document.getElementById("log-modal").classList.add("hidden");
}

function toggleElement(id) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle("hidden");
}

function updateStepNav(currentStep) {
    for (let i = 1; i <= 5; i++) {
        const el = document.getElementById(`step-nav-${i}`);
        if (!el) continue;
        if (i < currentStep) {
            el.className = "p-2.5 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center justify-center gap-2";
            el.querySelector("span").className = "w-5 h-5 rounded-full bg-emerald-600 text-white flex items-center justify-center text-xs";
        } else if (i === currentStep) {
            el.className = "p-2.5 rounded-lg bg-blue-50 text-blue-700 border border-blue-200 flex items-center justify-center gap-2 font-bold shadow-xs";
            el.querySelector("span").className = "w-5 h-5 rounded-full bg-blue-600 text-white flex items-center justify-center text-xs";
        } else {
            el.className = "p-2.5 rounded-lg bg-slate-100 text-slate-500 border border-slate-200 flex items-center justify-center gap-2";
            el.querySelector("span").className = "w-5 h-5 rounded-full bg-slate-400 text-white flex items-center justify-center text-xs";
        }
    }
}

function startJobPolling() {
    fetchJobs();
    pollInterval = setInterval(fetchJobs, 3000);
}
