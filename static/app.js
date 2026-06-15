/**
 * app.js — AWS Spec Analyzer front-end logic
 * Features: analyze, interactive BOM, remove/add services, comparative report,
 *           region selector, missing-info form with re-analyze, client-side region switching
 */

"use strict";

// ── AWS Regions (synced with pricing.py) ──────────────────────────────────
const REGIONS = [
  { code: "us-east-1",      label: "US East (N. Virginia)",        multiplier: 1.00 },
  { code: "us-east-2",      label: "US East (Ohio)",               multiplier: 1.00 },
  { code: "us-west-1",      label: "US West (N. California)",      multiplier: 1.14 },
  { code: "us-west-2",      label: "US West (Oregon)",             multiplier: 1.00 },
  { code: "ca-central-1",   label: "Canada (Central)",             multiplier: 1.10 },
  { code: "ca-west-1",      label: "Canada (Calgary)",             multiplier: 1.12 },
  { code: "eu-west-1",      label: "Europe (Ireland)",             multiplier: 1.12 },
  { code: "eu-west-2",      label: "Europe (London)",              multiplier: 1.17 },
  { code: "eu-west-3",      label: "Europe (Paris)",               multiplier: 1.17 },
  { code: "eu-central-1",   label: "Europe (Frankfurt)",           multiplier: 1.16 },
  { code: "eu-central-2",   label: "Europe (Zurich)",              multiplier: 1.18 },
  { code: "eu-north-1",     label: "Europe (Stockholm)",           multiplier: 1.10 },
  { code: "eu-south-1",     label: "Europe (Milan)",               multiplier: 1.18 },
  { code: "eu-south-2",     label: "Europe (Spain)",               multiplier: 1.18 },
  { code: "ap-southeast-1", label: "Asia Pacific (Singapore)",     multiplier: 1.13 },
  { code: "ap-southeast-2", label: "Asia Pacific (Sydney)",        multiplier: 1.14 },
  { code: "ap-southeast-3", label: "Asia Pacific (Jakarta)",       multiplier: 1.15 },
  { code: "ap-southeast-4", label: "Asia Pacific (Melbourne)",     multiplier: 1.14 },
  { code: "ap-northeast-1", label: "Asia Pacific (Tokyo)",         multiplier: 1.18 },
  { code: "ap-northeast-2", label: "Asia Pacific (Seoul)",         multiplier: 1.13 },
  { code: "ap-northeast-3", label: "Asia Pacific (Osaka)",         multiplier: 1.18 },
  { code: "ap-south-1",     label: "Asia Pacific (Mumbai)",        multiplier: 1.12 },
  { code: "ap-south-2",     label: "Asia Pacific (Hyderabad)",     multiplier: 1.14 },
  { code: "ap-east-1",      label: "Asia Pacific (Hong Kong)",     multiplier: 1.20 },
  { code: "me-south-1",     label: "Middle East (Bahrain)",        multiplier: 1.18 },
  { code: "me-central-1",   label: "Middle East (UAE)",            multiplier: 1.18 },
  { code: "af-south-1",     label: "Africa (Cape Town)",           multiplier: 1.20 },
  { code: "il-central-1",   label: "Israel (Tel Aviv)",            multiplier: 1.20 },
  { code: "sa-east-1",      label: "South America (Sao Paulo)",     multiplier: 1.22 },
  { code: "us-gov-east-1",  label: "AWS GovCloud (US-East)",       multiplier: 1.15 },
  { code: "us-gov-west-1",  label: "AWS GovCloud (US-West)",       multiplier: 1.15 },
];

// ── State ─────────────────────────────────────────────────────────────────
const state = {
  analysisResult: null,
  originalText: null,
  bomRows: [],
  region: "us-east-1",
  regionMultiplier: 1.00,
  missingInfoValues: {},
};

let currentMappings = [];   // active BOM items (includes manually added)
let selectedFile    = null;

// ── DOM refs ──────────────────────────────────────────────────────────────
const dropZone         = document.getElementById("drop-zone");
const fileInput        = document.getElementById("file-input");
const fileSelectedInfo = document.getElementById("file-selected-info");
const selectedFilename = document.getElementById("selected-filename");
const clearFileBtn     = document.getElementById("clear-file");
const textInput        = document.getElementById("text-input");
const analyzeBtn       = document.getElementById("analyze-btn");
const projectName      = document.getElementById("project-name");
const loading          = document.getElementById("loading");
const errorBox         = document.getElementById("error-box");
const errorMsg         = document.getElementById("error-message");
const resultSection    = document.getElementById("result-section");
const resultMeta       = document.getElementById("result-meta");
const missingBox       = document.getElementById("missing-info-box");
const missingList      = document.getElementById("missing-info-list");
const bomSection       = document.getElementById("bom-section");
const bomWrapper       = document.getElementById("bom-table-wrapper");
const bomTotalBadge    = document.getElementById("bom-total-badge");
const totalMonthly     = document.getElementById("total-monthly");
const totalAnnual      = document.getElementById("total-annual");
const exportCsvBtn     = document.getElementById("export-csv-btn");
const exportXlsxBtn    = document.getElementById("export-excel-btn");
const bomRowTemplate   = document.getElementById("bom-row-template");
const addServiceBtn    = document.getElementById("add-service-btn");
const compareSection   = document.getElementById("compare-section");
const compareTbody     = document.getElementById("compare-tbody");
const compareTotalEl   = document.getElementById("compare-total-monthly");
const regionSelect     = document.getElementById("region-select");

