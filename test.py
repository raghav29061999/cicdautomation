def launch_ui():
    """
    Launch Streamlit UI (safe for python -m src.main) and allow Ctrl+C to stop it.
    """
    import signal
    import subprocess
    import sys
    from pathlib import Path

    ui_app = Path(__file__).parent / "ui" / "app.py"
    if not ui_app.exists():
        raise RuntimeError("UI entrypoint not found at src/ui/app.py")

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(ui_app),
        "--server.port=8501",
        "--server.address=localhost",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]

    # IMPORTANT:
    # - Don't exit immediately; wait on the Streamlit process
    # - Ctrl+C will now stop the app cleanly
    proc = subprocess.Popen(cmd)

    try:
        proc.wait()
    except KeyboardInterrupt:
        # Ctrl+C: terminate Streamlit cleanly
        try:
            # Windows: send CTRL_BREAK so Streamlit can shutdown
            if sys.platform.startswith("win"):
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.terminate()
        except Exception:
            pass

        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

        raise SystemExit(0)
