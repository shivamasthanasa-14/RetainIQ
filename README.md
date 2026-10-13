# RetainIQ

### Business problem
Support teams repeatedly read similar requests, look up documentation, draft responses, and decide which cases need individual investigation.

### What it does
A support preparation and review workflow for fictional RelayOps requests. It groups specific recurring issues, prepares documentation-grounded drafts, separates exceptions, and tracks assigned follow-ups. Approval, escalation, and resolution remain employee decisions.

### Main workflow
Select a scenario → inspect workload → review prepared or live AI results → inspect the customer message and cited documents → edit, reject, escalate, or approve each ticket → assign follow-up → record resolution. Validated Excel imports enter a separate custom workspace. Approving a reply neither sends a customer message nor resolves the ticket.

### Technologies
Python, Streamlit, Pandas, SQLite, OpenPyXL, Requests, TF-IDF document retrieval, and local Ollama integration. The standard prepared demonstration replays genuine recorded model outputs for exact matching inputs.

## Run locally

Use Python 3.12 or newer. From this repository's root:

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell: use .\.venv\Scripts\Activate.ps1 instead
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the local URL printed by Streamlit. If PowerShell activation is restricted, invoke `.venv\Scripts\python.exe` directly for the pip and streamlit commands. No model or API key is required for the default demonstration. Dependencies include the existing test tooling; installing them does not run tests.

`launch.ps1` is an optional Windows convenience wrapper; the Python command above is portable. For loopback port 8511, add `--server.address 127.0.0.1 --server.port 8511` locally.

### Demonstration data
`data/scenarios/` includes three reproducible, fictional datasets of 100 requests each, spanning eight operating weeks with reference date 30 September 2026. `knowledge_base/` contains twelve fictional support documents. `data/prepared_catalog.json` retains model outputs, exact-input hashes, source references, and development review notes. All are synthetic demonstration material. SQLite reviewer workspaces are initialized locally and excluded from publication.

Prepared mode needs no model at review time. Changed or unknown requests require Live AI or manual review; recorded results are never presented as fresh inference. For Live AI, configure an existing local Ollama service and model using the variables in `.env.example`. No model download is performed by the app.

### Application preview
No final application screenshot is available in this repository. No generated or outdated interface image is presented as an actual final capture.

### Limitations
Portfolio prototype with demonstration owner selection rather than production authentication. Development review of prepared outputs is not independent human evaluation or per-ticket approval. It does not send customer email; the optional local escalation dispatcher requires explicit setup. No autonomous agent framework, public deployment, or measured time/financial savings are claimed. See [case study](CASE_STUDY.md) for the business and implementation decisions.

## Publication and hosting

Local databases, custom uploads, reviewer workspaces, secrets, caches, logs, review archives, and development outputs are excluded from Git. A fresh checkout starts from synthetic demonstration records and recreates its own SQLite state. Existing local state is retained on disk.

The Streamlit application needs a Python server and writable local storage; GitHub Pages cannot run it. Hosted SQLite files may be ephemeral, and this prototype has no production authentication or durable hosted storage configuration. Local Ollama requires a separately configured service and installed model; no model is bundled. Example environment variables are documentation only and are not automatically loaded from `.env.example`.

## Streamlit Community Cloud readiness

Deploy repository `shivamasthanasa-14/RetainIQ`, branch `main`, entry point `app.py`, with Python 3.12. Leave Prepared AI Demo Results selected. No secrets, system packages, Ollama service, or API key are needed for the default demonstration.

The existing default `RETAINIQ_WORKSPACE_MODE=session` gives each browser session an opaque, separate SQLite workspace. Do not set it to `local` in a public deployment and leave `RETAINIQ_WORKSPACE_ROOT` unset. Workspaces and reset snapshots accumulate on the ephemeral host until removed or the instance is replaced; this is a portfolio demo rather than permanent storage. Live AI cannot use the visitor's local Ollama service; an absent service is reported without crashing. The server bind and port are left to Community Cloud; locally use `--server.address 127.0.0.1 --server.port 8511` for the former loopback settings.
