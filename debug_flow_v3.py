import requests
import json

BASE_URL = "http://127.0.0.1:8000/api/workflow"

def run_debug(model_name):
    print(f"\nTesting with model: {model_name}")
    try:
        start_payload = {
            "mode": "auto",
            "keyword": "2026 preivew test",
            "model": model_name
        }
        res = requests.post(f"{BASE_URL}/start", json=start_payload)
        res.raise_for_status()
        start_data = res.json()
        session_id = start_data["session_id"]
        print(f"   [Start] Success, Session ID: {session_id}")
    except Exception as e:
        print(f"   [Start] Failed: {e}")
        if hasattr(e, 'response') and e.response:
             print("   Response:", e.response.text)
        return

    try:
        collect_payload = {
            "session_id": session_id,
            "keyword": "2026 preivew test",
            "model": model_name
        }
        res = requests.post(f"{BASE_URL}/collect-data", json=collect_payload)
        res.raise_for_status()
        collect_data = res.json()
        items = collect_data.get("items", [])
        
        print(f"   [Collect] Items Count: {len(items)}")
        if len(items) > 0:
            print(f"   [Collect] First Title: {items[0].get('title')}")
        else:
            print("   [Collect] WARNING: Empty items list")

    except Exception as e:
        print(f"   [Collect] Failed: {e}")
        if hasattr(e, 'response') and e.response:
             print("   Response:", e.response.text)

if __name__ == "__main__":
    run_debug("gemini-3-flash-preview")