// Modal refs
const modalBackdrop  = document.getElementById("modal-backdrop");
const modalClose     = document.getElementById("modal-close");
const modalCancel    = document.getElementById("modal-cancel");
const modalConfirm   = document.getElementById("modal-confirm");
const mCategory      = document.getElementById("m-category");
const mService       = document.getElementById("m-service");
const mSku           = document.getElementById("m-sku");
const mQty           = document.getElementById("m-qty");
const mUnit          = document.getElementById("m-unit");
const mPricing       = document.getElementById("m-pricing");
const mCost          = document.getElementById("m-cost");
const mNotes         = document.getElementById("m-notes");

// ── AWS Service catalogue for "Add Service" modal ─────────────────────────
const AWS_CATALOGUE = {
  "Compute": [
    "Amazon EC2", "Amazon EC2 Auto Scaling", "AWS Lambda",
    "AWS Elastic Beanstalk", "AWS Batch", "AWS Lightsail",
  ],
  "Storage": [
    "Amazon S3", "Amazon EBS", "Amazon EFS",
    "Amazon FSx for Windows File Server", "Amazon FSx for NetApp ONTAP",
    "Amazon FSx for Lustre", "Amazon S3 Glacier",
  ],
  "Database": [
    "Amazon RDS for MySQL", "Amazon RDS for PostgreSQL",
    "Amazon RDS for SQL Server", "Amazon RDS for Oracle",
    "Amazon RDS for MariaDB", "Amazon Aurora",
    "Amazon DynamoDB", "Amazon ElastiCache for Redis",
    "Amazon ElastiCache for Memcached", "Amazon DocumentDB",
    "Amazon Keyspaces", "Amazon OpenSearch Service",
    "Amazon MemoryDB for Redis", "Amazon Neptune",
    "Amazon Timestream", "Amazon QLDB",
  ],
  "Networking": [
    "Amazon VPC", "Amazon CloudFront", "Amazon Route 53",
    "Elastic Load Balancing (ALB)", "Elastic Load Balancing (NLB)",
    "Elastic Load Balancing (CLB)", "AWS WAF", "AWS Network Firewall",
    "AWS Shield Advanced", "AWS Direct Connect",
    "AWS Site-to-Site VPN", "AWS Transit Gateway",
    "NAT Gateway", "AWS Global Accelerator", "AWS PrivateLink",
  ],
  "Containers": [
    "Amazon EKS", "Amazon ECS", "AWS Fargate", "AWS App Runner",
    "Amazon ECR",
  ],
  "Serverless/API": [
    "AWS Lambda", "Amazon API Gateway", "AWS Step Functions",
    "Amazon EventBridge", "AWS App Runner",
  ],
  "Analytics/Data": [
    "Amazon Redshift", "AWS Glue", "Amazon Athena",
    "Amazon Kinesis Data Streams", "Amazon Kinesis Data Firehose",
    "Amazon MSK (Managed Kafka)", "Amazon EMR",
    "AWS Lake Formation", "Amazon QuickSight",
    "Amazon OpenSearch Service", "AWS Data Exchange",
  ],
  "GPU/ML": [
    "Amazon EC2 (P-instances, GPU)", "Amazon EC2 (G-instances, GPU)",
    "Amazon EC2 (Inf2, AWS Inferentia)", "Amazon EC2 (Trn1, AWS Trainium)",
    "Amazon SageMaker", "Amazon Bedrock",
    "Amazon Rekognition", "Amazon Comprehend",
    "Amazon Lex", "Amazon Translate", "Amazon Textract",
    "Amazon Polly",
  ],
  "Security/Identity": [
    "AWS IAM", "AWS IAM Identity Center",
    "AWS Secrets Manager", "AWS KMS",
    "AWS Certificate Manager", "AWS Directory Service",
    "Amazon GuardDuty", "AWS Security Hub",
    "AWS Inspector", "AWS Config", "AWS CloudTrail",
  ],
  "Other": [
    "Amazon CloudWatch", "AWS CloudFormation",
    "AWS Systems Manager", "AWS Backup",
    "Amazon SNS", "Amazon SQS", "Amazon MQ",
    "AWS CodePipeline", "AWS CodeBuild", "AWS CodeDeploy",
    "Amazon WorkSpaces", "Amazon AppStream 2.0",
  ],
};

// ── Region Selector Init ──────────────────────────────────────────────────
function initRegionSelector() {
  if (!regionSelect) return;
  regionSelect.innerHTML = "";
  REGIONS.sort((a, b) => a.label.localeCompare(b.label)).forEach(r => {
    const o = document.createElement("option");
    o.value = r.code;
    const pct = r.multiplier > 1.0 ? ` (+${Math.round((r.multiplier - 1) * 100)}%)` : "";
    o.textContent = `${r.label}${pct}`;
    if (r.code === state.region) o.selected = true;
    regionSelect.appendChild(o);
  });

  regionSelect.addEventListener("change", () => {
    const newRegion = regionSelect.value;
    const regionObj = REGIONS.find(r => r.code === newRegion);
    state.region = newRegion;
    state.regionMultiplier = regionObj ? regionObj.multiplier : 1.0;

    // If we have analysis results, rescale prices client-side
    if (currentMappings.length > 0) {
      rescalePricesClientSide();
    }
  });
}

function rescalePricesClientSide() {
  const newMult = state.regionMultiplier;
  currentMappings.forEach(m => {
    if (m._manual) return; // skip manual entries
    const baseMo = m.base_monthly_usd || m.monthly_estimate_usd;
    m.monthly_estimate_usd = Math.round(baseMo * newMult * 100) / 100;
    m.selected_monthly_usd = m.monthly_estimate_usd;
    // Also rescale alternatives
    if (m.alternatives) {
      m.alternatives.forEach(alt => {
        if (alt.base_monthly_usd !== undefined) {
          alt.monthly_usd = Math.round(alt.base_monthly_usd * newMult * 100) / 100;
        }
      });
    }
  });
  renderBOM();
  renderCompareReport();
}

