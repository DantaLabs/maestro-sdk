# maestro_sdk/memory.py
import collections.abc
import copy
import traceback
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Tuple
from uuid import UUID

# Use TYPE_CHECKING to avoid circular imports at runtime
if TYPE_CHECKING:
    from .client import MaestroClient

from .exceptions import MaestroError, MaestroApiError
from .models import MemoryUpdate # Import the specific model needed

class ManagedMemory(collections.abc.MutableMapping):
    """
    Manages a specific agent memory, providing dictionary-like access
    to its 'data' field and syncing changes with the Maestro server.

    (Keep the rest of the docstring as is)
    """

    def __init__(
        self,
        client: 'MaestroClient', # Use forward reference string
        agent_id: UUID,
        memory_name: str,
        auto_load: bool = True,
        create_if_missing: bool = True,
        default_description: Optional[str] = None,
    ):
        # Need to import MaestroClient here for the type check, but avoid runtime circular import
        from .client import MaestroClient
        if not isinstance(client, MaestroClient):
            raise TypeError("client must be an instance of MaestroClient")
        if not client.organization_id:
             raise ValueError("MaestroClient must be initialized with an organization_id.")
 

        self._client = client
        self._agent_id = agent_id # Store as UUID
        self._memory_name = memory_name
        self._create_if_missing = create_if_missing
        self._default_description = default_description or f"Managed memory '{memory_name}' for agent {agent_id}"

        # Internal state
        self._memory_id: Optional[UUID] = None
        self._memory_metadata: Dict[str, Any] = {} # Store non-data fields like description, type, tags, etc.
        self._data: Dict[str, Any] = {}
        self._loaded: bool = False
        self._dirty: bool = False # Tracks if _data has been potentially modified
        self._original_data_snapshot: Optional[Dict[str, Any]] = None # For accurate dirty checking

        if auto_load:
            try:
                self.load()
            except MaestroError as e:
                # Allow initialization even if auto-load fails, user can try loading later
                print(f"Warning: Auto-load failed during initialization for memory '{self._memory_name}': {e}")
                self._reset_local_state() # Ensure clean state on failure

    def _ensure_loaded(self):
        """Loads data if not already loaded."""
        if not self._loaded:
            print(f"Memory '{self._memory_name}' accessed before loading. Attempting load...")
            self.load() # load() handles errors and state changes


    def load(self, force_reload: bool = False) -> 'ManagedMemory':
        """
        Fetches the memory data from the Maestro server.
        """
        if self._loaded and not force_reload:
            return self

        print(f"Loading memory '{self._memory_name}' for agent {self._agent_id}...")
        try:
            memory_details = self._client._get_memory_by_name_raw(self._memory_name)

            if memory_details and isinstance(memory_details, dict):
                self._memory_id = UUID(str(memory_details['id']))
                self._memory_metadata = {k: v for k, v in memory_details.items() if k != 'data'}
                raw_data = memory_details.get('data', {})
                if not isinstance(raw_data, dict):
                     print(f"Warning: Memory '{self._memory_name}' data field is not a dictionary ({type(raw_data)}). Resetting to empty dict.")
                     self._data = {}
                else:
                     self._data = copy.deepcopy(raw_data)

                self._original_data_snapshot = copy.deepcopy(self._data)
                self._loaded = True
                self._dirty = False
                print(f"Memory '{self._memory_name}' loaded successfully (ID: {self._memory_id}).")
            else:
                 # Memory not found or invalid data
                 print(f"Memory '{self._memory_name}' not found on server or invalid data received. Initializing locally.")
                 self._reset_local_state()
                 self._loaded = True # Mark as loaded (even if empty) to avoid reload loops
                 self._dirty = False # Not dirty if it wasn't found/loaded

        except MaestroApiError as e:
             self._reset_local_state()
             print(f"Error loading memory '{self._memory_name}': {e}")
             raise # Re-raise API errors
        except Exception as e:
             self._reset_local_state()
             print(f"Unexpected error loading memory '{self._memory_name}': {e}")
             raise MaestroError(f"Unexpected error during memory load: {e}") from e

        return self

    def _check_dirty(self) -> bool:
        """ More robust check if data has changed compared to the snapshot """
        if not self._loaded:
             # If never loaded, any modification makes it dirty relative to non-existent server state
             return self._dirty
        return self._data != self._original_data_snapshot

    def update_and_commit(self, updates: Dict[str, Any], update_strategy: str = "merge") -> bool:
        """
        Update specific keys in the memory data and commit changes in one operation.

        Args:
            updates: Dictionary containing the keys and values to update
            update_strategy: How to update data on server:
                - "merge": Merge updates with existing data (default)
                - "replace": Replace entire data with updates

        Returns:
            bool: True if the update was successful
        """
        self._ensure_loaded()

        if update_strategy == "replace":
            # Replace entire data content
            if self._data != updates: # Only mark dirty if it actually changes
                self._data = copy.deepcopy(updates)
                self._dirty = True
        else: # merge strategy
            changed = False
            for key, value in updates.items():
                if key not in self._data or self._data[key] != value:
                    self._data[key] = value
                    changed = True
            if changed:
                self._dirty = True

        # Commit changes to server if anything was actually marked dirty
        if self._dirty:
            return self.commit_with_strategy(update_strategy)
        else:
            print(f"No changes detected in update_and_commit for memory '{self._memory_name}'. Skipping commit.")
            return True # No commit needed, considered successful

    def commit_with_strategy(self, update_strategy: str = "merge") -> bool:
        """
        Saves local changes to the 'data' field back to the Maestro server with specified strategy.

        Args:
            update_strategy: How to update data on server:
                - "merge": Server merges provided data (default)
                - "replace": Server replaces entire data content

        Returns:
            bool: True if the commit was successful
        """
        # Use the robust check before committing
        is_actually_dirty = self._check_dirty()
        if not is_actually_dirty:
            print(f"No actual changes detected to commit for memory '{self._memory_name}'.")
            self._dirty = False # Ensure flag is reset
            return True
        # If we reach here, is_actually_dirty is True, so self._dirty should also be True
        self._dirty = True # Ensure it's set just in case

        if not self._loaded:
            # This check might be redundant if _ensure_loaded works, but good safeguard
            print("Memory not loaded before commit, attempting load to check existence...")
            try:
                self.load()
                if not self._loaded:
                     print("Failed to load memory state before commit. Commit aborted.")
                     return False
                is_actually_dirty = self._check_dirty() # Re-check after load
                if not is_actually_dirty:
                     print(f"Data matches server state after loading. No commit needed for memory '{self._memory_name}'.")
                     self._dirty = False
                     return True
            except MaestroError as e:
                 print(f"Failed to load memory state before commit: {e}. Commit aborted.")
                 return False

        # --- Commit Logic (Create or Update) ---
        try:
            if self._memory_id is None: # Memory needs creation
                if not self._create_if_missing:
                    print(f"Memory '{self._memory_name}' does not exist and create_if_missing is False. Commit aborted.")
                    return False

                print(f"Creating memory '{self._memory_name}'...")
                # Prepare payload for creation
                memory_data_payload = {
                    "name": self._memory_name,
                    "memory_type": self._memory_metadata.get("memory_type", "json"), # Use existing or default
                    "data": self._data, # Send current local data
                    "description": self._memory_metadata.get("description", self._default_description),
                    "memory_metadata": self._memory_metadata.get("memory_metadata", {}),
                    "tags": self._memory_metadata.get("tags", [])
                }
                # Call the client's method to add memory
                created_memory_response = self._client.add_memory_to_agent(memory_data_payload)

                if created_memory_response and isinstance(created_memory_response, dict) and created_memory_response.get("id"):
                    new_id = UUID(str(created_memory_response['id']))
                    print(f"Memory '{self._memory_name}' created successfully (ID: {new_id}). Reloading state.")
                    # Reload state from server to ensure consistency
                    self.load(force_reload=True)
                    return True
                else:
                    print(f"Error: Memory creation for '{self._memory_name}' did not return a valid ID or response. Response: {created_memory_response}")
                    # State remains: _memory_id=None, _loaded=True (but empty), _dirty=True
                    return False

            else: # Memory exists, update it
                print(f"Updating memory '{self._memory_name}' (ID: {self._memory_id}) with strategy '{update_strategy}'...")

                memory_update_payload = MemoryUpdate(
                    data=self._data, 
                    update_strategy=update_strategy
                   
                )

             
                update_dict = memory_update_payload.model_dump(exclude_none=True)

                try:
                 
                    updated_memory_response = self._client.update_memory(
                        memory_id=self._memory_id,
                        update_data=update_dict, 
                        agent_id=self._agent_id 
                    )

                    print(f"Memory '{self._memory_name}' update API call successful. Reloading state.")
               
                    self.load(force_reload=True)
                    return True
                except MaestroApiError as e:
                
                    print(f"API Error during update for memory '{self._memory_name}': Status {e.status_code}, Detail: {e.error_detail}")
     
                    return False
                except Exception as e:
                    print(f"Unexpected error during memory update for '{self._memory_name}': {e}")
                    traceback.print_exc()
                   
                    return False

        except MaestroApiError as e:

            print(f"API Error during commit operation for memory '{self._memory_name}': Status {e.status_code}, Detail: {e.error_detail}")
            return False
        except Exception as e:
            print(f"Unexpected error during commit operation for memory '{self._memory_name}': {e}")
            traceback.print_exc()
            return False


    def commit(self) -> bool:
        """
        Saves local changes to the 'data' field back to the Maestro server.
        Uses replace strategy for backward compatibility.

        For more fine-grained control, use commit_with_strategy() instead.
        """
        print("Warning: commit() uses 'replace' strategy. Use commit_with_strategy('merge') for partial updates.")
        return self.commit_with_strategy("replace")

    def reset(self):
        """Discards local changes and reloads data from the server."""
        print(f"Resetting local changes for memory '{self._memory_name}'.")
        self._dirty = False
        try:
            self.load(force_reload=True)
        except MaestroError as e:
            print(f"Warning: Failed to reload memory during reset: {e}")
            # If reload fails, reset to a clean 'unloaded' state
            self._reset_local_state()

    def _reset_local_state(self):
        """Resets internal state variables to represent an unloaded/non-existent memory."""
        self._memory_id = None
        self._memory_metadata = {}
        self._data = {}
        self._loaded = False
        self._dirty = False
        self._original_data_snapshot = None


    def __getitem__(self, key: str) -> Any:
        self._ensure_loaded()
        try:
            return self._data[key]
        except KeyError:
            raise KeyError(f"Key '{key}' not found in memory '{self._memory_name}'")

    def __setitem__(self, key: str, value: Any):
        self._ensure_loaded()
        current_value = self._data.get(key)
        if key not in self._data or current_value != value:
            self._data[key] = value
            self._dirty = True
      
    def __delitem__(self, key: str):
        self._ensure_loaded()
        if key in self._data:
            del self._data[key]
            self._dirty = True
        else:
             raise KeyError(f"Key '{key}' not found in memory '{self._memory_name}'")

    def __iter__(self) -> Iterator[str]:
        self._ensure_loaded()
        return iter(self._data)

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._data)

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        self._ensure_loaded()
        return self._data.get(key, default)

    def update(self, other: Dict[str, Any] = None, **kwargs) -> None:
        self._ensure_loaded()
        to_update = {}
        if isinstance(other, collections.abc.Mapping):
            to_update.update(other)
        elif other is not None:
             try:
                 for k, v in other:
                     to_update[k] = v
             except (TypeError, ValueError):
                  raise TypeError("Invalid argument type for update()")
        if kwargs:
            to_update.update(kwargs)

        changed = False
        for key, value in to_update.items():
            current_value = self._data.get(key)
            if key not in self._data or current_value != value:
                changed = True
                self._data[key] = value

        if changed:
            self._dirty = True

    def pop(self, key: str, default: Optional[Any] = ...) -> Any:
        self._ensure_loaded()
        if key in self._data:
            value = self._data.pop(key)
            self._dirty = True
            return value
        else:
            if default is ...:
                 raise KeyError(f"Key '{key}' not found in memory '{self._memory_name}'")
            else:
                 return default

    def popitem(self) -> Tuple[str, Any]:
        self._ensure_loaded()
        if not self._data:
            raise KeyError("popitem(): dictionary is empty")
        item = self._data.popitem()
        self._dirty = True
        return item

    def clear(self) -> None:
        self._ensure_loaded()
        if self._data:
            self._data.clear()
            self._dirty = True

    def setdefault(self, key: str, default: Optional[Any] = None) -> Any:
        self._ensure_loaded()
        if key not in self._data:
            self._data[key] = default
            self._dirty = True
            return default
        else:
            return self._data[key]

    # --- Additional Helper Properties/Methods ---
    @property
    def memory_id(self) -> Optional[UUID]:

        self._ensure_loaded()
        return self._memory_id

    @property
    def metadata(self) -> Dict[str, Any]:
        self._ensure_loaded()
        # Return a copy to prevent external modification of internal state
        return self._memory_metadata.copy()

    @property
    def is_dirty(self) -> bool:
        # Use the check method which compares against the snapshot
        return self._check_dirty()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def __repr__(self) -> str:
        state = "loaded" if self._loaded else "unloaded"
        # Use the property self.is_dirty which uses the robust check
        dirty_state = ", dirty" if self.is_dirty else ""
        id_str = f"id={self._memory_id}" if self._memory_id else "id=None"
        # Show data preview only if loaded
        data_repr = "..." # Default if not loaded
        if self._loaded:
            data_repr = repr(self._data)
            if len(data_repr) > 100:
                data_repr = data_repr[:100] + "...}"
        return (f"<ManagedMemory(name='{self._memory_name}', agent='{self._agent_id}', "
                f"{id_str}, {state}{dirty_state}, data={data_repr})>")

    def __str__(self) -> str:
        self._ensure_loaded()
        return str(self._data)