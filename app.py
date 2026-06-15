"""
app.py - Flask backend for the AWS Spec Analyzer application.
Run: python app.py
Then open: http://localhost:5000
"""

import os
import json
import traceback
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import io

from parser import parse_file
from mapper import analyze_spec
from exporter import export_csv, export_excel
from mapper import get_sku_specs, get_all_sku_specs, SKU_SPECS

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

# Max upload size: 20 MB
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
# Disable static file caching during development
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

ALLOWED_EXTENSIONS = {
    "pdf", "docx", "doc", "txt", "csv", "json", "yaml", "yml",
    "xlsx", "xls", "md", "rst", "log", "conf", "ini", "toml",
    "png", "jpg", "jpeg", "bmp", "tiff", "tif", "webp",
}


def allowed_file(filename: str) -> bool:
    if "." not in filename:
        return True  # allow extension-less text files
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """
    POST /api/analyze
    Accepts multipart form data with a 'file' field.
    Optional form fields: 'region' (default: us-east-1), 'extra_context' (JSON string)
    Returns JSON analysis result.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Please attach a file."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not allowed_file(file.filename):
        return jsonify({
            "error": f"Unsupported file type. Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        }), 400

    try:
        file_bytes = file.read()
        if len(file_bytes) == 0:
            return jsonify({"error": "Uploaded file is empty."}), 400

        # Parse file to text
        text = parse_file(file.filename, file_bytes)

        if len(text.strip()) < 20:
            return jsonify({
                "error": "Could not extract meaningful text from the file. "
                         "Please ensure the file contains readable content."
            }), 422

        # Read region and extra_context from form fields
        region = request.form.get("region", "us-east-1")
        extra_context = None
        extra_context_str = request.form.get("extra_context", "")
        if extra_context_str:
            try:
                extra_context = json.loads(extra_context_str)
            except (json.JSONDecodeError, TypeError):
                pass

        # Analyze and map to AWS services
        result = analyze_spec(text, region=region, extra_context=extra_context)
        result["filename"] = file.filename
        result["text_length"] = len(text)

        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except RuntimeError as e:
        msg = str(e)
        # Surface Tesseract install instructions as a user-friendly 422
        if "Tesseract" in msg or "OCR" in msg:
            return jsonify({"error": msg}), 422
        return jsonify({"error": msg}), 500
    except Exception as e:
        return jsonify({
            "error": f"Unexpected error: {str(e)}",
            "detail": traceback.format_exc()
        }), 500


@app.route("/api/analyze-text", methods=["POST"])
def analyze_text():
    """
    POST /api/analyze-text
    Accepts JSON body: { "text": "...", "region": "us-east-1", "extra_context": {...} }
    For pasting spec text directly.
    """
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "Request body must include 'text' field."}), 400

    text = data.get("text", "").strip()
    if len(text) < 20:
        return jsonify({"error": "Please provide more text (at least 20 characters)."}), 422

    region = data.get("region", "us-east-1")
    extra_context = data.get("extra_context", None)

    try:
        result = analyze_spec(text, region=region, extra_context=extra_context)
        result["filename"] = data.get("filename", "Manual Input")
        result["text_length"] = len(text)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except RuntimeError as e:
        msg = str(e)
        if "Tesseract" in msg or "OCR" in msg:
            return jsonify({"error": msg}), 422
        return jsonify({"error": msg}), 500
    except Exception as e:
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


@app.route("/api/export/csv", methods=["POST"])
def export_csv_endpoint():
    """
    POST /api/export/csv
    Body: { "mappings": [...], "project_name": "..." }
    Returns CSV file download.
    """
    data = request.get_json(silent=True)
    if not data or "mappings" not in data:
        return jsonify({"error": "Missing 'mappings' in request body."}), 400

    try:
        csv_bytes = export_csv(data["mappings"], data.get("project_name", "AWS BOM"), data.get("region", "us-east-1"))
        return send_file(
            io.BytesIO(csv_bytes),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"{data.get('project_name', 'aws-bom').replace(' ', '_')}.csv"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/export/excel", methods=["POST"])
def export_excel_endpoint():
    """
    POST /api/export/excel
    Body: { "mappings": [...], "project_name": "..." }
    Returns Excel file download.
    """
    data = request.get_json(silent=True)
    if not data or "mappings" not in data:
        return jsonify({"error": "Missing 'mappings' in request body."}), 400

    try:
        xlsx_bytes = export_excel(data["mappings"], data.get("project_name", "AWS BOM"), data.get("region", "us-east-1"))
        return send_file(
            io.BytesIO(xlsx_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{data.get('project_name', 'aws-bom').replace(' ', '_')}.xlsx"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pricing-calculator-url", methods=["POST"])
def pricing_calculator_url():
    """
    POST /api/pricing-calculator-url
    Returns a link to the AWS Pricing Calculator.
    (The official calculator does not expose a public API for pre-populating estimates,
    so we return the base URL with guidance.)
    """
    return jsonify({
        "url": "https://calculator.aws/#/createCalculator",
        "message": "Open the AWS Pricing Calculator and manually enter your BOM items for an official estimate.",
        "note": "AWS does not provide a public API to pre-populate calculator estimates programmatically."
    })


@app.route("/api/sku-specs", methods=["GET"])
def sku_specs_endpoint():
    """
    GET /api/sku-specs?sku=m6i.large
    Returns specs for a specific SKU. Without query param, returns all specs.
    """
    sku = request.args.get("sku", "")
    if sku:
        specs = get_sku_specs(sku)
        if not specs:
            return jsonify({"error": f"No specs found for SKU: {sku}"}), 404
        return jsonify({"sku": sku, "specs": specs})
    else:
        return jsonify({"all_specs": SKU_SPECS})


@app.route("/api/sku-specs/compare", methods=["POST"])
def sku_specs_compare():
    """
    POST /api/sku-specs/compare
    Body: { "sku": "m6i.2xlarge", "requirement": { "vcpu": 8, "ram_gb": 32 } }
    Returns specs for the SKU plus a comparison against the requirement.
    """
    data = request.get_json(silent=True)
    if not data or "sku" not in data:
        return jsonify({"error": "Missing 'sku' in request body."}), 400

    sku = data["sku"]
    specs = get_sku_specs(sku)
    if not specs:
        return jsonify({"error": f"No specs found for SKU: {sku}", "sku": sku, "specs": {}}), 404

    requirement = data.get("requirement", {})
    comparison = {}

    # Compare vCPU
    if "vcpu" in specs and "vcpu" in requirement:
        req_vcpu = float(requirement["vcpu"])
        sku_vcpu = float(specs["vcpu"])
        comparison["vcpu"] = {
            "sku_value": sku_vcpu,
            "required": req_vcpu,
            "meets_requirement": sku_vcpu >= req_vcpu,
            "surplus_pct": round(((sku_vcpu - req_vcpu) / req_vcpu) * 100, 1) if req_vcpu > 0 else None
        }

    # Compare RAM
    if "ram_gb" in specs and "ram_gb" in requirement:
        req_ram = float(requirement["ram_gb"])
        sku_ram = float(specs["ram_gb"])
        comparison["ram_gb"] = {
            "sku_value": sku_ram,
            "required": req_ram,
            "meets_requirement": sku_ram >= req_ram,
            "surplus_pct": round(((sku_ram - req_ram) / req_ram) * 100, 1) if req_ram > 0 else None
        }

    # Overall fit
    all_met = all(c.get("meets_requirement", True) for c in comparison.values())
    comparison["overall_fit"] = "meets" if all_met else "undersized"

    return jsonify({
        "sku": sku,
        "specs": specs,
        "requirement": requirement,
        "comparison": comparison,
    })


if __name__ == "__main__":
    print("=" * 60)
    print("  AWS Spec Analyzer")
    print("  Running at: http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, host="0.0.0.0", port=5000)
