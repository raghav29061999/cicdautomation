def run_scenarios(
    parsed_scenarios: List[Dict[str, Any]],
    *,
    base_url: str | None = None,
    artifacts_dir: str | None = None,
    run_dir: str | None = None,
    config: Dict[str, Any] | None = None,
) -> List[ScenarioResult]:
    """
    Entry point used by pipeline / UI / executor node.

    Accepts extra args (run_dir, config) to stay compatible with pipeline calls.
    """

    _ensure_windows_proactor_loop_policy()

    # ---- resolve artifacts directory ----
    if artifacts_dir is None and run_dir is not None:
        artifacts_dir = str(Path(run_dir) / "execution")

    if artifacts_dir is None:
        raise ValueError("artifacts_dir or run_dir must be provided")

    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- resolve base_url ----
    if base_url is None:
        # fallback: deterministic default
        base_url = "https://www.amazon.com"

    # ---- config handling (safe defaults) ----
    cfg = config or {}
    headless = bool(cfg.get("headless", True))

    holder: Dict[str, Any] = {"results": None, "error": None}

    def _thread_main() -> None:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            holder["results"] = loop.run_until_complete(
                _run_all_async(
                    base_url=base_url,
                    parsed_scenarios=parsed_scenarios,
                    artifacts_dir=out_dir,
                    headless=headless,
                )
            )
        except Exception as e:
            holder["error"] = e
        finally:
            try:
                loop.close()
            except Exception:
                pass

    t = threading.Thread(target=_thread_main, daemon=True)
    t.start()
    t.join()

    if holder["error"] is not None:
        e = holder["error"]
        raise RuntimeError(f"Playwright execution failed: {type(e).__name__}: {e}")

    return holder["results"] or []
