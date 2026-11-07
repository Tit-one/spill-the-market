"""Explicit, literal env-file reuse. Never scan private projects or execute a file."""
import os
import re
from pathlib import Path

ALLOWED = {
    "TAVILY_API_KEY", "FIRECRAWL_API_KEY", "SPILL_TAVILY_USD_PER_CREDIT", "SPILL_FIRECRAWL_USD_PER_CREDIT",
    "SPILL_LLM_API_KEY", "SPILL_LLM_BASE_URL", "SPILL_LLM_MODEL", "SPILL_LLM_INPUT_USD_PER_MILLION",
    "SPILL_LLM_OUTPUT_USD_PER_MILLION", "SPILL_LLM_MAX_INPUT_TOKENS", "SPILL_LLM_MAX_OUTPUT_TOKENS",
    "SPILL_LLM_REASONING_EFFORT", "SPILL_LLM_TOKEN_PARAMETER",
    "SPILL_NEO4J_URI", "SPILL_NEO4J_USER", "SPILL_NEO4J_PASSWORD", "SPILL_NEO4J_DATABASE",
}
ALIASES = {
    "LLM_API_KEY": "SPILL_LLM_API_KEY", "OPENAI_API_KEY": "SPILL_LLM_API_KEY",
    "LLM_BASE_URL": "SPILL_LLM_BASE_URL", "LLM_MODEL_NAME": "SPILL_LLM_MODEL",
    "LLM_REASONING_EFFORT": "SPILL_LLM_REASONING_EFFORT",
    "NEO4J_URI": "SPILL_NEO4J_URI", "NEO4J_USER": "SPILL_NEO4J_USER",
    "NEO4J_USERNAME": "SPILL_NEO4J_USER", "NEO4J_PASSWORD": "SPILL_NEO4J_PASSWORD",
    "NEO4J_DATABASE": "SPILL_NEO4J_DATABASE",
}


def load_env_file(path: str | Path) -> dict:
    source = Path(path)
    if not source.is_file() or source.stat().st_size > 100_000:
        raise ValueError("Select an existing env file smaller than 100 KB")
    values = {}
    for line in source.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not match:
            continue
        key, value = match.groups()
        if key not in ALLOWED and key not in ALIASES:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        if value and "\x00" not in value:
            values[key] = value
    canonical = {key: value for key, value in values.items() if key in ALLOWED}
    for alias, key in ALIASES.items():
        if alias in values and key not in canonical:
            canonical[key] = values[alias]
    loaded = []
    for key, value in canonical.items():
        if not os.environ.get(key):
            os.environ[key] = value
            loaded.append(key)
    return {"loaded": sorted(loaded), "configuration": "explicit-env-file", "values_disclosed": False}
