import typer
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from uuid import UUID

# --- Configuration Constants ---
CONFIG_DIR = Path.home() / ".maestro"
CONFIG_FILE = CONFIG_DIR / "config.json"
PROJECT_STATE_FILE = ".maestro_state.json"
VERSION = "0.0.1"

def load_config() -> Dict[str, Any]:
    """Loads configuration from the JSON file."""
    if CONFIG_FILE.is_file():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            typer.secho(f"Warning: Could not decode configuration file at {CONFIG_FILE}. Ignoring.", fg=typer.colors.YELLOW, err=True)
        except Exception as e:
            typer.secho(f"Warning: Could not read configuration file at {CONFIG_FILE}: {e}. Ignoring.", fg=typer.colors.YELLOW, err=True)
    return {}

def save_config(config_data: Dict[str, Any]):
    """Saves configuration to the JSON file."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True) 
        with open(CONFIG_FILE, "w") as f:
            json.dump(config_data, f, indent=4)
    except Exception as e:
        typer.secho(f"Error: Could not write configuration file at {CONFIG_FILE}: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

def load_project_state(project_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Loads project-specific state from the local .maestro_state.json file."""
    if project_dir is None:
        project_dir = Path.cwd()
    
    state_file = project_dir / PROJECT_STATE_FILE
    if state_file.exists():
        try:
            with open(state_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            typer.secho(f"Warning: Could not decode project state file at {state_file}. Ignoring.", fg=typer.colors.YELLOW, err=True)
        except Exception as e:
            typer.secho(f"Warning: Could not read project state file at {state_file}: {e}. Ignoring.", fg=typer.colors.YELLOW, err=True)
    return {}

def save_project_state(state_data: Dict[str, Any], project_dir: Optional[Path] = None):
    """Saves project-specific state to the local .maestro_state.json file."""
    if project_dir is None:
        project_dir = Path.cwd()
    
    state_file = project_dir / PROJECT_STATE_FILE
    try:
        with open(state_file, "w") as f:
            json.dump(state_data, f, indent=4)
    except Exception as e:
        typer.secho(f"Error: Could not write project state file at {state_file}: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)