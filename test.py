from pathlib import Path
from datetime import datetime
from typing import Any


def save_debug_output(file_name: str, content: Any) -> None:
    """
    Save debug content into a text file.

    Args:
        file_name: base name of the file
        content: any content (str, dict, object)

    File will be saved in ./debug_logs directory.
    """

    try:
        debug_dir = Path("debug_logs")
        debug_dir.mkdir(exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        file_path = debug_dir / f"{file_name}_{timestamp}.txt"

        if isinstance(content, (dict, list)):
            import json
            text = json.dumps(content, indent=2, default=str)
        else:
            text = str(content)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)

    except Exception as e:
        print(f"Failed to write debug file: {e}")


save_debug_output("dashboard_run_output_raw", out)

# if available
if hasattr(out, "to_dict"):
    save_debug_output("dashboard_run_output_dict", out.to_dict())

if hasattr(out, "messages"):
    save_debug_output("dashboard_run_messages", out.messages)
