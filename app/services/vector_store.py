"""
vector_store.py — FAISS vector store with HuggingFace embeddings.
Loads all .txt files from database/learning_data/ into a searchable index.
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_vector_store = None
_embeddings = None


def _get_embeddings():
    """Lazy-load the embedding model."""
    global _embeddings
    if _embeddings is None:
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            from config import EMBEDDING_MODEL
            _embeddings = HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
            logger.info("Embeddings model loaded: %s", EMBEDDING_MODEL)
        except Exception as e:
            logger.error("Failed to load embeddings: %s", e)
            raise
    return _embeddings


def build_vector_store():
    """Build or rebuild the FAISS vector store from learning_data files."""
    global _vector_store
    try:
        from langchain_community.vectorstores import FAISS
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_core.documents import Document
        from config import LEARNING_DATA_DIR, VECTOR_STORE_DIR, CHUNK_SIZE, CHUNK_OVERLAP

        # Collect all .txt files
        text_files = sorted(LEARNING_DATA_DIR.glob("*.txt"))
        if not text_files:
            logger.info("No learning data files found. Vector store not built.")
            _vector_store = None
            return

        documents = []
        for file_path in text_files:
            try:
                content = file_path.read_text(encoding="utf-8").strip()
                if content:
                    documents.append(Document(
                        page_content=content,
                        metadata={"source": file_path.name}
                    ))
            except Exception as e:
                logger.warning("Could not read %s: %s", file_path, e)

        if not documents:
            logger.info("No content found in learning data files.")
            _vector_store = None
            return

        # Split into chunks
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        chunks = splitter.split_documents(documents)
        logger.info("Split %d documents into %d chunks.", len(documents), len(chunks))

        # Build FAISS index
        embeddings = _get_embeddings()
        _vector_store = FAISS.from_documents(chunks, embeddings)

        # Save to disk
        vector_store_path = str(VECTOR_STORE_DIR)
        _vector_store.save_local(vector_store_path)
        logger.info("Vector store saved to %s", vector_store_path)

    except Exception as e:
        logger.error("Failed to build vector store: %s", e)
        _vector_store = None


def load_vector_store():
    """Load FAISS vector store from disk if it exists."""
    global _vector_store
    try:
        from langchain_community.vectorstores import FAISS
        from config import VECTOR_STORE_DIR, LEARNING_DATA_DIR

        index_file = VECTOR_STORE_DIR / "index.faiss"
        if index_file.exists():
            embeddings = _get_embeddings()
            _vector_store = FAISS.load_local(
                str(VECTOR_STORE_DIR),
                embeddings,
                allow_dangerous_deserialization=True,
            )
            logger.info("Vector store loaded from disk.")
        else:
            # Build if no saved index
            build_vector_store()
    except Exception as e:
        logger.warning("Could not load vector store: %s. Will try to build.", e)
        build_vector_store()


def retrieve_relevant_context(query: str, k: int = 4) -> str:
    """
    Search the vector store for context relevant to the query.
    Returns a formatted string of relevant chunks.
    """
    global _vector_store
    if _vector_store is None:
        return ""
    try:
        docs = _vector_store.similarity_search(query, k=k)
        if not docs:
            return ""
        parts = []
        for doc in docs:
            parts.append(doc.page_content.strip())
        return "\n\n".join(parts)
    except Exception as e:
        logger.warning("Vector search failed: %s", e)
        return ""