// ── Tabs ──────────────────────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => {
      t.classList.remove("active");
      t.setAttribute("aria-selected", "false");
    });
    tab.classList.add("active");
    tab.setAttribute("aria-selected", "true");
    const target = tab.dataset.tab;
    document.getElementById("tab-file").classList.toggle("hidden", target !== "file");
    document.getElementById("tab-text").classList.toggle("hidden", target !== "text");
    updateAnalyzeButton();
  });
});

// ── File Drop Zone ────────────────────────────────────────────────────────
if (dropZone && fileInput) {
  dropZone.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") fileInput.click(); });
  dropZone.addEventListener("dragover", e => { e.preventDefault(); dropZone.classList.add("dragover"); });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
  dropZone.addEventListener("drop", e => {
    e.preventDefault(); dropZone.classList.remove("dragover");
    const file = e.dataTransfer.files[0];
    if (file) setSelectedFile(file);
  });
  fileInput.addEventListener("change", () => { if (fileInput.files[0]) setSelectedFile(fileInput.files[0]); });
}
if (clearFileBtn) {
  clearFileBtn.addEventListener("click", () => {
    selectedFile = null; fileInput.value = "";
    fileSelectedInfo.classList.add("hidden");
    updateAnalyzeButton();
  });
}

function setSelectedFile(file) {
  selectedFile = file;
  selectedFilename.textContent = `${file.name} (${formatBytes(file.size)})`;
  fileSelectedInfo.classList.remove("hidden");
  updateAnalyzeButton();
}

if (textInput) textInput.addEventListener("input", updateAnalyzeButton);

function updateAnalyzeButton() {
  const activeTab = document.querySelector(".tab.active")?.dataset.tab;
  analyzeBtn.disabled = activeTab === "file" ? !selectedFile : textInput.value.trim().length < 20;
}

// ── Analyze ───────────────────────────────────────────────────────────────
if (analyzeBtn) analyzeBtn.addEventListener("click", runAnalysis);

async function runAnalysis() {
  setLoading(true);
  hideError();
  resultSection.classList.add("hidden");
  bomSection.classList.add("hidden");
  compareSection.style.display = "none";

  try {
    const activeTab = document.querySelector(".tab.active")?.dataset.tab;
    const result = activeTab === "file" ? await analyzeFile() : await analyzeText();
    state.analysisResult = result;
    if (activeTab === "text") {
      state.originalText = textInput.value.trim();
    }
    renderResults(result);
  } catch (err) {
    showError(err.message || "An unexpected error occurred.");
  } finally {
    setLoading(false);
  }
}

async function analyzeFile() {
  const formData = new FormData();
  formData.append("file", selectedFile);
  formData.append("region", state.region);
  // Include extra_context if user filled missing-info
  if (Object.keys(state.missingInfoValues).length > 0) {
    formData.append("extra_context", JSON.stringify(state.missingInfoValues));
  }
  const resp = await fetch("/api/analyze", { method: "POST", body: formData });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || "Server error");
  return data;
}

