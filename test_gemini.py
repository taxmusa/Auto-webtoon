import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    # Try to find it in .env file directly if load_dotenv fails somehow
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

genai.configure(api_key=api_key)

model_name = "gemini-3.0-flash"
print(f"Testing model: {model_name}")

try:
    model = genai.GenerativeModel(model_name)
    response = model.generate_content("Hello, can you hear me? Answer in one word.")
    print("Success! Response:", response.text)
except Exception as e:
    print(f"Failed to generate content: {e}")
    # Try with 2.0-flash as fallback check
    print("\nTrying gemini-2.0-flash...")
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content("Hello")
        print("gemini-2.0-flash works.")
    except Exception as e2:
        print(f"gemini-2.0-flash also failed: {e2}")
