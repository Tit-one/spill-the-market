"""Explicit, literal env-file reuse. Never scan private projects or execute a file."""
import os
import json
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

VISION_SETTINGS = {
    "SPILL_VISION_ENABLED", "SPILL_VISION_BASE_URL", "SPILL_VISION_MODEL", "SPILL_VISION_API_KEY",
    "SPILL_VISION_INPUT_USD_PER_MILLION", "SPILL_VISION_OUTPUT_USD_PER_MILLION",
    "SPILL_VISION_MAX_IMAGE_INPUT_TOKENS", "SPILL_VISION_MAX_INPUT_TOKENS", "SPILL_VISION_MAX_OUTPUT_TOKENS",
    "SPILL_VISION_REASONING_EFFORT", "SPILL_VISION_TOKEN_PARAMETER",
    "SPILL_VISION_LOCAL_URL", "SPILL_VISION_LOCAL_MODEL",
}
ALLOWED.update(VISION_SETTINGS)


def load_provider_profile(data_dir=None, *, include_env_file=True) -> dict:
    """Read an explicitly saved provider reference and public settings, never copy secrets."""
    from .storage import data_directory
    path = data_directory(data_dir) / "provider-profile.json"
    if not path.is_file():
        return {"configuration": "environment", "values_disclosed": False}
    if path.stat().st_size > 32_000:
        raise ValueError("Saved public provider profile is too large")
    profile = json.loads(path.read_text(encoding="utf-8"))
    public = profile.get("public_settings", {})
    safe_names = {name for name in ALLOWED if not any(word in name for word in ("API_KEY", "PASSWORD"))}
    if not isinstance(public, dict) or not set(public) <= safe_names or any(not isinstance(v, str) for v in public.values()):
        raise ValueError("Provider profile may contain only named public settings")
    if include_env_file and profile.get("env_file"):
        load_env_file(profile["env_file"])
    for name, value in public.items():
        if not os.environ.get(name):
            os.environ[name] = value
    return {"configuration": "saved-provider-reference", "values_disclosed": False}


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
            seen = set()
            while reference := re.fullmatch(r"\$\{([A-Z][A-Z0-9_]*)\}", value):
                name = reference.group(1)
                if name not in ALLOWED and name not in ALIASES or name in seen:
                    raise ValueError(f"Selected configuration has an unsupported or cyclic reference: {name}")
                seen.add(name)
                value = os.environ.get(name) or values.get(name)
                if not value:
                    raise ValueError(f"Selected configuration references unavailable variable {name}")
            os.environ[key] = value
            loaded.append(key)
    return {"loaded": sorted(loaded), "configuration": "explicit-env-file", "values_disclosed": False}
