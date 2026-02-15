"""
Axiom Memory Engine: Hybrid Vector + Graph + Cache

Combines three storage backends for optimal retrieval:
- Vector store (pgvector) for semantic similarity
- Graph store (Neo4j) for relationship traversal
- Cache (Redis) for fast repeated access
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Optional, Literal
from datetime import datetime
from uuid import uuid4
import numpy as np

# These would be real imports in production
import asyncpg
from neo4j import AsyncGraphDatabase
import aioredis


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class Memory:
    """Single memory item"""
    id: str
    agent_id: str
    content: str
    embedding: Optional[np.ndarray] = None
    metadata: dict = None
    relationships: list[dict] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.relationships is None:
            self.relationships = []
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "content": self.content,
            "metadata": self.metadata,
            "relationships": self.relationships,
            "timestamp": self.timestamp.isoformat()
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())

@dataclass
class SearchResult:
    """Result from memory search"""
    memory: Memory
    score: float  # Relevance score (0-1)
    source: Literal["vector", "graph", "cache"]


# ============================================================================
# VECTOR STORE (pgvector)
# ============================================================================

class VectorStore:
    """
    Vector store using PostgreSQL with pgvector extension
    
    Optimized for semantic similarity search using HNSW index
    """
    
    def __init__(self, connection_string: str, embedding_dims: int = 1536):
        self.connection_string = connection_string
        self.embedding_dims = embedding_dims
        self.pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self):
        """Initialize connection pool and create tables"""
        
        self.pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=5,
            max_size=20
        )
        
        async with self.pool.acquire() as conn:
            # Enable pgvector extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            
            # Create table with vector column
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS memory_vectors (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector({self.embedding_dims}) NOT NULL,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Create HNSW index for fast similarity search
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS memory_vectors_embedding_idx
                ON memory_vectors
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
            """)
            
            # Create index on agent_id for filtering
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS memory_vectors_agent_idx
                ON memory_vectors(agent_id)
            """)
    
    async def insert(
        self,
        memory_id: str,
        agent_id: str,
        content: str,
        embedding: np.ndarray,
        metadata: dict
    ):
        """Insert memory with vector"""
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO memory_vectors (id, agent_id, content, embedding, metadata)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (id) DO UPDATE
                SET content = $3,
                    embedding = $4,
                    metadata = $5,
                    updated_at = NOW()
            """, memory_id, agent_id, content, embedding.tolist(), json.dumps(metadata))
    
    async def search(
        self,
        agent_id: str,
        query_embedding: np.ndarray,
        k: int = 10,
        similarity_threshold: float = 0.7
    ) -> list[dict]:
        """
        Semantic similarity search using cosine distance
        
        Returns k most similar memories with score > threshold
        """
        
        async with self.pool.acquire() as conn:
            results = await conn.fetch("""
                SELECT
                    id,
                    agent_id,
                    content,
                    metadata,
                    1 - (embedding <=> $1::vector) as similarity,
                    created_at
                FROM memory_vectors
                WHERE agent_id = $2
                    AND 1 - (embedding <=> $1::vector) > $3
                ORDER BY embedding <=> $1::vector
                LIMIT $4
            """, query_embedding.tolist(), agent_id, similarity_threshold, k)
            
            return [dict(r) for r in results]
    
    async def delete(self, memory_id: str):
        """Delete memory by ID"""
        
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM memory_vectors WHERE id = $1",
                memory_id
            )
    
    async def close(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()


# ============================================================================
# GRAPH STORE (Neo4j)
# ============================================================================

class GraphStore:
    """
    Graph store using Neo4j for relationship traversal
    
    Stores entities and their relationships for contextual retrieval
    """
    
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.driver = None
    
    async def initialize(self):
        """Initialize Neo4j driver"""
        
        self.driver = AsyncGraphDatabase.driver(
            self.connection_string,
            max_connection_lifetime=3600
        )
        
        # Create constraints and indexes
        async with self.driver.session() as session:
            # Constraint on Memory nodes
            await session.run("""
                CREATE CONSTRAINT memory_id IF NOT EXISTS
                FOR (m:Memory) REQUIRE m.id IS UNIQUE
            """)
            
            # Index on agent_id
            await session.run("""
                CREATE INDEX memory_agent_idx IF NOT EXISTS
                FOR (m:Memory) ON (m.agent_id)
            """)
    
    async def store_memory_graph(
        self,
        memory_id: str,
        agent_id: str,
        nodes: list[dict],
        edges: list[dict]
    ):
        """
        Store memory with its graph structure
        
        Args:
            memory_id: Unique memory identifier
            agent_id: Agent that owns this memory
            nodes: List of {type, id, properties} dicts
            edges: List of {from, to, type, properties} dicts
        """
        
        async with self.driver.session() as session:
            # Create memory node
            await session.run("""
                MERGE (m:Memory {id: $memory_id})
                SET m.agent_id = $agent_id,
                    m.created_at = datetime()
            """, memory_id=memory_id, agent_id=agent_id)
            
            # Create entity nodes and connect to memory
            for node in nodes:
                await session.run(f"""
                    MERGE (e:{node['type']} {{id: $node_id}})
                    SET e += $properties
                    WITH e
                    MATCH (m:Memory {{id: $memory_id}})
                    MERGE (m)-[:CONTAINS]->(e)
                """,
                    node_id=node['id'],
                    properties=node.get('properties', {}),
                    memory_id=memory_id
                )
            
            # Create relationships between entities
            for edge in edges:
                await session.run(f"""
                    MATCH (from {{id: $from_id}})
                    MATCH (to {{id: $to_id}})
                    MERGE (from)-[r:{edge['type']}]->(to)
                    SET r += $properties
                """,
                    from_id=edge['from'],
                    to_id=edge['to'],
                    properties=edge.get('properties', {})
                )
    
    async def traverse(
        self,
        start_nodes: list[str],
        depth: int = 2,
        agent_id: Optional[str] = None
    ) -> list[dict]:
        """
        Traverse graph from start nodes
        
        Returns all nodes reachable within depth hops
        """
        
        async with self.driver.session() as session:
            query = f"""
                MATCH path = (start)-[*1..{depth}]-(connected)
                WHERE start.id IN $start_ids
            """
            
            if agent_id:
                query += """
                    AND EXISTS {
                        MATCH (m:Memory {agent_id: $agent_id})-[:CONTAINS]->(start)
                    }
                """
            
            query += """
                RETURN DISTINCT connected.id as id,
                       labels(connected) as types,
                       properties(connected) as properties,
                       length(path) as distance
                ORDER BY distance
                LIMIT 100
            """
            
            result = await session.run(
                query,
                start_ids=start_nodes,
                agent_id=agent_id
            )
            
            records = await result.data()
            return records
    
    async def find_related_memories(
        self,
        entity_ids: list[str],
        agent_id: str,
        limit: int = 10
    ) -> list[str]:
        """
        Find memories that contain any of the given entities
        """
        
        async with self.driver.session() as session:
            result = await session.run("""
                MATCH (m:Memory)-[:CONTAINS]->(e)
                WHERE e.id IN $entity_ids
                    AND m.agent_id = $agent_id
                RETURN DISTINCT m.id as memory_id,
                       count(e) as entity_count
                ORDER BY entity_count DESC
                LIMIT $limit
            """,
                entity_ids=entity_ids,
                agent_id=agent_id,
                limit=limit
            )
            
            records = await result.data()
            return [r['memory_id'] for r in records]
    
    async def close(self):
        """Close driver"""
        if self.driver:
            await self.driver.close()


# ============================================================================
# CACHE (Redis)
# ============================================================================

class CacheStore:
    """
    Redis cache for fast repeated access
    
    Caches frequently accessed memories and query results
    """
    
    def __init__(self, connection_string: str, ttl: int = 3600):
        self.connection_string = connection_string
        self.ttl = ttl
        self.redis = None
    
    async def initialize(self):
        """Initialize Redis connection"""
        self.redis = await aioredis.create_redis_pool(self.connection_string)
    
    async def get(self, key: str) -> Optional[dict]:
        """Get value from cache"""
        
        value = await self.redis.get(key)
        if value:
            return json.loads(value)
        return None
    
    async def set(self, key: str, value: dict, ttl: Optional[int] = None):
        """Set value in cache with TTL"""
        
        await self.redis.setex(
            key,
            ttl or self.ttl,
            json.dumps(value)
        )
    
    async def delete(self, key: str):
        """Delete key from cache"""
        await self.redis.delete(key)
    
    async def close(self):
        """Close connection"""
        if self.redis:
            self.redis.close()
            await self.redis.wait_closed()


# ============================================================================
# EMBEDDING MODEL
# ============================================================================

class EmbeddingModel:
    """
    Wrapper for embedding model
    
    Supports OpenAI, Cohere, or custom models
    """
    
    def __init__(self, model_name: str = "text-embedding-3-large"):
        self.model_name = model_name
        # In production, initialize actual embedding model here
    
    async def embed(self, text: str) -> np.ndarray:
        """Generate embedding for text"""
        
        # Placeholder - in production, call actual embedding API
        # For now, return random vector
        return np.random.rand(1536)
    
    async def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Generate embeddings for batch of texts"""
        
        # Placeholder
        return [await self.embed(text) for text in texts]


# ============================================================================
# HYBRID MEMORY ENGINE
# ============================================================================

class MemoryEngine:
    """
    Hybrid memory system combining vector, graph, and cache
    
    Provides intelligent retrieval using multiple strategies:
    - Vector: Semantic similarity
    - Graph: Relationship traversal
    - Cache: Fast repeated access
    """
    
    def __init__(
        self,
        postgres_url: str,
        neo4j_url: str,
        redis_url: str,
        embedding_dims: int = 1536,
        embedding_model: str = "text-embedding-3-large"
    ):
        self.vector = VectorStore(postgres_url, embedding_dims)
        self.graph = GraphStore(neo4j_url)
        self.cache = CacheStore(redis_url)
        self.embeddings = EmbeddingModel(embedding_model)
    
    async def initialize(self):
        """Initialize all backends"""
        
        await asyncio.gather(
            self.vector.initialize(),
            self.graph.initialize(),
            self.cache.initialize()
        )
    
    async def store(
        self,
        agent_id: str,
        memory: Memory
    ) -> str:
        """
        Store memory across all backends
        
        Returns memory_id for later retrieval
        """
        
        memory_id = memory.id or str(uuid4())
        
        # 1. Generate embeddings if needed
        if not memory.embedding and memory.content:
            memory.embedding = await self.embeddings.embed(memory.content)
        
        # 2. Store in vector DB for semantic search
        if memory.embedding is not None:
            await self.vector.insert(
                memory_id=memory_id,
                agent_id=agent_id,
                content=memory.content,
                embedding=memory.embedding,
                metadata=memory.metadata
            )
        
        # 3. Store relationships in graph
        if memory.relationships:
            nodes = [r for r in memory.relationships if r.get('type') == 'node']
            edges = [r for r in memory.relationships if r.get('type') == 'edge']
            
            await self.graph.store_memory_graph(
                memory_id=memory_id,
                agent_id=agent_id,
                nodes=nodes,
                edges=edges
            )
        
        # 4. Cache for fast retrieval
        await self.cache.set(
            key=f"memory:{agent_id}:{memory_id}",
            value=memory.to_dict()
        )
        
        return memory_id
    
    async def store_batch(
        self,
        agent_id: str,
        updates: list[dict]
    ):
        """Store batch of memory updates"""
        
        tasks = []
        for update in updates:
            memory = Memory(
                id=str(uuid4()),
                agent_id=agent_id,
                content=update.get('content', ''),
                metadata=update.get('metadata', {})
            )
            tasks.append(self.store(agent_id, memory))
        
        await asyncio.gather(*tasks)
    
    async def recall(
        self,
        agent_id: str,
        query: str,
        k: int = 5,
        strategy: Literal["hybrid", "vector", "graph"] = "hybrid"
    ) -> list[SearchResult]:
        """
        Recall memories using specified strategy
        
        Hybrid: Combines vector similarity + graph traversal
        Vector: Pure semantic similarity
        Graph: Pure relationship traversal
        """
        
        if strategy == "vector":
            return await self._vector_search(agent_id, query, k)
        
        if strategy == "graph":
            return await self._graph_search(agent_id, query, k)
        
        # Hybrid search (default)
        return await self._hybrid_search(agent_id, query, k)
    
    async def _vector_search(
        self,
        agent_id: str,
        query: str,
        k: int
    ) -> list[SearchResult]:
        """Pure vector similarity search"""
        
        # Generate query embedding
        query_embedding = await self.embeddings.embed(query)
        
        # Search vector store
        results = await self.vector.search(
            agent_id=agent_id,
            query_embedding=query_embedding,
            k=k
        )
        
        # Convert to SearchResult
        return [
            SearchResult(
                memory=Memory(
                    id=r['id'],
                    agent_id=r['agent_id'],
                    content=r['content'],
                    metadata=r['metadata']
                ),
                score=r['similarity'],
                source="vector"
            )
            for r in results
        ]
    
    async def _graph_search(
        self,
        agent_id: str,
        query: str,
        k: int
    ) -> list[SearchResult]:
        """Pure graph traversal search"""
        
        # This is simplified - in production, would extract entities from query
        # For now, just return empty
        return []
    
    async def _hybrid_search(
        self,
        agent_id: str,
        query: str,
        k: int
    ) -> list[SearchResult]:
        """
        Hybrid search combining vector + graph
        
        Algorithm:
        1. Vector search for top-k*2 semantically similar memories
        2. Graph traversal to find related context
        3. Rank by combined score
        4. Return top-k overall
        """
        
        # Step 1: Vector similarity search (get more candidates)
        query_embedding = await self.embeddings.embed(query)
        
        vector_results = await self.vector.search(
            agent_id=agent_id,
            query_embedding=query_embedding,
            k=k * 2
        )
        
        # Step 2: For each result, get connected graph context
        enriched_results = []
        
        for result in vector_results:
            memory_id = result['id']
            
            # Get related entities from graph
            # (Simplified - in production would extract entity IDs from memory)
            related = []
            
            enriched_results.append({
                "memory": result,
                "vector_score": result['similarity'],
                "related_context": related
            })
        
        # Step 3: Rerank based on combined score
        ranked = self._rerank_hybrid(enriched_results, query)
        
        # Step 4: Return top-k
        return ranked[:k]
    
    def _rerank_hybrid(
        self,
        results: list[dict],
        query: str
    ) -> list[SearchResult]:
        """
        Rerank results using hybrid scoring:
        - 0.6 * vector_similarity
        - 0.3 * graph_connectivity
        - 0.1 * recency
        """
        
        scored = []
        for r in results:
            graph_score = len(r["related_context"]) / 10  # Normalize
            recency_score = self._recency_score(
                r["memory"].get('created_at', datetime.now())
            )
            
            final_score = (
                0.6 * r["vector_score"] +
                0.3 * graph_score +
                0.1 * recency_score
            )
            
            memory = Memory(
                id=r["memory"]['id'],
                agent_id=r["memory"]['agent_id'],
                content=r["memory"]['content'],
                metadata=r["memory"]['metadata']
            )
            
            scored.append((
                final_score,
                SearchResult(memory=memory, score=final_score, source="hybrid")
            ))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        
        return [result for _, result in scored]
    
    def _recency_score(self, timestamp: datetime) -> float:
        """Calculate recency score (0-1)"""
        
        age_seconds = (datetime.now() - timestamp).total_seconds()
        age_days = age_seconds / 86400
        
        # Exponential decay: score = e^(-age_days/30)
        return np.exp(-age_days / 30)
    
    async def close(self):
        """Close all connections"""
        await asyncio.gather(
            self.vector.close(),
            self.graph.close(),
            self.cache.close()
        )


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

async def example_usage():
    """Example of using MemoryEngine"""
    
    # Initialize engine
    engine = MemoryEngine(
        postgres_url="postgresql://localhost/axiom",
        neo4j_url="bolt://localhost:7687",
        redis_url="redis://localhost:6379"
    )
    
    await engine.initialize()
    
    # Store memory
    memory = Memory(
        id=str(uuid4()),
        agent_id="research_agent",
        content="Apple Inc is a technology company founded by Steve Jobs",
        relationships=[
            {"type": "node", "id": "apple", "properties": {"name": "Apple Inc"}},
            {"type": "node", "id": "jobs", "properties": {"name": "Steve Jobs"}},
            {"type": "edge", "from": "jobs", "to": "apple", "properties": {"relationship": "founded"}}
        ]
    )
    
    memory_id = await engine.store("research_agent", memory)
    print(f"Stored memory: {memory_id}")
    
    # Recall memories
    results = await engine.recall(
        agent_id="research_agent",
        query="Tell me about Apple",
        k=5,
        strategy="hybrid"
    )
    
    for result in results:
        print(f"Score: {result.score:.3f} | {result.memory.content}")
    
    await engine.close()


if __name__ == "__main__":
    asyncio.run(example_usage())