async function analyzeText() {
  const body = {
    text: textInput.value.trim(),
    filename: "Manual Input",
    region: state.region,
  };
  // Include extra_context if user filled missing-info
  if (Object.keys(state.missingInfoValues).length > 0) {
    body.extra_context = state.missingInfoValues;
  }
  const resp = await fetch("/api/analyze-text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || "Server error");
  return data;
}

// ── Render Results ────────────────────────────────────────────────────────
function renderResults(data) {
  currentMappings = (data.mappings || []).map(m => ({ ...m, _manual: false }));
  state.bomRows = currentMappings;

  // Meta chips
  resultMeta.innerHTML = "";
  appendChip(resultMeta, `📂 ${data.filename || "Unknown"}`, "chip-platform");
  appendChip(resultMeta, `Source: ${platformLabel(data.source_platform)}`, "chip-platform");
  appendChip(resultMeta, `Confidence: ${data.overall_confidence?.replace("_", " ").toUpperCase()}`,
    `chip-confidence-${data.overall_confidence}`);
  appendChip(resultMeta, `${currentMappings.length} service area(s) identified`, "chip-platform");
  appendChip(resultMeta, `Region: ${data.region_label || data.region}`, "chip-platform");
  const summaryChip = document.createElement("div");
  summaryChip.className = "meta-chip chip-summary";
  summaryChip.textContent = data.summary || "";
  resultMeta.appendChild(summaryChip);

  // Missing info form
  renderMissingInfoForm(data.missing_info || [], data.overall_confidence);

  resultSection.classList.remove("hidden");
  renderBOM();
  renderCompareReport();
}

function renderMissingInfoForm(missingInfo, confidence) {
  if (missingInfo.length === 0) {
    missingBox.classList.add("hidden");
    return;
  }

  missingBox.classList.remove("hidden");
  missingList.innerHTML = "";

  // Warning banner for needs_info
  const banner = confidence === "needs_info"
    ? `<div class="missing-warning-banner">⚠️ Several critical details are missing. Please fill in the fields below for a more accurate estimate.</div>`
    : "";

  let formHtml = banner + `<div class="missing-info-form">`;
  missingInfo.forEach((item, idx) => {
    const existingVal = state.missingInfoValues[item] || "";
    formHtml += `
      <div class="missing-field">
        <label for="missing-input-${idx}" class="missing-field-label">${escHtml(item)}</label>
        <input type="text" id="missing-input-${idx}" class="missing-field-input"
               data-field="${escHtml(item)}" value="${escHtml(existingVal)}"
               placeholder="Enter value..." aria-label="${escHtml(item)}" />
      </div>`;
  });
  formHtml += `</div>
    <button class="btn btn-primary reanalyze-btn" id="reanalyze-btn">
      <span class="btn-icon-l">🔄</span> Re-analyze with Additional Info
    </button>`;

  missingList.innerHTML = formHtml;

  // Expand or collapse based on confidence
  if (confidence === "needs_info") {
    missingBox.classList.add("expanded");
    missingBox.classList.remove("collapsed-info");
  } else if (confidence === "medium") {
    missingBox.classList.add("collapsed-info");
    missingBox.classList.remove("expanded");
  }

  // Wire up re-analyze button
  const reanalyzeBtn = document.getElementById("reanalyze-btn");
  if (reanalyzeBtn) {
    reanalyzeBtn.addEventListener("click", handleReanalyze);
  }

  // Wire up click-to-expand on collapsed state
  missingBox.addEventListener("click", () => {
    if (missingBox.classList.contains("collapsed-info")) {
      missingBox.classList.remove("collapsed-info");
      missingBox.classList.add("expanded");
    }
  });
}

async function handleReanalyze() {
  // Collect values from missing-info inputs
  const inputs = missingList.querySelectorAll(".missing-field-input");
  state.missingInfoValues = {};
  inputs.forEach(input => {
    const field = input.dataset.field;
    const val = input.value.trim();
    if (val) {
      state.missingInfoValues[field] = val;
    }
  });

  if (Object.keys(state.missingInfoValues).length === 0) {
    showError("Please fill in at least one field before re-analyzing.");
    return;
  }

  // Re-run analysis
  setLoading(true);
  hideError();

  try {
    const activeTab = document.querySelector(".tab.active")?.dataset.tab;
    let result;
    if (activeTab === "file" && selectedFile) {
      result = await analyzeFile();
    } else if (state.originalText) {
      const body = {
        text: state.originalText,
        filename: "Manual Input",
        region: state.region,
        extra_context: state.missingInfoValues,
      };
      const resp = await fetch("/api/analyze-text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "Server error");
      result = data;
    } else {
      result = await analyzeText();
    }
    state.analysisResult = result;
    renderResults(result);
  } catch (err) {
    showError(err.message || "Re-analysis failed.");
  } finally {
    setLoading(false);
  }
}

function appendChip(parent, text, cls) {
  const chip = document.createElement("div");
  chip.className = `meta-chip ${cls}`;
  chip.textContent = text;
  parent.appendChild(chip);
}

function platformLabel(p) {
  return { azure: "Microsoft Azure", gcp: "Google Cloud", onprem: "On-Premises", generic: "Generic" }[p] || p;
}

// ── BOM Rendering ─────────────────────────────────────────────────────────
function renderBOM() {
  bomWrapper.innerHTML = "";

  currentMappings.forEach((mapping, index) => {
    const clone = bomRowTemplate.content.cloneNode(true);
    const row = clone.querySelector(".bom-row");
    row.dataset.index = index;
    if (mapping._manual) row.classList.add("manual-row");
    if (mapping.confidence === "needs_info") row.classList.add("needs-info-row");

    // Header
    row.querySelector(".bom-category-badge").textContent = mapping.category;
    row.querySelector(".bom-service-name").textContent = mapping.service_name;

    const conf = row.querySelector(".bom-confidence");
    conf.textContent = confidenceLabel(mapping.confidence);
    conf.className = `bom-confidence confidence-${mapping.confidence}`;

    // Toggle expand/collapse
    const header  = row.querySelector(".bom-row-header");
    const body    = row.querySelector(".bom-row-body");
    const toggleBtn = row.querySelector(".bom-toggle");

    header.addEventListener("click", e => {
      if (e.target.closest(".bom-remove")) return; // don't toggle on remove click
      const isOpen = !body.classList.contains("collapsed");
      body.classList.toggle("collapsed", isOpen);
      toggleBtn.classList.toggle("open", !isOpen);
      toggleBtn.setAttribute("aria-expanded", String(!isOpen));
    });

    // ── Remove button ────────────────────────────────────────────────────
    const removeBtn = row.querySelector(".bom-remove");
    removeBtn.addEventListener("click", e => {
      e.stopPropagation();
      currentMappings.splice(index, 1);
      renderBOM();
      renderCompareReport();
    });

    // Body
    row.querySelector(".bom-spec-text").textContent = mapping._manual
      ? `[Manually added] ${mapping.notes || ""}`
      : `[${mapping.source_platform || ""}] ${mapping.notes || mapping.raw_description || ""}`;

    // Reasoning/justification panel
    if (mapping.reasoning || mapping.extracted_requirement) {
      const reasonDiv = document.createElement("div");
      reasonDiv.className = "bom-reasoning";
      let reasonHtml = "";
      if (mapping.extracted_requirement) {
        reasonHtml += `<div class="reason-extract"><strong>📄 From spec:</strong> <span class="reason-quote">"${escHtml(mapping.extracted_requirement.substring(0, 300))}"</span></div>`;
      }
      if (mapping.reasoning) {
        reasonHtml += `<div class="reason-why"><strong>💡 Why this service:</strong> ${escHtml(mapping.reasoning)}</div>`;
      }
      reasonDiv.innerHTML = reasonHtml;
      const specText = row.querySelector(".bom-spec-text");
      specText.parentNode.insertBefore(reasonDiv, specText.nextSibling);
    }
    // Quantity
    const qtyInput = row.querySelector(".ctrl-qty");
    qtyInput.value = mapping.selected_quantity || mapping.quantity || 1;
    qtyInput.addEventListener("input", () => {
      currentMappings[index].selected_quantity = Math.max(1, parseInt(qtyInput.value) || 1);
      updateRowCost(row, index);
      updateTotals();
      renderCompareReport();
    });

    // Type selector — use service_types from server if available
    const typeSelect = row.querySelector(".ctrl-type");
    const typeOptions = (mapping.service_types && mapping.service_types.length > 0)
      ? mapping.service_types
      : [];
    // Always include the recommended type first
    const recType = mapping.recommended_type;
    const recOpt = document.createElement("option");
    recOpt.value = recType; recOpt.textContent = formatSkuOption(recType, true);
    recOpt.selected = true;
    typeSelect.appendChild(recOpt);
    // Add service_types from server with specs preview
    typeOptions.forEach(t => {
      if (t !== recType) {
        const o = document.createElement("option");
        o.value = t; o.textContent = formatSkuOption(t, false);
        typeSelect.appendChild(o);
      }
    });
    // Add alternatives as options too
    (mapping.alternatives || []).forEach(alt => {
      if (alt.type !== recType && !typeOptions.includes(alt.type)) {
        const o = document.createElement("option");
        o.value = alt.type; o.textContent = formatSkuOption(alt.type, false);
        typeSelect.appendChild(o);
      }
    });

    typeSelect.addEventListener("change", () => {
      currentMappings[index].selected_type = typeSelect.value;
      const matched = (mapping.alternatives || []).find(a => a.type === typeSelect.value);
      currentMappings[index].selected_monthly_usd = matched ? matched.monthly_usd : mapping.monthly_estimate_usd;
      updateRowCost(row, index);
      updateTotals();
      // Update SKU specs panel without re-rendering entire BOM
      updateSkuSpecsPanel(row, typeSelect.value, mapping);
      renderCompareReport();
    });

    // Pricing model selector
    const pricingSelect = row.querySelector(".ctrl-pricing");
    (mapping.pricing_options || ["On-Demand"]).forEach(opt => {
      const o = document.createElement("option");
      o.value = opt; o.textContent = opt;
      if (opt === (mapping.selected_pricing || mapping.pricing_options?.[0])) o.selected = true;
      pricingSelect.appendChild(o);
    });

    pricingSelect.addEventListener("change", () => {
      currentMappings[index].selected_pricing = pricingSelect.value;
      const base = mapping.monthly_estimate_usd;
      currentMappings[index].selected_monthly_usd = applyPricingDiscount(base, pricingSelect.value, mapping.recommended_type);
      updateRowCost(row, index);
      updateTotals();
      renderCompareReport();
    });

    // Region selector in row — populate from REGIONS
    const regionRowSelect = row.querySelector(".ctrl-region");
    if (regionRowSelect) {
      regionRowSelect.innerHTML = "";
      REGIONS.sort((a, b) => a.label.localeCompare(b.label)).forEach(r => {
        const o = document.createElement("option");
        o.value = r.code;
        o.textContent = `${r.code} (${r.label})`;
        if (r.code === state.region) o.selected = true;
        regionRowSelect.appendChild(o);
      });
    }

    // Alternatives chips
    const altsList = row.querySelector(".alts-list");
    (mapping.alternatives || []).forEach(alt => {
      const chip = document.createElement("button");
      chip.className = "alt-chip";
      chip.textContent = `${alt.label} — $${fmtUSD(alt.monthly_usd)}/mo`;
      chip.title = `Type: ${alt.type}`;
      chip.addEventListener("click", () => {
        let found = false;
        for (const opt of typeSelect.options) { if (opt.value === alt.type) { opt.selected = true; found = true; break; } }
        if (!found) {
          const o = document.createElement("option");
          o.value = alt.type; o.textContent = formatSkuOption(alt.type, false); o.selected = true;
          typeSelect.appendChild(o);
        }
        currentMappings[index].selected_type = alt.type;
        currentMappings[index].selected_monthly_usd = alt.monthly_usd;
        altsList.querySelectorAll(".alt-chip").forEach(c => c.classList.remove("selected"));
        chip.classList.add("selected");
        updateRowCost(row, index);
        updateTotals();
        updateSkuSpecsPanel(row, alt.type, mapping);
        renderCompareReport();
      });
      altsList.appendChild(chip);
    });

    // Missing info
    const rowMissing = row.querySelector(".row-missing");
    const missingItemsEl = row.querySelector(".missing-items");
    if ((mapping.missing_info || []).length > 0) {
      missingItemsEl.innerHTML = mapping.missing_info.map(m => `<li>${escHtml(m)}</li>`).join("");
      rowMissing.classList.remove("hidden");
    }

    // SKU Specs comparison panel
    const specsHtml = buildSkuSpecsHtml(mapping);
    if (specsHtml) {
      const specsDiv = document.createElement("div");
      specsDiv.className = "sku-specs-panel";
      specsDiv.innerHTML = specsHtml;
      const costPreview = row.querySelector(".cost-preview");
      costPreview.parentNode.insertBefore(specsDiv, costPreview);
    }

    updateRowCost(row, index);

    const calcLink = row.querySelector(".calc-link");
    calcLink.href = mapping.aws_calculator_url || "https://calculator.aws/#/createCalculator";
    calcLink.target = "_blank";
    calcLink.rel = "noopener";

    bomWrapper.appendChild(clone);
  });

  updateTotals();
  bomSection.classList.remove("hidden");
}

function buildTypeOptions(mapping) {
  const opts = [{ value: mapping.recommended_type, label: `${mapping.recommended_type} (Recommended)` }];
  (mapping.alternatives || []).forEach(alt => {
    if (alt.type !== mapping.recommended_type) opts.push({ value: alt.type, label: alt.type });
  });
  return opts;
}

function buildSkuSpecsHtml(mapping) {
  const specs = mapping.recommended_type_specs;
  if (!specs || Object.keys(specs).length === 0) return "";

  // Extract requirement from notes for comparison
  const reqInfo = parseRequirementFromNotes(mapping.notes || "");

  let html = `<div class="specs-header">
    <span class="specs-title">📋 SKU Specs: <strong>${escHtml(mapping.selected_type || mapping.recommended_type)}</strong></span>
  </div><div class="specs-grid">`;

  // Build spec rows with comparison
  if (specs.vcpu !== undefined) {
    const meets = reqInfo.vcpu ? specs.vcpu >= reqInfo.vcpu : null;
    html += specRow("vCPU", specs.vcpu, reqInfo.vcpu, meets);
  }
  if (specs.ram_gb !== undefined) {
    const meets = reqInfo.ram_gb ? specs.ram_gb >= reqInfo.ram_gb : null;
    html += specRow("RAM", `${specs.ram_gb} GB`, reqInfo.ram_gb ? `${reqInfo.ram_gb} GB` : null, meets);
  }
  if (specs.network_gbps !== undefined) {
    html += specRow("Network", typeof specs.network_gbps === "number" ? `${specs.network_gbps} Gbps` : specs.network_gbps, null, null);
  }
  if (specs.storage !== undefined) {
    html += specRow("Storage", specs.storage, null, null);
  }
  if (specs.arch !== undefined) {
    html += specRow("Architecture", specs.arch, null, null);
  }
  if (specs.family !== undefined) {
    html += specRow("Family", specs.family, null, null);
  }
  if (specs.gpu !== undefined) {
    html += specRow("GPU", specs.gpu, null, null);
  }
  // EBS-specific
  if (specs.iops !== undefined) {
    html += specRow("IOPS", specs.iops, null, null);
  }
  if (specs.throughput_mbps !== undefined) {
    html += specRow("Throughput", specs.throughput_mbps + " MB/s", null, null);
  }
  if (specs.max_size_tb !== undefined) {
    html += specRow("Max Size", specs.max_size_tb + " TB", null, null);
  }
  // S3-specific
  if (specs.durability !== undefined) {
    html += specRow("Durability", specs.durability, null, null);
  }
  if (specs.availability !== undefined) {
    html += specRow("Availability", specs.availability, null, null);
  }
  if (specs.retrieval !== undefined) {
    html += specRow("Retrieval", specs.retrieval, null, null);
  }
  // Lambda-specific
  if (specs.ram_mb !== undefined) {
    html += specRow("Memory", `${specs.ram_mb} MB`, null, null);
  }
  if (specs.vcpu_share !== undefined) {
    html += specRow("Compute", specs.vcpu_share, null, null);
  }
  if (specs.use_case !== undefined) {
    html += specRow("Use Case", specs.use_case, null, null);
  }

  html += "</div>";
  return html;
}

function specRow(label, skuValue, reqValue, meets) {
  let indicator = "";
  if (meets === true) indicator = `<span class="spec-ok">✅</span>`;
  else if (meets === false) indicator = `<span class="spec-warn">⚠️ undersized</span>`;

  let reqCol = reqValue ? `<span class="spec-req">Required: ${escHtml(String(reqValue))}</span>` : "";

  return `<div class="spec-row">
    <span class="spec-label">${escHtml(label)}</span>
    <span class="spec-value">${escHtml(String(skuValue))}</span>
    ${reqCol}${indicator}
  </div>`;
}

function parseRequirementFromNotes(notes) {
  const result = {};
  const vcpuMatch = notes.match(/vCPU:\s*(\d+)/i);
  if (vcpuMatch && vcpuMatch[1] !== "0") result.vcpu = parseInt(vcpuMatch[1]);
  const ramMatch = notes.match(/RAM:\s*(\d+(?:\.\d+)?)/i);
  if (ramMatch && ramMatch[1] !== "0") result.ram_gb = parseFloat(ramMatch[1]);
  return result;
}

// ── Client-side SKU specs cache (loaded from server on first use) ─────────
let _skuSpecsCache = null;

async function loadSkuSpecs() {
  if (_skuSpecsCache) return _skuSpecsCache;
  try {
    const resp = await fetch("/api/sku-specs");
    const data = await resp.json();
    _skuSpecsCache = data.all_specs || {};
  } catch (e) {
    _skuSpecsCache = {};
  }
  return _skuSpecsCache;
}

// Load on init (non-blocking)
loadSkuSpecs();

function getSkuSpecsLocal(sku) {
  if (!_skuSpecsCache) return null;
  return _skuSpecsCache[sku] || null;
}

function formatSkuOption(sku, isRecommended) {
  const specs = getSkuSpecsLocal(sku);
  let label = sku;
  if (specs) {
    const parts = [];
    if (specs.vcpu) parts.push(`${specs.vcpu} vCPU`);
    if (specs.ram_gb) parts.push(`${specs.ram_gb} GB RAM`);
    if (specs.ram_mb) parts.push(`${specs.ram_mb} MB`);
    if (specs.gpu) parts.push(specs.gpu.split(" ").pop()); // just the model name
    if (parts.length > 0) label += ` — ${parts.join(", ")}`;
  }
  if (isRecommended) label += " ★";
  return label;
}

function updateSkuSpecsPanel(row, newSku, mapping) {
  const existingPanel = row.querySelector(".sku-specs-panel");
  const specs = getSkuSpecsLocal(newSku);
  const reqInfo = parseRequirementFromNotes(mapping.notes || "");

  if (!specs || Object.keys(specs).length === 0) {
    // No specs for this SKU — try fetching, or show nothing
    if (existingPanel) {
      existingPanel.innerHTML = `<div class="specs-header"><span class="specs-title">📋 SKU Specs: <strong>${escHtml(newSku)}</strong> — <em>No detailed specs available</em></span></div>`;
    }
    return;
  }

  // Build the same specs HTML with the new SKU
  let html = `<div class="specs-header">
    <span class="specs-title">📋 SKU Specs: <strong>${escHtml(newSku)}</strong></span>
  </div><div class="specs-grid">`;

  if (specs.vcpu !== undefined) {
    const meets = reqInfo.vcpu ? specs.vcpu >= reqInfo.vcpu : null;
    html += specRow("vCPU", specs.vcpu, reqInfo.vcpu, meets);
  }
  if (specs.ram_gb !== undefined) {
    const meets = reqInfo.ram_gb ? specs.ram_gb >= reqInfo.ram_gb : null;
    html += specRow("RAM", `${specs.ram_gb} GB`, reqInfo.ram_gb ? `${reqInfo.ram_gb} GB` : null, meets);
  }
  if (specs.network_gbps !== undefined) {
    html += specRow("Network", typeof specs.network_gbps === "number" ? `${specs.network_gbps} Gbps` : specs.network_gbps, null, null);
  }
  if (specs.storage !== undefined) html += specRow("Storage", specs.storage, null, null);
  if (specs.arch !== undefined) html += specRow("Architecture", specs.arch, null, null);
  if (specs.family !== undefined) html += specRow("Family", specs.family, null, null);
  if (specs.gpu !== undefined) html += specRow("GPU", specs.gpu, null, null);
  if (specs.iops !== undefined) html += specRow("IOPS", specs.iops, null, null);
  if (specs.throughput_mbps !== undefined) html += specRow("Throughput", specs.throughput_mbps + " MB/s", null, null);
  if (specs.max_size_tb !== undefined) html += specRow("Max Size", specs.max_size_tb + " TB", null, null);
  if (specs.durability !== undefined) html += specRow("Durability", specs.durability, null, null);
  if (specs.availability !== undefined) html += specRow("Availability", specs.availability, null, null);
  if (specs.retrieval !== undefined) html += specRow("Retrieval", specs.retrieval, null, null);
  if (specs.ram_mb !== undefined) html += specRow("Memory", `${specs.ram_mb} MB`, null, null);
  if (specs.vcpu_share !== undefined) html += specRow("Compute", specs.vcpu_share, null, null);
  if (specs.use_case !== undefined) html += specRow("Use Case", specs.use_case, null, null);

  html += "</div>";

  if (existingPanel) {
    existingPanel.innerHTML = html;
  } else {
    // Insert new panel
    const specsDiv = document.createElement("div");
    specsDiv.className = "sku-specs-panel";
    specsDiv.innerHTML = html;
    const costPreview = row.querySelector(".cost-preview");
    if (costPreview) costPreview.parentNode.insertBefore(specsDiv, costPreview);
  }
}

function confidenceLabel(c) {
  return { high: "✅ High", medium: "⚠️ Medium", needs_info: "❓ Needs Info", low: "🔴 Low" }[c] || c;
}

function applyPricingDiscount(base, model, instanceType) {
  const modelLower = model.toLowerCase();
  if (modelLower.includes("spot"))                        return base * 0.30;
  if (modelLower.includes("3yr") || modelLower.includes("3-year")) return base * 0.55;
  if (modelLower.includes("1yr") || modelLower.includes("1-year")) return base * 0.70;
  if (modelLower.includes("savings"))                     return base * 0.66;
  if (modelLower.includes("graviton"))                    return base * 0.80;
  if (modelLower.includes("serverless"))                  return base * 0.90;
  if (modelLower.includes("aurora serverless"))           return base * 0.85;
  return base;
}

function updateRowCost(row, index) {
  const m = currentMappings[index];
  const monthly = m.selected_monthly_usd !== undefined ? m.selected_monthly_usd : m.monthly_estimate_usd;
  row.querySelector(".item-cost").textContent = `$${fmtUSD(monthly)} / mo`;
}

function updateTotals() {
  let monthly = 0;
  currentMappings.forEach(m => {
    monthly += m.selected_monthly_usd !== undefined ? m.selected_monthly_usd : m.monthly_estimate_usd;
  });
  totalMonthly.textContent = `$${fmtUSD(monthly)}`;
  totalAnnual.textContent  = `$${fmtUSD(monthly * 12)}`;
  bomTotalBadge.textContent = `$${fmtUSD(monthly)} / mo`;

  // Update region label in disclaimer
  const regionObj = REGIONS.find(r => r.code === state.region);
  const disclaimer = document.querySelector(".price-disclaimer");
  if (disclaimer && regionObj) {
    disclaimer.innerHTML = `⚠️ Prices are estimates based on public AWS on-demand rates (${regionObj.label}).
      Verify with the <a href="https://calculator.aws/pricing/2/home" target="_blank" rel="noopener">official AWS Pricing Calculator</a>.`;
  }
}

// ── Comparative Report ────────────────────────────────────────────────────
function renderCompareReport() {
  if (currentMappings.length === 0) {
    compareSection.style.display = "none";
    return;
  }

  compareTbody.innerHTML = "";
  let totalMo = 0;

  currentMappings.forEach((m, i) => {
    const monthly = m.selected_monthly_usd !== undefined ? m.selected_monthly_usd : m.monthly_estimate_usd;
    totalMo += monthly;

    const confClass = `compare-conf-${m.confidence}`;
    const confText  = { high: "✅ High", medium: "⚠️ Medium", needs_info: "❓ Needs Info", low: "🔴 Low" }[m.confidence] || m.confidence;

    // Original spec text — use notes for manual rows
    const specText = m._manual
      ? `Manually added${m.notes ? ": " + m.notes : ""}`
      : (m.notes || m.raw_description || "—");

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td style="color:var(--text-secondary);font-size:12px;">${i + 1}</td>
      <td><span class="bom-category-badge" style="background:var(--aws-dark);color:#fff;font-size:11px;padding:2px 8px;border-radius:12px;">${escHtml(m.category)}</span></td>
      <td class="compare-spec-cell">${escHtml(specText.substring(0, 180))}${specText.length > 180 ? "…" : ""}</td>
      <td class="compare-arrow">→</td>
      <td><span class="compare-aws-service">${escHtml(m.service_name)}</span></td>
      <td class="compare-sku">${escHtml(m.selected_type || m.recommended_type || "—")}</td>
      <td><span style="font-size:12px;">${escHtml(m.selected_pricing || m.pricing_options?.[0] || "On-Demand")}</span></td>
      <td style="font-weight:700;color:var(--aws-dark);">$${fmtUSD(monthly)}</td>
      <td><span class="${confClass}">${confText}</span></td>
    `;
    compareTbody.appendChild(tr);
  });

  compareTotalEl.textContent = `$${fmtUSD(totalMo)}`;
  compareSection.style.display = "block";
}

// ── Add Service Modal ─────────────────────────────────────────────────────
function populateServiceDropdown(category) {
  mService.innerHTML = "";
  (AWS_CATALOGUE[category] || AWS_CATALOGUE["Other"]).forEach(svc => {
    const o = document.createElement("option");
    o.value = svc; o.textContent = svc;
    mService.appendChild(o);
  });
}

// Init category dropdown
if (mCategory && mService) {
  populateServiceDropdown(mCategory.value);
  mCategory.addEventListener("change", () => populateServiceDropdown(mCategory.value));
}

if (addServiceBtn) addServiceBtn.addEventListener("click", openModal);
if (modalClose) modalClose.addEventListener("click",  closeModal);
if (modalCancel) modalCancel.addEventListener("click", closeModal);
if (modalBackdrop) modalBackdrop.addEventListener("click", e => { if (e.target === modalBackdrop) closeModal(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });

function openModal() {
  // Reset fields
  mCategory.value = "Compute";
  populateServiceDropdown("Compute");
  mSku.value     = "";
  mQty.value     = "1";
  mUnit.value    = "instance";
  mPricing.value = "On-Demand";
  mCost.value    = "";
  mNotes.value   = "";
  modalBackdrop.classList.remove("hidden");
  mSku.focus();
}

function closeModal() {
  modalBackdrop.classList.add("hidden");
}

if (modalConfirm) modalConfirm.addEventListener("click", () => {
  const category    = mCategory.value;
  const serviceName = mService.value;
  const sku         = mSku.value.trim() || serviceName;
  const qty         = Math.max(1, parseInt(mQty.value) || 1);
  const unit        = mUnit.value.trim() || "instance";
  const pricing     = mPricing.value;
  const cost        = parseFloat(mCost.value) || 0;
  const notes       = mNotes.value.trim();

  const newMapping = {
    category,
    service_name:         serviceName,
    service_code:         "Manual",
    recommended_type:     sku,
    selected_type:        sku,
    description:          notes || `Manually added ${serviceName}`,
    quantity:             qty,
    selected_quantity:    qty,
    unit,
    confidence:           "high",
    missing_info:         [],
    alternatives:         [],
    pricing_options:      ["On-Demand", "Spot", "Reserved 1yr", "Reserved 3yr", "Savings Plans", "Graviton (ARM)", "Pay-per-use"],
    selected_pricing:     pricing,
    monthly_estimate_usd: cost,
    base_monthly_usd:     cost,
    selected_monthly_usd: cost,
    aws_calculator_url:   "https://calculator.aws/pricing/2/home",
    raw_description:      notes || `Manually added: ${serviceName}`,
    notes:                notes || `Manually added: ${serviceName} — ${sku}`,
    source_platform:      "manual",
    _manual:              true,
  };

  currentMappings.push(newMapping);
  closeModal();
  renderBOM();
  renderCompareReport();
});

// ── Export ────────────────────────────────────────────────────────────────
if (exportCsvBtn) exportCsvBtn.addEventListener("click",  () => exportBOM("csv"));
if (exportXlsxBtn) exportXlsxBtn.addEventListener("click", () => exportBOM("excel"));

async function exportBOM(format) {
  if (currentMappings.length === 0) return;
  const btn = format === "csv" ? exportCsvBtn : exportXlsxBtn;
  const origText = btn.textContent;
  btn.textContent = "Exporting…";
  btn.disabled = true;

  try {
    const resp = await fetch(`/api/export/${format}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mappings: currentMappings,
        project_name: projectName.value.trim() || "AWS BOM",
        region: state.region
      })
    });

    if (!resp.ok) { const err = await resp.json(); showError(err.error || "Export failed."); return; }

    const blob = await resp.blob();
    const ext = format === "csv" ? "csv" : "xlsx";
    const safeName = (projectName.value.trim() || "aws-bom").replace(/[^a-zA-Z0-9-_]/g, "_");
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${safeName}.${ext}`;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  } catch (err) {
    showError(`Export error: ${err.message}`);
  } finally {
    btn.textContent = origText; btn.disabled = false;
  }
}

// ── AWS Calculator ────────────────────────────────────────────────────────
const calcBtn = document.getElementById("aws-calc-btn");
if (calcBtn) {
  calcBtn.addEventListener("click", async () => {
    try {
      const resp = await fetch("/api/pricing-calculator-url", { method: "POST" });
      const data = await resp.json();
      window.open(data.url, "_blank");
    } catch (err) {
      window.open("https://calculator.aws/pricing/2/home", "_blank");
    }
  });
}

// ── UI Helpers ────────────────────────────────────────────────────────────
function setLoading(on) {
  loading.classList.toggle("hidden", !on);
  analyzeBtn.disabled = on;
}

function showError(msg) {
  errorMsg.textContent = msg;
  errorBox.classList.remove("hidden");
}

function hideError() { errorBox.classList.add("hidden"); }

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function fmtUSD(n) {
  return Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Init ──────────────────────────────────────────────────────────────────
try {
  initRegionSelector();
  updateAnalyzeButton();
  console.log("[AWS Spec Analyzer] UI initialized successfully.");
} catch (e) {
  console.error("[AWS Spec Analyzer] Init error:", e);
}
