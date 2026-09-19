# ProtoCheck

ProtoCheck is a local web application for checking whether factual claims in an AI-generated answer are supported by selected evidence.

It follows a simple reliability loop:

```text
Generate → Extract claims → Verify against evidence → Repair → Verify again
```

## Features

- Generate a draft answer with Gemini
- Add evidence from pasted text, text files, PDFs, or webpages
- Extract factual claims from the draft
- Mark each claim as `SUPPORTED`, `UNSUPPORTED`, or `CONTRADICTED`
- Show the evidence excerpt and reason for every verdict
- Repair unsupported claims using the selected evidence and re-verify the result
- Recommend relevant public sources using Tavily (optional)

## Tech stack

- Python and FastAPI
- Pydantic
- Jinja2, HTML, CSS, and vanilla JavaScript
- Gemini API
- Tavily Search API
- pytest

## Setup

Requirements: Python 3.10 or later.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
LLM_API_KEY=your_gemini_api_key
LLM_MODEL=gemini-3.6-flash
TAVILY_API_KEY=your_tavily_api_key
```

`TAVILY_API_KEY` is only needed for source recommendations.

## Run locally

```bash
python app.py
```

Open http://127.0.0.1:8000 in your browser.

## Test

```bash
pytest -q
```

## Important note

Verification is evidence-bounded: a `SUPPORTED` verdict means the selected evidence supports the claim. It does not make a broader claim about global factual correctness.

## Project structure

```text
app.py                 FastAPI application entry point
core/                  Claim extraction, verification, repair, and generation logic
evidence/              Evidence ingestion, processing, and storage
routes/                API routes
templates/ and static/ Web interface
tests/                 Automated tests
```
