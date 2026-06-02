import os, sys

# Load env file
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
with open(env_path) as f:
    for line in f:
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ[k.strip()] = v.strip().strip("'\"")

api_key = os.environ.get("GROQ_API_KEY", "")
print(f"Key prefix: {api_key[:15]}...")

# Try a quick generate call with Groq models
models_to_try = [
    "llama-3.3-70b-versatile",
    "llama3-70b-8192",
    "mixtral-8x7b-32768",
    "llama3-8b-8192",
]

print("\n=== Testing Groq model availability ===")
try:
    from langchain_groq import ChatGroq
    for model in models_to_try:
        try:
            llm = ChatGroq(model=model, max_retries=0, temperature=0.0)
            result = llm.invoke("Say OK")
            print(f"  [OK] {model}: {str(result.content)[:40]}")
            break  # Stop at first working model
        except Exception as e:
            err = str(e)[:80]
            print(f"  [FAIL] {model}: {err}")
except Exception as e:
    print(f"langchain-groq import error: {e}")
