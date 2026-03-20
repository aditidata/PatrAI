"""
PatrAI — Thread memory using sentence-transformers and ChromaDB.

Provides semantic storage and retrieval of email thread context.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded globals to avoid slow startup
_model = None
_chroma_client = None
_collection = None


def _get_model():
    """Lazy-load the sentence transformer model on first use."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading SentenceTransformer model 'all-MiniLM-L6-v2'")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _get_collection():
    """Lazy-initialize ChromaDB client and collection on first use."""
    global _chroma_client, _collection
    if _collection is None:
        import chromadb
        logger.info("Initializing ChromaDB PersistentClient at './chroma_db'")
        _chroma_client = chromadb.PersistentClient(path="./chroma_db")
        _collection = _chroma_client.get_or_create_collection(name="email_threads")
    return _collection


def embed_and_store(thread_id: str, text: str) -> None:
    """
    Embed the given text and upsert it into ChromaDB keyed by thread_id.

    Args:
        thread_id: Unique identifier for the email thread.
        text: Concatenated thread text to embed and store.
    """
    model = _get_model()
    collection = _get_collection()

    embedding = model.encode(text)
    collection.upsert(
        ids=[thread_id],
        embeddings=[embedding.tolist()],
        documents=[text],
        metadatas=[{"thread_id": thread_id}],
    )
    logger.info("Stored embedding for thread_id=%s", thread_id)


def retrieve_context(thread_id: str, query: str, top_k: int = 3) -> list[str]:
    """
    Retrieve the top-k semantically similar documents from ChromaDB.

    Args:
        thread_id: The thread identifier (used for logging context).
        query: The query text to embed and search against.
        top_k: Maximum number of results to return (default 3).

    Returns:
        A list of document strings. Returns [] if the collection is empty
        or no results are found.
    """
    try:
        collection = _get_collection()

        # Guard against querying an empty collection
        count = collection.count()
        if count == 0:
            return []

        model = _get_model()
        query_embedding = model.encode(query)

        # Clamp n_results to the number of stored documents
        n_results = min(top_k, count)
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=n_results,
        )

        documents = results.get("documents", [[]])[0]
        logger.info(
            "Retrieved %d context documents for thread_id=%s",
            len(documents),
            thread_id,
        )
        return documents if documents else []

    except Exception:
        logger.exception("Failed to retrieve context for thread_id=%s", thread_id)
        return []
