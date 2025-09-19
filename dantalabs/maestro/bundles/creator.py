import zipfile
import tempfile
import os
import yaml
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from ..exceptions import MaestroError

class BundleCreator:
    """Handles creation of agent bundles from source directories."""
    
    def create_bundle(
        self, 
        source_dir: str, 
        output_path: Optional[str] = None,
        include_requirements: bool = True,
        install_dependencies: bool = True,
        maestro_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Creates a ZIP bundle from a source directory for agent deployment.
        
        Args:
            source_dir: Path to the directory containing agent code
            output_path: Path for the output ZIP file. If None, creates in temp directory
            include_requirements: Whether to automatically include requirements from pyproject.toml or requirements.txt
            install_dependencies: Whether to install dependencies into the bundle (includes them as Python libraries)
            maestro_config: Optional maestro.yaml configuration to include in the bundle
            
        Returns:
            str: Path to the created bundle ZIP file
            
        Raises:
            MaestroError: If bundle creation fails
        """
        source_path = Path(source_dir)
        if not source_path.exists() or not source_path.is_dir():
            raise MaestroError(f"Source directory '{source_dir}' does not exist or is not a directory")
        

        if output_path is None:
            temp_dir = tempfile.mkdtemp(prefix="maestro_bundle_")
            output_path = os.path.join(temp_dir, "agent_bundle.zip")
        
        # Create a temporary directory for dependency installation if needed
        deps_temp_dir = None
        if install_dependencies:
            deps_temp_dir = tempfile.mkdtemp(prefix="maestro_deps_")
        
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:

                added_files = set()
                

                for root, dirs, files in os.walk(source_path):

                    dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', '.pytest_cache', 'node_modules', '.venv', 'venv'}]
                    
                    for file in files:

                        if file.startswith('.') and file not in {'.env.example'}:
                            continue
                        if file.endswith(('.pyc', '.pyo', '.pyd')):
                            continue
                            
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source_path)
                        zipf.write(file_path, arcname)
                        added_files.add(arcname)
                

                if install_dependencies and deps_temp_dir:
                    requirements_content = self._extract_requirements(source_path)
                    if requirements_content:
                        self._install_dependencies(requirements_content, deps_temp_dir, zipf, added_files)
                

                elif include_requirements and "requirements.txt" not in added_files:
                    requirements_content = self._extract_requirements(source_path)
                    if requirements_content:
                        zipf.writestr("requirements.txt", requirements_content)
                        added_files.add("requirements.txt")
                
                # Create maestro.yaml config if provided (only if not already present)
                self._add_maestro_config(zipf, added_files, maestro_config)
                    
            return output_path
            
        except Exception as e:
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except:
                    pass
            raise MaestroError(f"Failed to create bundle: {e}") from e
        finally:
            
            if deps_temp_dir and os.path.exists(deps_temp_dir):
                try:
                    import shutil
                    shutil.rmtree(deps_temp_dir)
                except Exception:
                    pass

    def _extract_requirements(self, source_path: Path) -> Optional[str]:
        """Extracts requirements from pyproject.toml or requirements.txt files."""
   
        pyproject_path = source_path / "pyproject.toml"
        if pyproject_path.exists():
            pyproject_data = None
            
     
            try:
                import toml
                with open(pyproject_path, 'r') as f:
                    pyproject_data = toml.load(f)
            except ImportError:
            
                import tomllib
                with open(pyproject_path, 'rb') as f:
                    pyproject_data = tomllib.load(f)
            
            except Exception:
                pass  
                
            if pyproject_data:
                dependencies = []
                
            
                if 'project' in pyproject_data and 'dependencies' in pyproject_data['project']:
                    dependencies.extend(pyproject_data['project']['dependencies'])
                
              
                if 'tool' in pyproject_data and 'poetry' in pyproject_data['tool']:
                    poetry_deps = pyproject_data['tool']['poetry'].get('dependencies', {})
                    for dep, version in poetry_deps.items():
                        if dep != 'python':
                            if isinstance(version, str):
                                dependencies.append(f"{dep}{version}")
                            elif isinstance(version, dict) and 'version' in version:
                                dependencies.append(f"{dep}{version['version']}")
                            else:
                                dependencies.append(dep)
                
                if dependencies:
                    return '\n'.join(dependencies)
        
   
        requirements_path = source_path / "requirements.txt"
        if requirements_path.exists():
            try:
                return requirements_path.read_text().strip()
            except Exception:
                pass
        
        return None

    def _install_dependencies(self, requirements_content: str, deps_temp_dir: str, zipf: zipfile.ZipFile, added_files: set):
        """Install dependencies to temporary directory and add to bundle."""
        req_file = os.path.join(deps_temp_dir, "temp_requirements.txt")
        with open(req_file, 'w') as f:
            f.write(requirements_content)
        
        try:
            print(f"Installing dependencies to bundle... (this may take several minutes)")
            
            result = subprocess.run([
                sys.executable, "-m", "pip", "install", 
                "-r", req_file,
                "--target", deps_temp_dir,
                "--upgrade",
                "--no-cache-dir"
            ], check=True, capture_output=True, text=True, timeout=900)
            
            if result.stdout:
                print(f"Dependency installation completed.")
            if result.stderr and result.returncode == 0:
                print(f"Installation warnings: {result.stderr}")
            
          
            package_count = 0
            for root, dirs, files in os.walk(deps_temp_dir):
                dirs[:] = [d for d in dirs if not d.endswith('.dist-info') and not d.endswith('.egg-info') and d != '__pycache__']
                
                for file in files:
                    if file == "temp_requirements.txt":
                        continue
                    if file.endswith(('.pyc', '.pyo', '.pyd')):
                        continue
                        
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, deps_temp_dir)
                    
                    if arcname not in added_files:
                        zipf.write(file_path, arcname)
                        added_files.add(arcname)
                        package_count += 1
            
            print(f"Dependencies installed and included in bundle ({package_count} files added).")
            
        except subprocess.TimeoutExpired:
            print(f"Warning: Dependency installation timed out after 15 minutes.")
            self._fallback_to_requirements_txt(requirements_content, zipf, added_files)
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to install dependencies: {e}")
            self._fallback_to_requirements_txt(requirements_content, zipf, added_files)
        except Exception as e:
            print(f"Warning: Unexpected error during dependency installation: {e}")
            self._fallback_to_requirements_txt(requirements_content, zipf, added_files)

    def _fallback_to_requirements_txt(self, requirements_content: str, zipf: zipfile.ZipFile, added_files: set):
        """Fallback to including requirements.txt if dependency installation fails."""
        print("Continuing with requirements.txt inclusion instead...")
        if "requirements.txt" not in added_files:
            zipf.writestr("requirements.txt", requirements_content)
            added_files.add("requirements.txt")

    def _add_maestro_config(self, zipf: zipfile.ZipFile, added_files: set, maestro_config: Optional[Dict[str, Any]]):
        """Add maestro.yaml config to bundle if not already present."""
        has_maestro_config = any(name in added_files for name in ["maestro.yaml", "maestro.yml"])
        
        if maestro_config and not has_maestro_config:
            yaml_content = yaml.dump(maestro_config, default_flow_style=False)
            zipf.writestr("maestro.yaml", yaml_content)
            added_files.add("maestro.yaml")
        elif not has_maestro_config:
           
            default_config = {
                "entrypoint": "main.py",
                "description": "Agent bundle",
                "version": "1.0.0"
            }
            yaml_content = yaml.dump(default_config, default_flow_style=False)
            zipf.writestr("maestro.yaml", yaml_content)
            added_files.add("maestro.yaml")