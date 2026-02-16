import sys
import threading
import time
import uvicorn

def open_browser():
    """서버 기동 후 브라우저 자동 열기 (reload 시 자식 프로세스 대기 포함)"""
    time.sleep(4)
    url = "http://127.0.0.1:8000"
    try:
        if sys.platform == "win32":
            import subprocess
            subprocess.Popen(f"start {url}", shell=True)
        else:
            import webbrowser
            webbrowser.open(url)
    except Exception:
        import webbrowser
        webbrowser.open(url)

if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

