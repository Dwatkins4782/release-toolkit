"""
Configuration Loader — Loads and merges YAML config with environment variables.
"""

import os
import re
import yaml
from pathlib import Path
from dotenv import load_dotenv


def _resolve_env_vars(value):
    """Replace ${VAR_NAME} patterns with environment variable values."""
    if isinstance(value, str):
        pattern = r'\$\{([^}]+)\}'
        def replacer(match):
            env_var = match.group(1)
            return os.environ.get(env_var, match.group(0))
        return re.sub(pattern, replacer, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def find_config_dir():
    """Find the config directory, searching up from CWD."""
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        config_dir = parent / "config"
        if (config_dir / "release-config.yaml").exists():
            return config_dir
    # Fallback: relative to this script
    return Path(__file__).parent.parent.parent / "config"


def load_config(config_dir=None):
    """Load release-config.yaml and merge with environment variables."""
    if config_dir is None:
        config_dir = find_config_dir()
    config_dir = Path(config_dir)

    # Load .env file if present
    env_file = config_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    # Load main config
    config_path = config_dir / "release-config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Load conventional commits config
    cc_path = config_dir / "conventional-commits.yaml"
    if cc_path.exists():
        with open(cc_path, 'r') as f:
            config['conventional_commits'] = yaml.safe_load(f)

    # Resolve environment variables in config values
    config = _resolve_env_vars(config)

    return config


def get_config_value(config, key_path, default=None):
    """Get a nested config value using dot notation (e.g., 'jira.base_url')."""
    keys = key_path.split('.')
    value = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value
