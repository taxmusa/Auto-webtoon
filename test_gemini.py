from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY"):
                    api_key = line.split("=")[1].strip().strip('"')
                    break
    except:
        pass

if not api_key:
    print("Error: GEMINI_API_KEY not found.")
    exit(1)

client = genai.Client(api_key=api_key)

model_name = "gemini-3.0-flash"
print(f"Testing model: {model_name}")

try:
    response = client.models.generate_content(model=model_name, contents="Hello, can you hear me? Answer in one word.")
    print("Success! Response:", response.text)
except Exception as e:
    print(f"Failed to generate content: {e}")
    print("\nTrying gemini-2.0-flash...")
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents="Hello")
        print("gemini-2.0-flash works.")
    except Exception as e2:
        print(f"gemini-2.0-flash also failed: {e2}")
