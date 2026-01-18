"""
User Context Store for Agent-S

Stores and retrieves user-specific context learned from recordings,
such as preferences, URLs, credentials (usernames only), and patterns.
"""

import json
from pathlib import Path
from typing import Optional, List

from .models import UserContext, ContextType


class UserContextStore:
    """
    Persistent store for user context extracted from recordings.
    
    Stores user preferences, URLs, entities, and patterns that can be
    used to personalize automation tasks.
    """
    
    def __init__(self, store_path: Optional[Path] = None):
        """
        Initialize the context store.
        
        Args:
            store_path: Path to the store directory (default: skill_store in package)
        """
        default_path = Path(__file__).parent.parent.parent.parent / "skill_store"
        self.store_path = store_path or default_path
        self.store_path.mkdir(parents=True, exist_ok=True)
        
        self.context_file = self.store_path / "user_context.json"
        self._contexts: dict[str, UserContext] = {}
        self._load()
    
    def _load(self):
        """Load contexts from disk."""
        if self.context_file.exists():
            try:
                data = json.loads(self.context_file.read_text())
                for item in data:
                    ctx = UserContext.from_dict(item)
                    self._contexts[ctx.key] = ctx
            except Exception as e:
                print(f"Error loading user context: {e}")
    
    def _save(self):
        """Save contexts to disk."""
        data = [ctx.to_dict() for ctx in self._contexts.values()]
        self.context_file.write_text(json.dumps(data, indent=2))
    
    def add(self, context: UserContext):
        """
        Add or update a user context.
        
        Args:
            context: UserContext to add
        """
        self._contexts[context.key] = context
        self._save()
    
    def add_many(self, contexts: List[UserContext]):
        """
        Add multiple contexts at once.
        
        Args:
            contexts: List of UserContext objects
        """
        for ctx in contexts:
            self._contexts[ctx.key] = ctx
        self._save()
    
    def get(self, key: str) -> Optional[UserContext]:
        """
        Get a context by key.
        
        Args:
            key: Context key
            
        Returns:
            UserContext or None if not found
        """
        return self._contexts.get(key)
    
    def get_by_type(self, context_type: ContextType) -> List[UserContext]:
        """
        Get all contexts of a specific type.
        
        Args:
            context_type: Type to filter by
            
        Returns:
            List of matching contexts
        """
        return [
            ctx for ctx in self._contexts.values() 
            if ctx.context_type == context_type
        ]
    
    def get_by_application(self, application: str) -> List[UserContext]:
        """
        Get all contexts for a specific application.
        
        Args:
            application: Application name to filter by
            
        Returns:
            List of matching contexts
        """
        app_lower = application.lower()
        return [
            ctx for ctx in self._contexts.values() 
            if app_lower in ctx.application.lower()
        ]
    
    def get_all(self) -> List[UserContext]:
        """
        Get all stored contexts.
        
        Returns:
            List of all contexts
        """
        return list(self._contexts.values())
    
    def search(self, query: str) -> List[UserContext]:
        """
        Search contexts by keyword.
        
        Args:
            query: Search query
            
        Returns:
            List of matching contexts
        """
        query_lower = query.lower()
        results = []
        for ctx in self._contexts.values():
            if (query_lower in ctx.key.lower() or 
                query_lower in ctx.value.lower() or
                query_lower in ctx.description.lower() or
                query_lower in ctx.application.lower()):
                results.append(ctx)
        return results
    
    def delete(self, key: str) -> bool:
        """
        Delete a context by key.
        
        Args:
            key: Context key to delete
            
        Returns:
            True if deleted, False if not found
        """
        if key in self._contexts:
            del self._contexts[key]
            self._save()
            return True
        return False
    
    def clear(self):
        """Clear all contexts."""
        self._contexts.clear()
        self._save()
    
    def to_context_string(self, filter_app: Optional[str] = None) -> str:
        """
        Generate a formatted string of contexts for use in prompts.
        
        Args:
            filter_app: Optional application to filter by
            
        Returns:
            Formatted context string
        """
        contexts = self.get_by_application(filter_app) if filter_app else self.get_all()
        if not contexts:
            return ""
        
        lines = ["User Context (learned from recordings):"]
        for ctx in contexts:
            lines.append(
                f"  - {ctx.key}: {ctx.value} ({ctx.context_type.value}, {ctx.application})"
            )
        return "\n".join(lines)
    
    def stats(self) -> dict:
        """Get statistics about stored contexts."""
        type_counts = {}
        for ctx in self._contexts.values():
            type_name = ctx.context_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        return {
            "total_contexts": len(self._contexts),
            "by_type": type_counts,
            "store_path": str(self.store_path),
        }
