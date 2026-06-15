# AWS Spec Analyzer & BOM Builder

A local web application that reads technical specifications from any file format and maps the requirements to AWS services, producing a Bill of Materials (BOM) with pricing estimates.

## Features

- **Multi-format file parsing**: PDF, DOCX, TXT, CSV, JSON, YAML, XLSX, Markdown, and more
- **Vendor translation**: Automatically translates Microsoft Azure, Google Cloud, and on-premises specs to AWS equivalents
- **Smart AWS mapping**: Detects compute, storage, database, networking, GPU/ML, containers, serverless, analytics, and security requirements
- **Interactive BOM builder**: Adjust quantity, service type, and pricing model per line item
- **Pricing options per service**: On-Demand, Spot, Reserved (1yr/3yr), Savings Plans, Graviton (ARM)
- **Confidence scoring**: High / Medium / Needs Info — flags missing details
- **Export to CSV and Excel (.xlsx)** with styled BOM, service details sheet, and pricing disclaimer
- **Link to official AWS Pricing Calculator** for verified estimates

## Quick Start

### Prerequisites
- Python 3.9+
- All dependencies auto-installed via pip
- **For image OCR (PNG/JPG):** [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) must be installed separately and on your system PATH

### Install & Run

```
pip install flask flask-cors python-docx PyPDF2 openpyxl pyyaml requests Pillow pytesseract
python app.py
```

Or on Windows, double-click `start.bat`.

Then open your browser to: **http://localhost:5000**

## Usage

1. **Upload a file** or paste spec text directly
2. Set a **project name** for your export
3. Click **Analyze Specification**
4. Review the **Analysis Result** — check confidence and missing info prompts
5. In the **BOM**, expand each service row to:
   - Change quantity
   - Switch between instance types / SKUs
   - Choose pricing model (On-Demand, Spot, Graviton, Reserved, etc.)
   - Pick an alternative service
6. **Export** to CSV or Excel, or open the AWS Pricing Calculator link

## Supported Spec Types

| Source | Examples |
|--------|---------|
| On-Premises | Physical servers, VMware, NAS/SAN, Oracle DB, Cisco networking |
| Microsoft Azure | VMs, AKS, Azure SQL, Cosmos DB, Blob Storage, Azure Functions |
| Google Cloud | GCE, GKE, BigQuery, Cloud SQL, Cloud Run, Vertex AI |
| Generic | Any spec mentioning vCPUs, RAM, storage, databases, etc. |
| Images (PNG/JPG) | Screenshots of specs, architecture diagrams with text, scanned docs |

> **Image OCR note:** Requires [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed on your system.
> Download the Windows installer, install it, then add `C:\Program Files\Tesseract-OCR` to your system PATH.
> The app will show a clear error message if Tesseract is missing.

## File Structure

```
aws-spec-analyzer/
├── app.py          Flask backend + API endpoints
├── parser.py       File parsing (PDF, DOCX, XLSX, JSON, YAML, etc.)
├── mapper.py       Spec → AWS service mapping engine
├── exporter.py     CSV and Excel export generation
├── templates/
│   └── index.html  Single-page web UI
├── static/
│   ├── style.css
│   └── app.js
└── start.bat       Windows quick-start script
```

## Disclaimer

Pricing estimates are based on public AWS on-demand rates for the us-east-1 region and are for guidance only. Always verify with the [official AWS Pricing Calculator](https://calculator.aws/pricing/2/home).
