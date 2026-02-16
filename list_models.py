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
    print("Error: GEMINI_API_KEY not found")
    exit(1)

client = genai.Client(api_key=api_key)

print("Listing available models...")
try:
    with open("available_models.txt", "w", encoding="utf-8") as f:
        for m in client.models.list():
            print(m.name)
            f.write(m.name + "\n")
    print("Saved to available_models.txt")
except Exception as e:
    print(f"Error listing models: {e}")
