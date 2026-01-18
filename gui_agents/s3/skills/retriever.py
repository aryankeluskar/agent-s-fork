"""
Hybrid Skill Retriever for Agent-S

Implements hybrid search combining semantic similarity and BM25 keyword matching
for robust skill retrieval across different query types.
"""

import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, List

from .models import Skill, Step
from .store import SkillStore


@dataclass
class RetrievalResult:
    """Result from skill retrieval."""
    skill: Skill
    score: float
    matched_steps: List[tuple]  # List of (Step, score) tuples
    match_reason: str  # "semantic", "bm25", or "hybrid"


class BM25:
    """
    BM25 keyword-based retrieval algorithm.
    
    Provides term-frequency based matching for cases where
    semantic similarity might miss exact keyword matches.
    """
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        Initialize BM25 with tuning parameters.
        
        Args:
            k1: Term frequency saturation parameter
            b: Length normalization parameter
        """
        self.k1 = k1
        self.b = b
        self.doc_lengths: dict[str, int] = {}
        self.avg_doc_length: float = 0
        self.doc_freqs: dict[str, int] = defaultdict(int)
        self.term_freqs: dict[str, dict[str, int]] = {}
        self.corpus_size: int = 0
    
    def fit(self, documents: dict[str, str]) -> None:
        """
        Build BM25 index from documents.
        
        Args:
            documents: Dict mapping doc_id -> document text
        """
        self.corpus_size = len(documents)
        total_length = 0
        
        for doc_id, text in documents.items():
            tokens = self._tokenize(text)
            self.doc_lengths[doc_id] = len(tokens)
            total_length += len(tokens)
            
            self.term_freqs[doc_id] = defaultdict(int)
            seen_terms = set()
            for token in tokens:
                self.term_freqs[doc_id][token] += 1
                if token not in seen_terms:
                    self.doc_freqs[token] += 1
                    seen_terms.add(token)
        
        self.avg_doc_length = total_length / max(self.corpus_size, 1)
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into words."""
        text = text.lower()
        # Replace non-alphanumeric with spaces
        cleaned = []
        for char in text:
            if char.isalnum() or char.isspace():
                cleaned.append(char)
            else:
                cleaned.append(' ')
        return ''.join(cleaned).split()
    
    def score(self, query: str, doc_id: str) -> float:
        """
        Calculate BM25 score for a query-document pair.
        
        Args:
            query: Search query
            doc_id: Document ID
            
        Returns:
            BM25 score
        """
        if doc_id not in self.term_freqs:
            return 0.0
        
        query_tokens = self._tokenize(query)
        score = 0.0
        doc_length = self.doc_lengths[doc_id]
        
        for term in query_tokens:
            if term not in self.term_freqs[doc_id]:
                continue
            
            tf = self.term_freqs[doc_id][term]
            df = self.doc_freqs[term]
            
            # IDF
            idf = math.log((self.corpus_size - df + 0.5) / (df + 0.5) + 1)
            
            # TF component with saturation
            tf_component = (tf * (self.k1 + 1)) / (
                tf + self.k1 * (1 - self.b + self.b * doc_length / self.avg_doc_length)
            )
            
            score += idf * tf_component
        
        return score
    
    def search(self, query: str, top_k: int = 10) -> List[tuple]:
        """
        Search for documents matching query.
        
        Args:
            query: Search query
            top_k: Number of results to return
            
        Returns:
            List of (doc_id, score) tuples sorted by score
        """
        scores = []
        for doc_id in self.term_freqs:
            score = self.score(query, doc_id)
            if score > 0:
                scores.append((doc_id, score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


# Prompt for extracting metadata from query
METADATA_EXTRACTION_PROMPT = """Extract metadata from this user query for filtering workflow skills.

Query: {query}

Extract:
1. Operating system mentioned (if any): macOS, Windows, Linux, or null
2. Application mentioned (if any): the specific app name, or null

Return JSON only:
{{"os": "macOS|Windows|Linux|null", "app": "app name or null"}}"""


class SkillRetriever:
    """
    Hybrid skill retriever combining semantic and BM25 search.
    
    Provides robust retrieval across different query types:
    - Semantic: "How do I resize images?" 
    - Keyword: "GIMP resize 800x600"
    - Hybrid: "resize image in GIMP to 800px"
    """
    
    def __init__(
        self,
        store: SkillStore,
        model: str = "openai/gpt-4o-mini",
    ):
        """
        Initialize the retriever.
        
        Args:
            store: SkillStore instance
            model: LLM model for metadata extraction
        """
        self.store = store
        self.model = model
        self.bm25 = BM25()
        self._build_bm25_index()
        
        # Initialize OpenAI client
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
    
    def _build_bm25_index(self) -> None:
        """Build BM25 index from all skills."""
        documents = {}
        for skill in self.store.get_all_skills():
            documents[skill.id] = skill.to_full_embedding_text()
        if documents:
            self.bm25.fit(documents)
    
    def refresh_index(self) -> None:
        """Refresh the BM25 index after adding skills."""
        self._build_bm25_index()
    
    def retrieve(
        self,
        query: str,
        n_results: int = 5,
        os_filter: Optional[str] = None,
        app_filter: Optional[str] = None,
        use_hybrid: bool = True,
        semantic_weight: float = 0.7,
    ) -> List[RetrievalResult]:
        """
        Retrieve skills matching a query.
        
        Args:
            query: Search query
            n_results: Maximum number of results
            os_filter: Filter by operating system
            app_filter: Filter by application
            use_hybrid: Whether to use hybrid (semantic + BM25) search
            semantic_weight: Weight for semantic scores (BM25 gets 1 - this)
            
        Returns:
            List of RetrievalResult objects
        """
        # Get semantic results
        semantic_results = self.store.search_skills(
            query=query,
            n_results=n_results * 2,  # Get more for merging
            os_filter=os_filter,
            app_filter=app_filter,
        )
        
        if not use_hybrid:
            return self._convert_to_results(semantic_results, "semantic")
        
        # Get BM25 results
        bm25_results = self.bm25.search(query, top_k=n_results * 2)
        bm25_scores = {doc_id: score for doc_id, score in bm25_results}
        
        # Combine scores
        combined_scores: dict[str, tuple] = {}  # skill_id -> (Skill, score, reason)
        
        # Add semantic results
        if semantic_results:
            max_sem = max(score for _, score in semantic_results) or 1
            for skill, score in semantic_results:
                norm_score = score / max_sem
                combined_scores[skill.id] = (skill, norm_score * semantic_weight, "semantic")
        
        # Add BM25 results
        if bm25_scores:
            max_bm25 = max(bm25_scores.values()) or 1
            bm25_weight = 1 - semantic_weight
            for skill_id, score in bm25_scores.items():
                norm_score = score / max_bm25
                skill = self.store.get_skill(skill_id)
                if skill:
                    if skill_id in combined_scores:
                        existing_skill, existing_score, _ = combined_scores[skill_id]
                        combined_scores[skill_id] = (
                            existing_skill,
                            existing_score + norm_score * bm25_weight,
                            "hybrid"
                        )
                    else:
                        combined_scores[skill_id] = (skill, norm_score * bm25_weight, "bm25")
        
        # Sort by combined score
        sorted_results = sorted(
            combined_scores.values(),
            key=lambda x: x[1],
            reverse=True
        )[:n_results]
        
        return [
            RetrievalResult(
                skill=skill,
                score=score,
                matched_steps=[],
                match_reason=reason
            )
            for skill, score, reason in sorted_results
        ]
    
    def retrieve_with_steps(
        self,
        query: str,
        n_skills: int = 3,
        n_steps_per_skill: int = 3,
        os_filter: Optional[str] = None,
        app_filter: Optional[str] = None,
    ) -> List[RetrievalResult]:
        """
        Retrieve skills with their most relevant steps.
        
        Args:
            query: Search query
            n_skills: Number of skills to retrieve
            n_steps_per_skill: Number of steps per skill
            os_filter: Filter by OS
            app_filter: Filter by application
            
        Returns:
            List of RetrievalResult with matched_steps populated
        """
        # Get skills
        skill_results = self.retrieve(
            query=query,
            n_results=n_skills,
            os_filter=os_filter,
            app_filter=app_filter,
        )
        
        # Get matching steps for each skill
        for result in skill_results:
            step_results = self.store.search_steps(
                query=query,
                n_results=n_steps_per_skill,
                skill_id_filter=result.skill.id,
            )
            result.matched_steps = [(step, score) for _, step, score in step_results]
        
        return skill_results
    
    def retrieve_composable(
        self,
        goal: str,
        sub_goals: List[str],
        n_results_per_goal: int = 2,
    ) -> List[List[RetrievalResult]]:
        """
        Retrieve skills for multiple sub-goals for composition.
        
        Args:
            goal: Overall goal (for context)
            sub_goals: List of sub-goals to retrieve for
            n_results_per_goal: Number of results per sub-goal
            
        Returns:
            List of result lists, one per sub-goal
        """
        all_results = []
        
        for sub_goal in sub_goals:
            results = self.retrieve(
                query=sub_goal,
                n_results=n_results_per_goal,
                use_hybrid=True,
            )
            all_results.append(results)
        
        return all_results
    
    def find_skill_chain(
        self,
        start_skill_id: str,
        target_postcondition: str,
        max_depth: int = 3,
    ) -> List[Skill]:
        """
        Find a chain of skills leading to a target postcondition.
        
        Args:
            start_skill_id: ID of starting skill
            target_postcondition: Desired final state
            max_depth: Maximum chain length
            
        Returns:
            List of skills forming the chain
        """
        start_skill = self.store.get_skill(start_skill_id)
        if not start_skill:
            return []
        
        # Check if start skill already achieves target
        if any(target_postcondition.lower() in pc.lower() for pc in start_skill.postconditions):
            return [start_skill]
        
        # BFS to find chain
        chain = [start_skill]
        visited = {start_skill_id}
        
        for _ in range(max_depth - 1):
            current_skill = chain[-1]
            chainable = self.store.find_chainable_skills(current_skill)
            
            # Check if any chainable skill achieves target
            for candidate in chainable:
                if candidate.id in visited:
                    continue
                
                if any(target_postcondition.lower() in pc.lower() for pc in candidate.postconditions):
                    chain.append(candidate)
                    return chain
                
                visited.add(candidate.id)
            
            # Take first unvisited chainable skill
            if chainable:
                for c in chainable:
                    if c.id not in visited:
                        chain.append(c)
                        visited.add(c.id)
                        break
                else:
                    break
            else:
                break
        
        return chain
    
    def _convert_to_results(
        self,
        skill_scores: List[tuple],
        match_reason: str
    ) -> List[RetrievalResult]:
        """Convert (skill, score) tuples to RetrievalResult objects."""
        return [
            RetrievalResult(
                skill=skill,
                score=score,
                matched_steps=[],
                match_reason=match_reason
            )
            for skill, score in skill_scores
        ]
    
    def extract_metadata_from_query(self, query: str) -> dict:
        """
        Extract OS and application filters from a natural language query.
        
        Args:
            query: User query
            
        Returns:
            Dict with optional "os" and "app" keys
        """
        if not self.client:
            return {}
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": METADATA_EXTRACTION_PROMPT.format(query=query)}
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
            
            result = {}
            if data.get("os") and data["os"] != "null":
                result["os"] = data["os"]
            if data.get("app") and data["app"] != "null":
                result["app"] = data["app"]
            
            return result
            
        except Exception:
            return {}
