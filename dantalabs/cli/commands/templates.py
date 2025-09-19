import typer
import os
from pathlib import Path
from typing import Optional, Annotated
from ..utils.github import GitHubTemplateManager
from ..config import load_config

app = typer.Typer()

@app.command()
def init_command(
    template: Annotated[str, typer.Argument(help="Name of the template to initialize")],
    project_name: Annotated[Optional[str], typer.Option("--name", help="Name for the new project")] = None,
    output_dir: Annotated[Optional[str], typer.Option("--output", "-o", help="Output directory for the project")] = None,
    repo_url: Annotated[Optional[str], typer.Option("--repo", help="GitHub repository URL for templates")] = None,
):
    """
    Initialize a new project from a template.
    
    Downloads and sets up a starter project from the specified template.
    """
    # Load config to get default repository if not provided
    config = load_config()
    default_repo = config.get("template_repo", "dantalabs/maestro-templates")
    repo_url = repo_url or default_repo
    
    # Use template name as project name if not specified
    if project_name is None:
        project_name = template
    
    # Use current directory if output not specified
    if output_dir is None:
        output_dir = os.getcwd()
    
    output_path = Path(output_dir) / project_name
    
    typer.secho(f"Initializing project '{project_name}' from template '{template}'...", fg=typer.colors.CYAN)
    typer.echo(f"Repository: {repo_url}")
    typer.echo(f"Output directory: {output_path}")
    
    try:
        github_manager = GitHubTemplateManager(repo_url)
        
        # Check if template exists
        templates = github_manager.list_templates()
        if template not in templates:
            typer.secho(f"Error: Template '{template}' not found.", fg=typer.colors.RED, err=True)
            typer.echo("Available templates:")
            for tmpl in templates:
                typer.echo(f"  - {tmpl}")
            raise typer.Exit(code=1)
        
        # Check if output directory already exists
        if output_path.exists():
            if not typer.confirm(f"Directory '{output_path}' already exists. Continue anyway?"):
                typer.echo("Aborted.")
                raise typer.Exit(code=0)
        
        # Download and initialize the template
        github_manager.download_template(template, str(output_path), project_name)
        
        typer.secho(f"\n✅ Successfully initialized project '{project_name}' from template '{template}'!", fg=typer.colors.GREEN)
        typer.echo(f"Project location: {output_path}")
        
        # Show next steps if available
        readme_path = output_path / "README.md"
        if readme_path.exists():
            typer.echo(f"\nNext steps: Check {readme_path} for setup instructions.")
            
    except Exception as e:
        typer.secho(f"Error initializing project: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def list_templates_command(
    repo_url: Annotated[Optional[str], typer.Option("--repo", help="GitHub repository URL for templates")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show detailed information about each template")] = False,
):
    """
    List available project templates.
    
    Shows all templates available in the configured GitHub repository.
    """
    # Load config to get default repository if not provided
    config = load_config()
    default_repo = config.get("template_repo", "dantalabs/maestro-templates")
    repo_url = repo_url or default_repo
    
    typer.secho(f"Fetching templates from: {repo_url}", fg=typer.colors.CYAN)
    
    try:
        github_manager = GitHubTemplateManager(repo_url)
        templates = github_manager.list_templates(verbose=verbose)
        
        if not templates:
            typer.secho("No templates found.", fg=typer.colors.YELLOW)
            return
        
        typer.echo(f"\nAvailable templates ({len(templates)} found):")
        typer.echo("=" * 50)
        
        if verbose:
            for template_info in templates:
                typer.echo(f"\n📁 {template_info['name']}")
                if template_info.get('description'):
                    typer.echo(f"   Description: {template_info['description']}")
                if template_info.get('dependencies'):
                    typer.echo(f"   Dependencies: {', '.join(template_info['dependencies'])}")
                if template_info.get('tags'):
                    typer.echo(f"   Tags: {', '.join(template_info['tags'])}")
        else:
            for template in templates:
                name = template if isinstance(template, str) else template['name']
                typer.echo(f"  - {name}")
        
        typer.echo(f"\nTo initialize a project, use: dlm init <template-name>")
        
    except Exception as e:
        typer.secho(f"Error fetching templates: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)