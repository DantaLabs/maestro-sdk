import os
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Union
from urllib.request import urlopen
from urllib.parse import urlparse
import typer


class GitHubTemplateManager:
    """Manages downloading and processing templates from GitHub repositories."""
    
    def __init__(self, repo_url: str):
        """
        Initialize the GitHub template manager.
        
        Args:
            repo_url: GitHub repository URL (e.g., 'dantalabs/maestro-templates' or full URL)
        """
        # Parse repository URL to extract owner/repo
        if repo_url.startswith('http'):
            parsed = urlparse(repo_url)
            path_parts = parsed.path.strip('/').split('/')
            if len(path_parts) >= 2:
                self.repo_owner = path_parts[0]
                self.repo_name = path_parts[1]
            else:
                raise ValueError(f"Invalid GitHub repository URL: {repo_url}")
        else:
            # Assume format is owner/repo
            if '/' in repo_url:
                self.repo_owner, self.repo_name = repo_url.split('/', 1)
            else:
                raise ValueError(f"Invalid repository format: {repo_url}. Expected 'owner/repo'")
        
        self.base_api_url = "https://api.github.com"
        self.base_repo_url = f"https://github.com/{self.repo_owner}/{self.repo_name}"
    
    def list_templates(self, verbose: bool = False) -> Union[List[str], List[Dict[str, Any]]]:
        """
        List available templates in the repository.
        
        Args:
            verbose: If True, returns detailed information about each template
            
        Returns:
            List of template names or detailed template information
        """
        try:
            # Get repository contents
            api_url = f"{self.base_api_url}/repos/{self.repo_owner}/{self.repo_name}/contents"
            
            with urlopen(api_url) as response:
                contents = json.loads(response.read().decode())
            
            templates = []
            
            for item in contents:
                if item['type'] == 'dir':
                    template_name = item['name']
                    
                    if verbose:
                        # Try to get template metadata
                        template_info = self._get_template_info(template_name)
                        templates.append(template_info)
                    else:
                        templates.append(template_name)
            
            return templates
            
        except Exception as e:
            raise Exception(f"Failed to fetch templates from repository: {e}")
    
    def _get_template_info(self, template_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific template.
        
        Args:
            template_name: Name of the template directory
            
        Returns:
            Dictionary with template information
        """
        template_info = {"name": template_name}
        
        try:
            # Try to get template.json file
            template_json_url = f"{self.base_api_url}/repos/{self.repo_owner}/{self.repo_name}/contents/{template_name}/template.json"
            
            try:
                with urlopen(template_json_url) as response:
                    content = json.loads(response.read().decode())
                    if content.get('content'):
                        # Decode base64 content
                        import base64
                        template_config = json.loads(base64.b64decode(content['content']).decode())
                        template_info.update(template_config)
            except:
                # If template.json doesn't exist, try to get README
                readme_url = f"{self.base_api_url}/repos/{self.repo_owner}/{self.repo_name}/contents/{template_name}/README.md"
                try:
                    with urlopen(readme_url) as response:
                        content = json.loads(response.read().decode())
                        if content.get('content'):
                            import base64
                            readme_content = base64.b64decode(content['content']).decode()
                            # Extract first line as description
                            lines = readme_content.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and not line.startswith('#'):
                                    template_info['description'] = line
                                    break
                except:
                    pass
                    
        except Exception:
            # If we can't get additional info, just return the name
            pass
        
        return template_info
    
    def download_template(self, template_name: str, output_path: str, project_name: str):
        """
        Download and set up a template.
        
        Args:
            template_name: Name of the template to download
            output_path: Path where the project should be created
            project_name: Name of the new project
        """
        output_path = Path(output_path)
        
        # Create output directory
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Download repository as ZIP
        zip_url = f"{self.base_repo_url}/archive/refs/heads/main.zip"
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            zip_path = temp_path / "repo.zip"
            
            typer.echo("Downloading template repository...")
            
            # Download ZIP file
            with urlopen(zip_url) as response:
                with open(zip_path, 'wb') as f:
                    shutil.copyfileobj(response, f)
            
            # Extract ZIP file
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_path)
            
            # Find the extracted directory (should be repo-name-main)
            extracted_dirs = [d for d in temp_path.iterdir() if d.is_dir() and d.name != '__pycache__']
            if not extracted_dirs:
                raise Exception("No directory found in downloaded repository")
            
            repo_dir = extracted_dirs[0]
            template_dir = repo_dir / template_name
            
            if not template_dir.exists():
                raise Exception(f"Template '{template_name}' not found in repository")
            
            typer.echo(f"Copying template files to {output_path}...")
            
            # Copy template files to output directory
            self._copy_template_files(template_dir, output_path, project_name)
            
            # Process template files (replace placeholders)
            self._process_template_files(output_path, template_name, project_name)
    
    def _copy_template_files(self, source_dir: Path, dest_dir: Path, project_name: str):
        """Copy files from template directory to destination."""
        for item in source_dir.rglob('*'):
            if item.is_file():
                # Calculate relative path
                rel_path = item.relative_to(source_dir)
                dest_path = dest_dir / rel_path
                
                # Create parent directories
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file
                shutil.copy2(item, dest_path)
    
    def _process_template_files(self, project_dir: Path, template_name: str, project_name: str):
        """Process template files to replace placeholders."""
        placeholders = {
            '{{PROJECT_NAME}}': project_name,
            '{{TEMPLATE_NAME}}': template_name,
            '{{PROJECT_NAME_SNAKE}}': project_name.lower().replace('-', '_').replace(' ', '_'),
            '{{PROJECT_NAME_KEBAB}}': project_name.lower().replace('_', '-').replace(' ', '-'),
        }
        
        # File extensions to process for placeholder replacement
        processable_extensions = {'.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.yaml', '.yml', '.md', '.txt', '.toml', '.cfg', '.ini'}
        
        for file_path in project_dir.rglob('*'):
            if file_path.is_file() and file_path.suffix in processable_extensions:
                try:
                    # Read file content
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Replace placeholders
                    modified = False
                    for placeholder, replacement in placeholders.items():
                        if placeholder in content:
                            content = content.replace(placeholder, replacement)
                            modified = True
                    
                    # Write back if modified
                    if modified:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                            
                except Exception as e:
                    # Skip files that can't be processed
                    typer.echo(f"Warning: Could not process file {file_path}: {e}")
                    continue
        
        # Also rename files/directories with placeholders in their names
        self._rename_template_items(project_dir, placeholders)
    
    def _rename_template_items(self, project_dir: Path, placeholders: Dict[str, str]):
        """Rename files and directories that contain placeholders in their names."""
        # Process files and directories with placeholders in names
        # We need to process deepest items first to avoid path issues
        items_to_rename = []
        
        for item in project_dir.rglob('*'):
            for placeholder in placeholders:
                if placeholder in item.name:
                    items_to_rename.append(item)
                    break
        
        # Sort by depth (deepest first)
        items_to_rename.sort(key=lambda x: len(x.parts), reverse=True)
        
        for item in items_to_rename:
            new_name = item.name
            for placeholder, replacement in placeholders.items():
                new_name = new_name.replace(placeholder, replacement)
            
            if new_name != item.name:
                new_path = item.parent / new_name
                try:
                    item.rename(new_path)
                except Exception as e:
                    typer.echo(f"Warning: Could not rename {item} to {new_path}: {e}")