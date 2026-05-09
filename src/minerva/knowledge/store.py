"""
Minerva Knowledge Store — Multi-backend knowledge storage.

Tier 1 (always available):
- Markdown + Git: Source file versioning (llm-wiki-agent)
- SQLite FTS5: Full-text search
- LanceDB: Vector embeddings

Tier 2 (graceful degradation):
- Neo4j: Graph database (via Graphiti)
- Semantica: SHACL ontology + Allen temporal + Datalog
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


# ============================================================
# Data Models
# ============================================================

@dataclass
class Entity:
    id: str
    type: str  # Person|Org|Product|Publication|Concept|Metric|Event|Claim|Timeline
    name: str
    aliases: list[str] = field(default_factory=list)
    properties: dict = field(default_factory=dict)
    valid_from: str | None = None
    valid_until: str | None = None
    superseded_by: str | None = None
    source_ids: list[str] = field(default_factory=list)
    confidence: str = "MEDIUM"  # HIGH|MEDIUM|LOW
    recorded_at: str | None = None
    last_verified: str | None = None


@dataclass
class Relation:
    id: str
    subject_id: str
    predicate: str
    object_id: str
    valid_from: str | None = None
    valid_until: str | None = None
    confidence: str = "MEDIUM"
    source_ids: list[str] = field(default_factory=list)
    recorded_at: str | None = None


# ============================================================
# Abstract Interface
# ============================================================

class IKnowledgeStore(ABC):
    """Unified interface for knowledge storage operations."""

    @abstractmethod
    async def upsert_entity(self, entity: Entity) -> str:
        """Insert or update an entity. Returns entity ID."""
        ...

    @abstractmethod
    async def upsert_relation(self, rel: Relation) -> str:
        """Insert or update a relation. Returns relation ID."""
        ...

    @abstractmethod
    async def get_entity(self, entity_id: str) -> Entity | None:
        """Get entity by ID."""
        ...

    @abstractmethod
    async def search(
        self, query: str, mode: str = "hybrid", top_k: int = 20
    ) -> list[dict]:
        """Search knowledge base.

        Modes:
        - fulltext: SQLite FTS5 keyword search
        - semantic: LanceDB vector similarity
        - graph: Entity relationship traversal (Neo4j or SQLite CTE)
        - hybrid: Fulltext + semantic + graph, RRF fused
        - timeline: Time-ordered entity/event search
        """
        ...

    @abstractmethod
    async def ingest(self, source: str, source_type: str = "auto") -> dict:
        """Ingest content into knowledge base.

        Returns: {entity_count, relation_count, source_path}
        """
        ...

    @abstractmethod
    async def get_timeline(
        self, entity_id: str, from_date: str | None = None, to_date: str | None = None
    ) -> list[dict]:
        """Get chronological timeline for an entity."""
        ...

    @abstractmethod
    async def get_contradictions(self, entity_id: str | None = None) -> list[dict]:
        """Find contradictory claims related to an entity (or all if None)."""
        ...


# ============================================================
# SQLite Backend (Tier 1)
# ============================================================

class SQLiteKnowledgeStore(IKnowledgeStore):
    """Tier 1 knowledge store backed by SQLite + FTS5.

    Schema:
    - entities: id, type, name, aliases(JSON), properties(JSON), ...
    - entities_fts: FTS5 virtual table on (name, aliases)
    - relations: id, subject_id, predicate, object_id, ...
    - sources: id, path, content_hash, ingested_at, ...
    """

    def __init__(self, db_path: str = "~/minerva/knowledge.db"):
        import sqlite3
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """Create tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                aliases TEXT DEFAULT '[]',
                properties TEXT DEFAULT '{}',
                valid_from TEXT,
                valid_until TEXT,
                superseded_by TEXT,
                source_ids TEXT DEFAULT '[]',
                confidence TEXT DEFAULT 'MEDIUM',
                recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_verified TEXT
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts
                USING fts5(name, aliases, content='entities', content_rowid='rowid');
            CREATE TABLE IF NOT EXISTS relations (
                id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL REFERENCES entities(id),
                predicate TEXT NOT NULL,
                object_id TEXT NOT NULL REFERENCES entities(id),
                valid_from TEXT,
                valid_until TEXT,
                confidence TEXT DEFAULT 'MEDIUM',
                source_ids TEXT DEFAULT '[]',
                recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_rel_subject ON relations(subject_id);
            CREATE INDEX IF NOT EXISTS idx_rel_object ON relations(object_id);
            CREATE INDEX IF NOT EXISTS idx_rel_predicate ON relations(predicate);
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                source_type TEXT,
                ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        self.conn.commit()

    async def upsert_entity(self, entity: Entity) -> str:
        """
        Pseudocode:
        1. Check if entity with same name+type exists → UPDATE
        2. Else → INSERT
        3. Rebuild FTS5 index for this entity
        4. Return entity.id
        """
        import json as _json
        self.conn.execute("""
            INSERT OR REPLACE INTO entities (id, type, name, aliases, properties,
                valid_from, valid_until, superseded_by, source_ids, confidence, recorded_at, last_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
        """, (
            entity.id, entity.type, entity.name,
            _json.dumps(entity.aliases), _json.dumps(entity.properties),
            entity.valid_from, entity.valid_until, entity.superseded_by,
            _json.dumps(entity.source_ids), entity.confidence, entity.last_verified,
        ))
        self.conn.commit()
        return entity.id

    async def get_entity(self, entity_id: str) -> Entity | None:
        import json as _json
        row = self.conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        if row is None:
            return None
        return Entity(
            id=row["id"], type=row["type"], name=row["name"],
            aliases=_json.loads(row["aliases"]),
            properties=_json.loads(row["properties"]),
            valid_from=row["valid_from"], valid_until=row["valid_until"],
            superseded_by=row["superseded_by"],
            source_ids=_json.loads(row["source_ids"]),
            confidence=row["confidence"],
            recorded_at=row["recorded_at"], last_verified=row["last_verified"],
        )

    async def search(self, query: str, mode: str = "hybrid", top_k: int = 20) -> list[dict]:
        """Search entities by keyword (FTS5)."""
        rows = self.conn.execute(
            "SELECT e.* FROM entities e JOIN entities_fts f ON e.rowid = f.rowid "
            "WHERE entities_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, top_k)
        ).fetchall()
        return [dict(r) for r in rows]

    async def upsert_relation(self, rel: Relation) -> str:
        import json as _json
        self.conn.execute("""
            INSERT OR REPLACE INTO relations (id, subject_id, predicate, object_id,
                valid_from, valid_until, confidence, source_ids, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (rel.id, rel.subject_id, rel.predicate, rel.object_id,
              rel.valid_from, rel.valid_until, rel.confidence, _json.dumps(rel.source_ids)))
        self.conn.commit()
        return rel.id

    async def ingest(self, source: str, source_type: str = "auto") -> dict:
        """Ingest content into knowledge base.

        Pseudocode:
        1. Detect source_type: url, pdf, markdown, code
        2. Extract content:
           - URL → Jina Reader or BeautifulSoup
           - PDF → marker-pdf or PyMuPDF
           - Markdown → read directly
           - Code → tree-sitter parse
        3. Generate content hash (SHA-256)
        4. Check deduplication: if hash exists → skip
        5. Run spaCy NER for entity extraction
        6. For low-confidence entities → LLM confirmation
        7. Upsert entities and relations
        8. Update FTS5 index
        9. Return {entity_count, relation_count, source_path}
        """
        return {"entity_count": 0, "relation_count": 0, "source_path": source}

    async def get_timeline(self, entity_id: str, from_date: str | None = None, to_date: str | None = None) -> list[dict]:
        """Get chronological events related to entity."""
        query = """
            SELECT e.* FROM entities e
            JOIN relations r ON (e.id = r.object_id OR e.id = r.subject_id)
            WHERE (r.subject_id = ? OR r.object_id = ?)
              AND e.type = 'Event'
        """
        params = [entity_id, entity_id]
        if from_date:
            query += " AND e.valid_from >= ?"
            params.append(from_date)
        if to_date:
            query += " AND e.valid_from <= ?"
            params.append(to_date)
        query += " ORDER BY e.valid_from ASC"
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    async def get_contradictions(self, entity_id: str | None = None) -> list[dict]:
        """Find CONTRADICTS relations."""
        if entity_id:
            rows = self.conn.execute(
                "SELECT * FROM relations WHERE predicate = 'CONTRADICTS' AND (subject_id = ? OR object_id = ?)",
                (entity_id, entity_id)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM relations WHERE predicate = 'CONTRADICTS'"
            ).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# LanceDB Vector Backend (Tier 1)
# ============================================================

class LanceDBVectorStore:
    """Vector similarity search via LanceDB.

    Embedding model: sentence-transformers/all-MiniLM-L6-v2 (384d)
    """

    def __init__(self, db_path: str = "~/minerva/vectors", embedding_dim: int = 384):
        self.db_path = db_path
        self.dim = embedding_dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts.

        Pseudocode:
        1. Load sentence-transformers model (cached)
        2. model.encode(texts, batch_size=32)
        3. Return 384d float vectors
        """
        ...

    async def search(self, query: str, top_k: int = 20) -> list[dict]:
        """Semantic search.

        Pseudocode:
        1. embed(query) → query_vector
        2. table.search(query_vector).limit(top_k).to_list()
        3. Return [{id, content, similarity, metadata}, ...]
        """
        ...

    async def index_entities(self, entities: list[Entity]):
        """Index entities for semantic search.

        Pseudocode:
        1. texts = [f"{e.name}: {e.properties.get('description', '')}" for e in entities]
        2. vectors = embed(texts)
        3. table.add([{id, text, vector, metadata}, ...])
        """
        ...


# ============================================================
# KnowledgeStore Factory
# ============================================================

def create_knowledge_store(config: dict) -> IKnowledgeStore:
    """Create knowledge store based on configuration.

    Returns SQLiteKnowledgeStore (Tier 1) as primary.
    Tier 2 stores (Neo4j, Semantica) are added as wrappers if enabled.
    """
    store = SQLiteKnowledgeStore(db_path=config.get("sqlite_path", "~/minerva/knowledge.db"))
    logger.info("knowledge_store_created", backend="sqlite")
    return store
