import typer
import json
import dotenv
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

def load_schemas(file_path: Path, schema_file: Optional[Path] = None) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Loads input, output, and memory schemas from JSON file."""
    input_schema = {}
    output_schema = {}
    memory_template = {}
    
    # Try to load schemas from JSON file with same name if no specific file is provided
    if not schema_file:
        if file_path.is_file():
            default_schema_file = file_path.with_suffix('.json')
        else:
            default_schema_file = file_path / f"{file_path.name}.json"
        
        if default_schema_file.exists():
            schema_file = default_schema_file
    
    # Load schemas from the JSON file if it exists
    if schema_file and schema_file.exists():
        try:
            typer.echo(f"Loading schemas from '{schema_file}'...")
            with open(schema_file, 'r') as f:
                schema_data = json.load(f)
                
            # Extract schemas from the file
            if 'input' in schema_data:
                input_schema = schema_data['input']
                typer.echo("Input schema loaded.")
            
            if 'output' in schema_data:
                output_schema = schema_data['output']
                typer.echo("Output schema loaded.")
            
            if 'memory' in schema_data:
                memory_template = schema_data['memory']
                typer.echo("Memory template loaded.")
        except json.JSONDecodeError as e:
            typer.secho(f"Error parsing JSON file '{schema_file}': {e}", fg=typer.colors.RED, err=True)
            typer.secho("Continuing with default empty schemas.", fg=typer.colors.YELLOW)
        except Exception as e:
            typer.secho(f"Error reading schema file '{schema_file}': {e}", fg=typer.colors.RED, err=True)
            typer.secho("Continuing with default empty schemas.", fg=typer.colors.YELLOW)
    
    return input_schema, output_schema, memory_template

def load_env_variables(base_dir: Path, env_file: Optional[Path] = None) -> Dict[str, Any]:
    """Loads environment variables from .env file."""
    env_variables = {}
    
    # Try to load environment variables from .env file
    if not env_file:
        default_env_file = base_dir / '.env'
        if default_env_file.exists():
            env_file = default_env_file
    
    if env_file and env_file.exists():
        try:
            typer.echo(f"Loading environment variables from '{env_file}'...")
            env_variables = dotenv.dotenv_values(env_file)
            if env_variables:
                typer.echo(f"Loaded {len(env_variables)} environment variables.")
            else:
                typer.echo("No environment variables found in .env file.")
        except Exception as e:
            typer.secho(f"Error reading .env file '{env_file}': {e}", fg=typer.colors.RED, err=True)
            typer.secho("Continuing without environment variables.", fg=typer.colors.YELLOW)
    
    return env_variables