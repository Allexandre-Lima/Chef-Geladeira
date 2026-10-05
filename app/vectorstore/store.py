"""Base de conhecimento culinária em ChromaDB (RAG)."""
from __future__ import annotations

import logging
import os
from typing import List

import chromadb

from app.agent.llm import embed

logger = logging.getLogger(__name__)


class KnowledgeBase:
    def __init__(self, persist_dir: str, knowledge_dir: str) -> None:
        self.knowledge_dir = knowledge_dir
        self._client = chromadb.PersistentClient(path=persist_dir)
        # embedding_function=None: os vetores vêm do Gemini, calculados por nós.
        self._col = self._client.get_or_create_collection(
            "culinary_knowledge", metadata={"hnsw:space": "cosine"}, embedding_function=None
        )

    def _load_chunks(self) -> List[str]:
        chunks: List[str] = []
        if not os.path.isdir(self.knowledge_dir):
            return chunks
        for name in sorted(os.listdir(self.knowledge_dir)):
            if name.endswith(".md"):
                with open(os.path.join(self.knowledge_dir, name), encoding="utf-8") as fh:
                    chunks += [p.strip() for p in fh.read().split("\n\n") if len(p.strip()) > 40]
        return chunks

    def ingest_if_empty(self) -> None:
        if self._col.count() > 0:
            return
        chunks = self._load_chunks()
        if not chunks:
            return
        self._col.add(
            ids=[f"chunk-{i}" for i in range(len(chunks))],
            documents=chunks,
            embeddings=embed(chunks),
        )
        logger.info("knowledge ingested", extra={"extra_data": {"chunks": len(chunks)}})

    def search(self, query: str, k: int = 3) -> List[str]:
        self.ingest_if_empty()  # tolera falha de ingestão no startup
        if self._col.count() == 0:
            return []
        res = self._col.query(query_embeddings=embed([query]), n_results=k)
        return res["documents"][0]
