import os
import sys
from dotenv import load_dotenv

# Add execution dir
sys.path.append(os.path.join(os.getcwd(), 'execution'))

load_dotenv()

print(f"OPENAI_API_KEY present: {'OPENAI_API_KEY' in os.environ}")
if 'OPENAI_API_KEY' in os.environ:
    print(f"Key length: {len(os.environ['OPENAI_API_KEY'])}")
    print(f"Key prefix: {os.environ['OPENAI_API_KEY'][:5]}...")

try:
    import openai
    print("OpenAI library imported successfully.")
except ImportError:
    print("OpenAI library NOT installed.")

# Import analyzer
try:
    import llm_post_analyzer
    print("Unmodified code loaded.")
    llm_post_analyzer.configure_llm()
    print(f"Configured PROVIDER: {llm_post_analyzer.PROVIDER}")
except Exception as e:
    print(f"Error importing/re-running analyzer: {e}")
