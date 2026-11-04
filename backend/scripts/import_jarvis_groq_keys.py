"""Explicit user-authorized secret transfer. Never prints credential values.

Reads only Groq entries from the supplied source dotenv. Preserves unrelated
destination service credentials and leaves the source project unchanged.
"""
import argparse
from pathlib import Path
import re
import os
import tempfile
import httpx
from dotenv import dotenv_values

GROUPS = ["PARSING", "CHAT", "TAILORING", "ATS", "CLASSIFICATION"]
REMOVED = {"GROQ_API_KEY", "NVIDIA_NIM_API_KEY", "NVIDIA_NIM_BASE_URL", "GEMINI_API_KEY",
           "ANTHROPIC_API_KEY", "ZHIPU_API_KEY", "LOCAL_LLM_BASE_URL", "CLERK_SECRET_KEY"}


def transfer(source: Path, destination: Path):
    values = dotenv_values(source, interpolate=False)
    keys = []
    for name, value in values.items():
        if "GROQ" in name.upper() and "KEY" in name.upper():
            for key in re.findall(r"gsk_[A-Za-z0-9_-]{25,}", value or ""):
                if key not in keys:
                    keys.append(key)
    if len(keys) < len(GROUPS):
        raise RuntimeError("Five distinct Groq credentials are required; destination was not changed.")
    for index, key in enumerate(keys[:5], 1):
        try:
            response = httpx.get("https://api.groq.com/openai/v1/models", headers={"Authorization": "Bearer " + key}, timeout=20)
        except httpx.HTTPError:
            raise RuntimeError(f"Could not verify source credential {index}; destination was not changed.") from None
        if response.status_code != 200:
            raise RuntimeError(f"Source credential {index} failed validation ({response.status_code}); destination was not changed.")
    content = destination.read_text(encoding="utf-8") if destination.exists() else ""
    kept = []
    for line in content.splitlines():
        match = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=", line)
        if match:
            name = match[1]
            if name in REMOVED or name.startswith("GROQ_API_KEY_") or name.startswith("MODEL_PHASE_"):
                continue
        kept.append(line)
    kept.append("\n# Groq credentials assigned by task; shared organization limits still apply.")
    for group, key in zip(GROUPS, keys):
        kept.append(f"GROQ_API_KEY_{group}='{key}'")
    descriptor, temporary = tempfile.mkstemp(prefix=".groq-config-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(kept) + "\n")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Validated and installed five task-scoped Groq credentials. Source project unchanged. No secrets displayed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    transfer(args.source, args.destination)
