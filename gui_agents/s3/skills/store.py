"""
Skill Store for Agent-S

A hierarchical vector store for workflow skills using ChromaDB.
Supports semantic search, metadata filtering, and skill composition.
"""

import json
import os
from pathlib import Path
from typing import Optional, List, Tuple

from .models import Skill, Step
from .context_store import UserContextStore


# Default store path
DEFAULT_STORE_PATH = Path(__file__).parent.parent.parent.parent / "skill_store"


# Prompt for checking if postcondition matches precondition
CONDITION_MATCH_PROMPT = """Determine if a workflow's postcondition can satisfy another workflow's precondition.

Postcondition (what the first workflow produces): {postcondition}
Precondition (what the second workflow needs): {precondition}

Consider semantic meaning, not just string matching. For example:
- "file_created" can satisfy "file_exists"
- "app_opened:chrome" can satisfy "browser_available"
- "user_logged_in" can satisfy "user_authenticated"

Return JSON only:
{{"matches": true|false, "reason": "brief explanation"}}"""


class SkillStore:
    """
    Hierarchical vector store for workflow skills.
    
    Stores skills at two levels:
    1. Skill level: Workflow summaries for high-level matching
    2. Step level: Individual steps for detailed retrieval
    
    Uses ChromaDB for vector storage and supports semantic search
    with metadata filtering.
    """
    
    def __init__(
        self,
        store_path: Optional[Path] = None,
        use_sentence_transformers: bool = True,
        model: str = "openai/gpt-4o-mini",
    ):
        """
        Initialize the skill store.
        
        Args:
            store_path: Path to store data (default: skill_store in project root)
            use_sentence_transformers: Whether to use sentence-transformers for embeddings
            model: LLM model for condition matching
        """
        self.store_path = store_path or DEFAULT_STORE_PATH
        self.store_path.mkdir(parents=True, exist_ok=True)
        self.model = model
        
        # Initialize OpenAI client for condition matching
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=api_key,
                )
            except ImportError:
                self.client = None
        else:
            self.client = None
        
        # Initialize ChromaDB
        self._init_chromadb(use_sentence_transformers)
        
        # Initialize JSON cache for full skill data
        self.skills_json_path = self.store_path / "skills.json"
        self._skills_cache: dict[str, Skill] = {}
        self._load_skills_cache()
        
        # Initialize context store
        self.context_store = UserContextStore(self.store_path)
    
    def _init_chromadb(self, use_sentence_transformers: bool):
        """Initialize ChromaDB with appropriate embedding function."""
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise ImportError(
                "chromadb is required for the skill store. "
                "Install with: pip install chromadb"
            )
        
        # Create persistent client
        self.chroma_client = chromadb.PersistentClient(
            path=str(self.store_path / "chroma"),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Create embedding function
        self.embedding_function = self._create_embedding_function(use_sentence_transformers)
        
        # Create collections
        self.skills_collection = self.chroma_client.get_or_create_collection(
            name="skills",
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"}
        )
        
        self.steps_collection = self.chroma_client.get_or_create_collection(
            name="steps",
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"}
        )
    
    def _create_embedding_function(self, use_sentence_transformers: bool):
        """Create embedding function for ChromaDB."""
        try:
            from chromadb.utils import embedding_functions
            
            if use_sentence_transformers:
                try:
                    return embedding_functions.SentenceTransformerEmbeddingFunction(
                        model_name="all-MiniLM-L6-v2"
                    )
                except Exception as e:
                    print(f"Warning: Could not load sentence-transformers: {e}")
            
            # Fallback to default
            return embedding_functions.DefaultEmbeddingFunction()
            
        except Exception as e:
            print(f"Warning: Using default embedding: {e}")
            return None
    
    def _load_skills_cache(self):
        """Load skills from JSON cache."""
        if self.skills_json_path.exists():
            try:
                data = json.loads(self.skills_json_path.read_text())
                for skill_data in data:
                    skill = Skill.from_dict(skill_data)
                    self._skills_cache[skill.id] = skill
            except Exception as e:
                print(f"Warning: Could not load skills cache: {e}")
    
    def _save_skills_cache(self):
        """Save skills to JSON cache."""
        data = [skill.to_dict() for skill in self._skills_cache.values()]
        self.skills_json_path.write_text(json.dumps(data, indent=2))
    
    def add_skill(self, skill: Skill) -> None:
        """
        Add a skill to the store.
        
        Args:
            skill: Skill to add
        """
        # Add to cache
        self._skills_cache[skill.id] = skill
        
        # Build metadata for ChromaDB
        param_values = [p.example for p in skill.parameters]
        
        # Add to skills collection
        self.skills_collection.upsert(
            ids=[skill.id],
            documents=[skill.to_full_embedding_text()],
            metadatas=[{
                "name": skill.name,
                "summary": skill.summary[:500] if skill.summary else "",
                "os": skill.metadata.operating_system,
                "apps": ",".join(skill.metadata.applications),
                "suitability": skill.metadata.automation_suitability,
                "source_file": skill.metadata.source_file,
                "preconditions": ",".join(skill.preconditions),
                "postconditions": ",".join(skill.postconditions),
                "parameters": ",".join(param_values),
            }]
        )
        
        # Add steps to steps collection
        for step in skill.steps:
            step_id = f"{skill.id}_step_{step.number}"
            self.steps_collection.upsert(
                ids=[step_id],
                documents=[step.to_embedding_text()],
                metadatas=[{
                    "skill_id": skill.id,
                    "skill_name": skill.name,
                    "step_number": step.number,
                    "title": step.title,
                    "action_type": step.action_type.value if step.action_type else "",
                    "ui_element": step.ui_element or "",
                    "purpose": step.purpose,
                }]
            )
        
        # Add user context to context store
        if skill.user_context:
            self.context_store.add_many(skill.user_context)
        
        # Save cache
        self._save_skills_cache()
    
    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """
        Get a skill by ID.
        
        Args:
            skill_id: Skill ID
            
        Returns:
            Skill or None if not found
        """
        return self._skills_cache.get(skill_id)
    
    def get_all_skills(self) -> List[Skill]:
        """
        Get all stored skills.
        
        Returns:
            List of all skills
        """
        return list(self._skills_cache.values())
    
    def search_skills(
        self,
        query: str,
        n_results: int = 5,
        os_filter: Optional[str] = None,
        app_filter: Optional[str] = None,
    ) -> List[Tuple[Skill, float]]:
        """
        Search for skills by semantic similarity.
        
        Args:
            query: Search query
            n_results: Maximum number of results
            os_filter: Filter by operating system
            app_filter: Filter by application
            
        Returns:
            List of (skill, similarity_score) tuples
        """
        # Build filter
        where_filter = None
        conditions = []
        
        if os_filter:
            conditions.append({"os": {"$eq": os_filter}})
        if app_filter:
            conditions.append({"apps": {"$contains": app_filter}})
        
        if len(conditions) == 1:
            where_filter = conditions[0]
        elif len(conditions) > 1:
            where_filter = {"$and": conditions}
        
        # Query ChromaDB
        results = self.skills_collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where_filter,
            include=["distances", "metadatas"]
        )
        
        # Convert to (Skill, score) tuples
        skill_scores = []
        if results["ids"] and results["ids"][0]:
            for i, skill_id in enumerate(results["ids"][0]):
                skill = self.get_skill(skill_id)
                if skill:
                    distance = results["distances"][0][i] if results["distances"] else 0
                    similarity = 1 - distance  # Convert distance to similarity
                    skill_scores.append((skill, similarity))
        
        return skill_scores
    
    def search_steps(
        self,
        query: str,
        n_results: int = 10,
        skill_id_filter: Optional[str] = None,
        action_type_filter: Optional[str] = None,
    ) -> List[Tuple[str, Step, float]]:
        """
        Search for individual steps by semantic similarity.
        
        Args:
            query: Search query
            n_results: Maximum number of results
            skill_id_filter: Filter by skill ID
            action_type_filter: Filter by action type
            
        Returns:
            List of (skill_id, step, similarity_score) tuples
        """
        # Build filter
        where_filter = None
        conditions = []
        
        if skill_id_filter:
            conditions.append({"skill_id": {"$eq": skill_id_filter}})
        if action_type_filter:
            conditions.append({"action_type": {"$eq": action_type_filter}})
        
        if len(conditions) == 1:
            where_filter = conditions[0]
        elif len(conditions) > 1:
            where_filter = {"$and": conditions}
        
        # Query ChromaDB
        results = self.steps_collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where_filter,
            include=["distances", "metadatas"]
        )
        
        # Convert to (skill_id, Step, score) tuples
        step_results = []
        if results["ids"] and results["ids"][0]:
            for i, step_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i]
                skill_id = metadata["skill_id"]
                skill = self.get_skill(skill_id)
                if skill:
                    step_number = metadata["step_number"]
                    for step in skill.steps:
                        if step.number == step_number:
                            distance = results["distances"][0][i] if results["distances"] else 0
                            similarity = 1 - distance
                            step_results.append((skill_id, step, similarity))
                            break
        
        return step_results
    
    def find_skills_by_postcondition(self, postcondition: str) -> List[Skill]:
        """
        Find skills that produce a specific postcondition.
        
        Args:
            postcondition: Postcondition to search for
            
        Returns:
            List of matching skills
        """
        matching = []
        for skill in self._skills_cache.values():
            for pc in skill.postconditions:
                if postcondition.lower() in pc.lower():
                    matching.append(skill)
                    break
        return matching
    
    def find_skills_by_precondition(self, precondition: str) -> List[Skill]:
        """
        Find skills that require a specific precondition.
        
        Args:
            precondition: Precondition to search for
            
        Returns:
            List of matching skills
        """
        matching = []
        for skill in self._skills_cache.values():
            for pre in skill.preconditions:
                if precondition.lower() in pre.lower():
                    matching.append(skill)
                    break
        return matching
    
    def find_chainable_skills(self, skill: Skill) -> List[Skill]:
        """
        Find skills that can be chained after this skill.
        
        A skill B can chain after skill A if A's postconditions
        satisfy B's preconditions.
        
        Args:
            skill: Starting skill
            
        Returns:
            List of chainable skills
        """
        chainable = []
        for candidate in self._skills_cache.values():
            if candidate.id == skill.id:
                continue
            
            for post in skill.postconditions:
                for pre in candidate.preconditions:
                    if self._conditions_match(post, pre):
                        chainable.append(candidate)
                        break
        return chainable
    
    def _conditions_match(self, postcondition: str, precondition: str) -> bool:
        """
        Check if a postcondition can satisfy a precondition.
        
        Uses string matching first, then LLM for semantic matching.
        """
        # Exact match
        if postcondition.lower() == precondition.lower():
            return True
        
        # Simple substring match
        if postcondition.lower() in precondition.lower() or precondition.lower() in postcondition.lower():
            return True
        
        # LLM-based matching (if available)
        if not self.client:
            return False
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": CONDITION_MATCH_PROMPT.format(
                        postcondition=postcondition,
                        precondition=precondition
                    )}
                ],
                max_tokens=100,
                temperature=0.1,
            )
            
            content = response.choices[0].message.content.strip()
            
            # Extract JSON
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                content = "\n".join(lines)
            
            data = json.loads(content)
            return data.get("matches", False)
            
        except Exception:
            return False
    
    def delete_skill(self, skill_id: str) -> bool:
        """
        Delete a skill from the store.
        
        Args:
            skill_id: ID of skill to delete
            
        Returns:
            True if deleted, False if not found
        """
        if skill_id not in self._skills_cache:
            return False
        
        skill = self._skills_cache[skill_id]
        
        # Delete from ChromaDB
        self.skills_collection.delete(ids=[skill_id])
        
        step_ids = [f"{skill_id}_step_{s.number}" for s in skill.steps]
        if step_ids:
            self.steps_collection.delete(ids=step_ids)
        
        # Delete from cache
        del self._skills_cache[skill_id]
        self._save_skills_cache()
        
        return True
    
    def clear(self) -> None:
        """Clear all skills from the store."""
        # Recreate collections
        self.chroma_client.delete_collection("skills")
        self.chroma_client.delete_collection("steps")
        
        self.skills_collection = self.chroma_client.create_collection(
            name="skills",
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"}
        )
        self.steps_collection = self.chroma_client.create_collection(
            name="steps",
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"}
        )
        
        # Clear cache
        self._skills_cache.clear()
        self._save_skills_cache()
    
    def stats(self) -> dict:
        """Get statistics about the store."""
        return {
            "total_skills": len(self._skills_cache),
            "total_steps": sum(len(s.steps) for s in self._skills_cache.values()),
            "store_path": str(self.store_path),
        }
