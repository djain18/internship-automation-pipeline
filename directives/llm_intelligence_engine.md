# LLM Intelligence Engine Documentation

**Component:** `execution/llm_post_analyzer.py`  
**Model:** `gemini-2.5-flash` (Cost-efficient, JSON-native)

## 1. Core Objectives
The LLM engine acts as a "Human-in-the-Loop" automated verification layer. It processes raw text from LinkedIn Posts to ensure high-quality, safe, and structured data.

### Key Functions:
1.  **Freshness Verification**: Deciphers "Posted 2 days ago" vs actual dates, ignoring "Promoted" timestamps.
2.  **Entity Extraction**:
    *   **Role**: Converts generic "Intern / Hiring" terms into specific roles (e.g., "React Developer Intern").
    *   **Company**: Extracts the hiring entity name from the post body.
    *   **Location**: Identifies specific City/Country or "Remote".
3.  **Spam & Scam Shield**: rigorous filtering of paid/fake internships.

---

## 2. Extraction Logic (Few-Shot Learning)
We use **Few-Shot Prompting** (providing examples in the prompt) to force the model to adhere to a strict JSON schema.

### The Prompt Strategy
*   **Role**: explicit instruction to be specific.
    *   *Bad*: "Internship"
    *   *Good*: "Full Stack Developer Intern"
*   **Company**: identifying the *hiring* company, not just the agency.
*   **Location**: extracting strict geographical data.

### Examples Provided to LLM:
> **Input:** "We are hiring React Interns at Dunder Mifflin in Scranton. Send CV to michael@dundermifflin.com"  
> **Output:** `{"role": "React Intern", "company": "Dunder Mifflin", "location": "Scranton", ...}`

> **Input:** "Looking for marketing intern. Remote role. DM me."  
> **Output:** `{"role": "Marketing Intern", "company": null, "location": "Remote", ...}`

> **Input:** "Earn 5000 daily! Simple typing job. WhatsApp 9999999999. Registration fee 500."  
> **Output:** `{"role": "Typing Job", "company": null, "is_spam_or_fake": true, "fake_reason": "Registration fee", ...}`

---

## 3. Anti-Spam & Fraud Detection
The LLM is trained to flag specific "Red Flags" immediately:

| Trigger Phrase | Verdict | Reason |
| :--- | :--- | :--- |
| "Training fee" | **REJECT** | Pay-to-work scam |
| "Security deposit" | **REJECT** | Financial risk |
| "Registration fee" | **REJECT** | Scam |
| "100% genuine" | **REJECT** | Suspicious language (over-selling) |
| "Typing job" / "Data entry" | **REJECT** | High-volume spam category |
| "Investment required" | **REJECT** | Financial scam |

---

## 4. Technical Implementation
*   **Retry Logic**: Implements exponential backoff for API limits.
*   **Fallback**: If LLM fails, defaults to "Generic Intern" but keeps the lead (Safe Fail).
*   **JSON Enforcement**: Uses `generation_config={"response_mime_type": "application/json"}` to guarantee parseable output.
