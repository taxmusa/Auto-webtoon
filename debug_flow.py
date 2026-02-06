import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000/api/workflow"

def run_debug():
    print("1. Starting Workflow (/start)...")
    try:
        start_payload = {
            "mode": "auto",
            "keyword": "2026년 육아휴직",
            "model": "gemini-3.0-flash"
        }
        res = requests.post(f"{BASE_URL}/start", json=start_payload)
        res.raise_for_status()
        start_data = res.json()
        session_id = start_data["session_id"]
        print(f"   Success! Session ID: {session_id}")
        print(f"   Field Info: {start_data.get('field')}")
    except Exception as e:
        print(f"   Failed to start: {e}")
        return

    print("\n2. Collecting Data (/collect-data)...")
    try:
        collect_payload = {
            "session_id": session_id,
            "keyword": "2026년 육아휴직",
            "model": "gemini-3.0-flash"
        }
        res = requests.post(f"{BASE_URL}/collect-data", json=collect_payload)
        res.raise_for_status()
        collect_data = res.json()
        items = collect_data.get("items", [])
        
        print(f"   Response Status: {res.status_code}")
        print(f"   Items Count: {len(items)}")
        
        if len(items) == 0:
            print("   WARNING: Items list is empty!")
            print("   Raw Response:", res.text)
        else:
            print("   First Item Title:", items[0].get("title"))
            print("   First Item Content Preview:", items[0].get("content")[:50] + "...")
            
    except Exception as e:
        print(f"   Failed to collect data: {e}")
        if hasattr(e, 'response') and e.response:
             print("   Error Response:", e.response.text)

if __name__ == "__main__":
    run_debug()
