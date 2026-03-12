# How to Use Vertex AI Free Credits ($300)

You absolutely **CAN** use your Google Cloud Vertex AI credits for this task. It is actually MORE stable than the free AI Studio API key.

## Prerequisite Checklist
1. **Google Cloud Project**: You must have a GCP Project with billing enabled (to access the credits).
2. **Enable API**: Search for "Vertex AI API" in GCP Console and enable it.
3. **Install CLI**: You need `gcloud` CLI installed and authenticated on your machine.
   - Run: `gcloud auth application-default login`
   
## Code Changes Required
The current script uses `google.generativeai` (AI Studio). To use Vertex AI, we need to switch to the `vertexai` library.

**I can make these changes for you if you have `gcloud` setup.**

### Summary of Change:
```python
# OLD (Current)
import google.generativeai as genai
genai.configure(api_key="your_key")

# NEW (Vertex AI)
import vertexai
from vertexai.generative_models import GenerativeModel
vertexai.init(project="your-project-id", location="us-central1")
model = GenerativeModel("gemini-2.5-flash-lite")
```

**Recommendation:**
For now, let's run with the **10-second delay fix** on your current key. It's the simplest fix. If it's still too slow, we can switch to Vertex AI.
