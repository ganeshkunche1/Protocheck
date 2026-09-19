# ProtoCheck — Automated Loop Engineering System

**ProtoCheck** is an AI self-check system designed to catch incorrect, unsupported, or hallucinated claims in LLM-generated responses.

The core idea is simple:

> **Generate → Verify → Repair → Re-verify**

Instead of trusting the first AI response, ProtoCheck checks the generated claims against selected evidence and identifies potential failures.

---

## Problem

Large Language Models can generate responses that sound confident and correct while containing unsupported or incorrect information.

The challenge is therefore not only generating an answer, but also verifying whether the answer is actually supported by the available context.

ProtoCheck explores an automated verification loop around LLM generation.

---

## How ProtoCheck Works

```text
User Prompt
     ↓
Source Recommendation
     ↓
Evidence Selection
     ↓
LLM Draft Generation
     ↓
Atomic Claim Extraction
     ↓
Claim-Level Verification
     ↓
 ┌───────────────┐
 │               │
PASS            FAIL
 │               │
 ↓               ↓
Final       Fix & Regenerate
Answer            ↓
              Re-verify
                  ↓
             Final Result
```

### Workflow

1. **User Prompt**  
   The user provides a question or task.

2. **Source Recommendation**  
   ProtoCheck recommends potentially relevant sources.

3. **Evidence Selection**  
   The user selects the relevant context/evidence to use for verification.

4. **Draft Generation**  
   An LLM generates the initial response.

5. **Atomic Claim Extraction**  
   The response is broken into individual claims.

6. **Claim-Level Verification**  
   Each claim is checked against the selected evidence.

7. **Failure Detection**  
   Unsupported or contradicted claims are identified.

8. **Repair / Regeneration**  
   The failed response can be regenerated using the relevant context.

9. **Re-verification**  
   The regenerated response is checked again.

---

## Failure Demonstration

### Test Prompt

```text
What is the number of straight sides of a circle?
```

### Evidence

```text
A circle is a round two-dimensional shape.
It has no straight sides and no vertices.
```

### Incorrect Draft

```text
A circle has four straight sides.
```

ProtoCheck extracts the claim:

```text
A circle has four straight sides.
```

The claim is then checked against the selected evidence.

```text
Claim
  ↓
Verification
  ↓
❌ Contradicted
  ↓
Fix & Regenerate
  ↓
Re-verification
```

This demonstrates the main purpose of the system: identifying a wrong AI-generated claim instead of simply trusting the generated response.

---

## Claim-Level Verification

ProtoCheck does not treat the complete response as one single claim.

For example:

```text
The project launched in March,
has three environments,
and supports five languages.
```

is separated into:

```text
Claim 1 → Project launched in March
Claim 2 → Project has three environments
Claim 3 → Project supports five languages
```

Each claim can then be evaluated independently against the available evidence.

---

## Loop Engineering

The main engineering idea behind ProtoCheck is what I call **Loop Engineering**.

A basic LLM workflow is:

```text
Prompt → LLM → Answer
```

ProtoCheck turns this into a verification loop:

```text
Prompt
  ↓
Generate
  ↓
Verify
  ↓
Identify Failure
  ↓
Repair
  ↓
Generate Again
  ↓
Verify Again
```

The important principle is that a regenerated answer should not automatically be trusted. It should go through verification again.

---

## Development Challenge

During development, I initially used the LLM API for multiple responsibilities:

- Answer generation
- Recommended source generation

This caused glitches and sometimes blocked the output.

I separated these responsibilities into two API paths:

```text
API 1
↓
Answer Generation

API 2
↓
Recommended Source Generation
```

This separation helped isolate the responsibilities and reduce the issue I was facing in the recommendation and generation workflow.

---

## Testing

The project was tested with multiple cases covering:

- Supported claims
- Unsupported claims
- Contradicted claims
- Intentionally incorrect factual responses
- Plausible-looking incorrect answers
- Repair and re-verification behaviour

The main failure case focuses on a confident but incorrect response that can be identified by checking it against explicit evidence.

---

## Limitations

ProtoCheck does **not** prove that an answer is universally true.

It verifies generated claims against the evidence available to the system.

Current limitations include:

- The verifier itself can make mistakes.
- Incorrect or incomplete evidence can affect verification.
- Multiple LLM calls increase token usage and cost.
- API availability can affect complete workflow execution.
- Evidence-grounded verification is not a guarantee of absolute truth.

The current implementation is a prototype focused on demonstrating the self-check loop.

---

## Tech Stack

- Python
- LLM APIs
- Source Recommendation
- Evidence Selection
- Claim Extraction
- Claim-Level Verification
- Web Application

---

## Run Locally

### 1. Clone the repository

```bash
git clone (https://github.com/ganeshkunche1/Protocheck/tree/main)
cd ProtoCheck
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

### 3. Activate the environment

**macOS / Linux**

```bash
source .venv/bin/activate
```

**Windows**

```bash
.venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure environment variables

Create a `.env` file and add the required API configuration.

**Do not commit API keys or `.env` files to GitHub.**

### 6. Run the application

```bash
python app.py
```

---

## Project Status

### Implemented

- Prompt-based interaction
- Source recommendation
- Evidence selection
- LLM response generation
- Atomic claim extraction
- Claim-level verification
- Failure identification
- Repair / regeneration workflow
- Re-verification workflow
- Web interface

### Known Constraint

The complete workflow can require multiple LLM calls. API usage, token consumption, and API availability can therefore affect complete end-to-end execution.

## Author

**Ganesh Kunche**

