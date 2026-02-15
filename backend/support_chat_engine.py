"""
Support Chat Engine — Product Q&A RAG for Hunt.

This engine is separate from the ICP discovery chat. It answers product
questions using indexed internal documentation with customer-safe responses.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import KnowledgeChunk, KnowledgeDocument, SupportChatLog

logger = logging.getLogger(__name__)

KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
KIMI_API_BASE = "https://api.moonshot.ai/v1"

SUPPORT_CHAT_MODEL = os.getenv("SUPPORT_CHAT_MODEL", "kimi-k2-turbo-preview")
SUPPORT_EMBEDDING_MODEL = os.getenv("SUPPORT_EMBEDDING_MODEL", "text-embedding-v4")

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent

SUPPORT_DOCS_DIR = os.getenv("SUPPORT_DOCS_DIR", "").strip()
SUPPORT_README_PATH = os.getenv("SUPPORT_README_PATH", "").strip()
SUPPORT_INCLUDE_README = os.getenv("SUPPORT_INCLUDE_README", "").strip().lower() in {"1", "true", "yes", "on"}

MAX_QUESTION_CHARS = 1800
EMBED_DIM = 256
TECHNICAL_QUESTION_KEYWORDS = (
    "api",
    "sdk",
    "endpoint",
    "webhook",
    "backend",
    "frontend",
    "database",
    "schema",
    "docker",
    "container",
    "deploy",
    "deployment",
    "infrastructure",
    "model",
    "llm",
    "embedding",
    "moonshot",
    "openai",
    "kimi",
    "supabase",
    "postgres",
    "setup",
    "integration",
    "technical",
    "architecture",
)
RESTRICTED_CUSTOMER_PATTERNS = (
    r"\bkimi\b",
    r"\bmoonshot\b",
    r"\bopenai\b",
    r"\bgpt\b",
    r"\bdocker\b",
    r"\bcontainer(s)?\b",
    r"\btoken(s)?\b",
    r"\bapi key(s)?\b",
    r"\bembedding(s)?\b",
    r"\bmodel(s)?\b",
    r"\bprompt(s)?\b",
    r"\buvicorn\b",
    r"\bfastapi\b",
    r"\bsupabase\b",
    r"\bpostgres(ql)?\b",
    r"\breadme\b",
    r"\bsource(s)?\b",
    r"https?://",
    r"\$\s?\d",
    r"\busd\b",
    r"\bcents?\b",
)


@dataclass
class RetrievedChunk:
    chunk_id: str
    title: str
    source_path: str
    content: str
    score: float


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sanitize_question(text: str) -> str:
    clean = (text or "").strip()[:MAX_QUESTION_CHARS]
    clean = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", clean)
    clean = re.sub(r"<[^>]*>", "", clean)
    return clean


def _tokenize(text: str) -> list[str]:
    # Unicode-safe tokenization so non-English queries (e.g. Serbian) still retrieve context.
    return re.findall(r"[^\W_]{2,}", text.lower(), flags=re.UNICODE)


def _hash_embedding(text: str, dim: int = EMBED_DIM) -> list[float]:
    vec = [0.0] * dim
    tokens = _tokenize(text)
    if not tokens:
        return vec
    for tok in tokens:
        idx = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16) % dim
        vec[idx] += 1.0
    norm = sum(v * v for v in vec) ** 0.5
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _keyword_overlap(query: str, chunk: str) -> float:
    q = set(_tokenize(query))
    c = set(_tokenize(chunk))
    if not q or not c:
        return 0.0
    return len(q & c) / max(len(q), 1)


def _extract_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()[:180]
    return fallback


def _chunk_markdown(text: str, target_chars: int = 1000, overlap_chars: int = 180) -> list[str]:
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    chunks: list[str] = []
    current = ""

    for block in blocks:
        candidate = (current + "\n\n" + block).strip() if current else block
        if len(candidate) <= target_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            tail = current[-overlap_chars:] if overlap_chars > 0 else ""
            current = (tail + "\n\n" + block).strip()
            if len(current) > target_chars * 1.5:
                for i in range(0, len(current), target_chars):
                    chunks.append(current[i : i + target_chars])
                current = ""
        else:
            for i in range(0, len(block), target_chars):
                chunks.append(block[i : i + target_chars])
            current = ""

    if current:
        chunks.append(current)
    return [c for c in chunks if c.strip()]


def _candidate_readme_paths() -> list[Path]:
    paths: list[Path] = []

    # Default behavior: do not index README for customer support answers.
    # This avoids leaking technical implementation details and dev setup docs.
    if not SUPPORT_INCLUDE_README:
        return paths

    # Explicit path wins when README indexing is enabled.
    if SUPPORT_README_PATH:
        paths.append(Path(SUPPORT_README_PATH))
        return paths

    # Optional legacy inclusion path.
    paths.append(BASE_DIR / "README.md")
    paths.append(REPO_ROOT / "README.md")
    return paths


def _candidate_docs_dirs() -> list[Path]:
    dirs: list[Path] = []
    if SUPPORT_DOCS_DIR:
        dirs.append(Path(SUPPORT_DOCS_DIR))
    # backend-contained docs
    dirs.append(BASE_DIR / "docs" / "product-knowledge")
    # repo-level docs
    dirs.append(REPO_ROOT / "docs" / "product-knowledge")
    return dirs


def _default_sources() -> list[Path]:
    sources: list[Path] = []

    for rp in _candidate_readme_paths():
        if rp.exists() and rp.is_file():
            sources.append(rp)
            break

    for dd in _candidate_docs_dirs():
        if dd.exists() and dd.is_dir():
            sources.extend(sorted(dd.glob("*.md")))
            break

    return sources


class SupportChatEngine:
    """RAG engine for product support Q&A."""

    def __init__(self):
        self.kimi_client: Optional[AsyncOpenAI] = None
        self._embedding_api_enabled = True
        if KIMI_API_KEY:
            self.kimi_client = AsyncOpenAI(api_key=KIMI_API_KEY, base_url=KIMI_API_BASE)
        else:
            logger.warning("Support chat running without KIMI_API_KEY. Falling back to extractive mode.")

    async def _embed_text(self, text: str) -> list[float]:
        if self.kimi_client and self._embedding_api_enabled:
            try:
                resp = await self.kimi_client.embeddings.create(
                    model=SUPPORT_EMBEDDING_MODEL,
                    input=text,
                )
                emb = resp.data[0].embedding  # type: ignore[index]
                if isinstance(emb, list) and emb:
                    return [float(x) for x in emb]
            except Exception as exc:
                self._embedding_api_enabled = False
                logger.warning("Moonshot embeddings unavailable, falling back to local embeddings: %s", exc)
        return _hash_embedding(text)

    async def index_knowledge_base(
        self,
        db: AsyncSession,
        source_paths: Optional[list[Path]] = None,
        clear_missing: bool = True,
    ) -> dict:
        paths = source_paths or _default_sources()
        if not paths:
            logger.warning(
                "Support index: no source docs found. Checked README paths=%s docs_dirs=%s",
                [str(p) for p in _candidate_readme_paths()],
                [str(d) for d in _candidate_docs_dirs()],
            )
        indexed_docs = 0
        indexed_chunks = 0
        unchanged_docs = 0
        archived_docs = 0

        existing = {
            d.slug: d
            for d in (await db.execute(select(KnowledgeDocument))).scalars().all()
        }
        seen_slugs: set[str] = set()

        for path in paths:
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8", errors="ignore").strip()
            if not content:
                continue

            rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            slug = rel.lower().replace("/", "__").replace(".", "_")
            title = _extract_title(content, fallback=path.stem.replace("-", " ").title())
            content_hash = _sha256(content)
            seen_slugs.add(slug)

            doc = existing.get(slug)
            needs_reindex = True

            if not doc:
                doc = KnowledgeDocument(
                    id=str(uuid.uuid4()),
                    slug=slug,
                    title=title,
                    source_path=rel,
                    source_type="markdown",
                    content_hash=content_hash,
                    status="active",
                    metadata_json={"path": rel},
                )
                db.add(doc)
                await db.flush()
            else:
                if doc.content_hash == content_hash and doc.status == "active":
                    needs_reindex = False
                doc.title = title
                doc.source_path = rel
                doc.source_type = "markdown"
                doc.content_hash = content_hash
                doc.status = "active"
                doc.metadata_json = {"path": rel}

            if not needs_reindex:
                unchanged_docs += 1
                continue

            await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))

            chunks = _chunk_markdown(content)
            for idx, chunk in enumerate(chunks):
                embedding = await self._embed_text(chunk)
                kc = KnowledgeChunk(
                    id=str(uuid.uuid4()),
                    document_id=doc.id,
                    chunk_index=idx,
                    content=chunk,
                    token_estimate=max(1, len(chunk) // 4),
                    embedding=embedding,
                    metadata_json={"source_path": rel},
                )
                db.add(kc)
                indexed_chunks += 1

            indexed_docs += 1

        if clear_missing:
            for slug, doc in existing.items():
                if slug not in seen_slugs and doc.status != "archived":
                    doc.status = "archived"
                    archived_docs += 1

        await db.commit()
        return {
            "sources_seen": len(paths),
            "indexed_docs": indexed_docs,
            "indexed_chunks": indexed_chunks,
            "unchanged_docs": unchanged_docs,
            "archived_docs": archived_docs,
        }

    async def _retrieve(
        self, db: AsyncSession, question: str, top_k: int = 6
    ) -> list[RetrievedChunk]:
        q_embedding = await self._embed_text(question)
        rows = (
            await db.execute(
                select(KnowledgeChunk, KnowledgeDocument)
                .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
                .where(KnowledgeDocument.status == "active")
            )
        ).all()

        scored: list[RetrievedChunk] = []
        for chunk, doc in rows:
            emb = chunk.embedding if isinstance(chunk.embedding, list) else []
            sem = _cosine(q_embedding, emb)
            lex = _keyword_overlap(question, chunk.content)
            score = 0.82 * sem + 0.18 * lex
            if score < 0.08:
                continue
            scored.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    title=doc.title,
                    source_path=doc.source_path,
                    content=chunk.content,
                    score=score,
                )
            )

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:max(1, top_k)]

    async def _generate_answer_with_llm(
        self, question: str, retrieved: list[RetrievedChunk]
    ) -> Optional[dict]:
        if not self.kimi_client:
            return None

        context_lines = []
        for i, ch in enumerate(retrieved, start=1):
            context_lines.append(
                f"[S{i}] title={ch.title} source={ch.source_path}\n{ch.content[:1400]}"
            )
        context_blob = "\n\n".join(context_lines)

        system_prompt = (
            "You are Hunt's product specialist and sales engineer. "
            "Be pro-Hunt, confident, and commercially helpful. "
            "Always answer in the same language as the user's question. "
            "Lead with business outcomes and why Hunt is valuable. "
            "Never mention internal sources, documents, or citations. "
            "Unless the user explicitly asks a technical implementation/setup question, "
            "do not mention model vendors, model names, embeddings, tokens, API keys, Docker, "
            "infrastructure, code files, or developer tooling. "
            "Never answer with 'I can't say if it's worth buying'. "
            "If exact quantitative proof is unavailable, give a qualitative recommendation "
            "based on known product capabilities and suggest a concrete next step (trial/pilot/demo). "
            "Do not invent features, limits, APIs, prices, or workflows beyond the provided context."
        )
        user_prompt = (
            "Return strict JSON:\n"
            "{"
            "\"answer\":\"string\","
            "\"confidence\":0.0,"
            "\"needs_human\":false"
            "}\n\n"
            f"Question:\n{question}\n\nSources:\n{context_blob}"
        )

        try:
            resp = await self.kimi_client.chat.completions.create(
                model=SUPPORT_CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=700,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(raw)
            if not isinstance(data, dict) or not data.get("answer"):
                return None
            data["confidence"] = float(data.get("confidence", 0.65))
            data["needs_human"] = bool(data.get("needs_human", False))
            return data
        except Exception as exc:
            logger.warning("Support LLM answer failed: %s", exc)
            return None

    @staticmethod
    def _is_technical_question(question: str) -> bool:
        q = (question or "").lower()
        return any(k in q for k in TECHNICAL_QUESTION_KEYWORDS)

    @staticmethod
    def _sanitize_customer_answer(answer: str, question: str) -> str:
        text = (answer or "").strip()
        if not text:
            return text

        if SupportChatEngine._is_technical_question(question):
            return text

        sentences = re.split(r"(?<=[.!?])\s+", text)
        filtered: list[str] = []
        for sentence in sentences:
            s = sentence.strip()
            if not s:
                continue
            if any(re.search(pat, s, flags=re.IGNORECASE) for pat in RESTRICTED_CUSTOMER_PATTERNS):
                continue
            filtered.append(s)

        cleaned = " ".join(filtered).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if cleaned:
            return cleaned

        return (
            "Hunt is built to deliver qualified B2B pipeline faster by combining discovery, "
            "AI qualification, and lead workflows in one place. "
            "Best next step: run a short trial with your real ICP and compare speed-to-qualified-lead."
        )

    @staticmethod
    def _extractive_fallback(question: str, retrieved: list[RetrievedChunk]) -> dict:
        if not retrieved:
            return {
                "answer": (
                    "Hunt is built to replace slow manual prospecting with a faster, AI-driven pipeline: "
                    "discover target accounts, qualify them with scoring, and turn results into sales-ready leads. "
                    "If your team spends too much time finding and vetting accounts manually, Hunt is a strong fit. "
                    "Best next step: run a short pilot with your real ICP and compare speed-to-qualified-lead."
                ),
                "confidence": 0.45,
                "needs_human": False,
            }

        lead = retrieved[0]
        answer = (
            "Hunt is designed to improve pipeline quality and execution speed by combining discovery, AI qualification, "
            "and lead operations in one flow. Based on your question, this is the most relevant capability:\n\n"
            f"{lead.content[:420].strip()}\n\n"
            "If you want, I can map this directly to your team's workflow and expected impact."
        )
        safe_answer = SupportChatEngine._sanitize_customer_answer(answer, question)
        return {"answer": safe_answer, "confidence": min(0.72, max(0.5, lead.score)), "needs_human": False}

    async def answer_question(
        self,
        db: AsyncSession,
        question: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        max_sources: int = 6,
    ) -> dict:
        clean_q = _sanitize_question(question)
        if not clean_q:
            return {
                "session_id": session_id or str(uuid.uuid4()),
                "answer": "Ask a product question and I will answer from Hunt documentation.",
                "confidence": 0.0,
                "needs_human": False,
                "citations": [],
            }

        sid = session_id or str(uuid.uuid4())
        retrieved = await self._retrieve(db, clean_q, top_k=max_sources)
        llm_answer = await self._generate_answer_with_llm(clean_q, retrieved)
        answer_data = llm_answer or self._extractive_fallback(clean_q, retrieved)

        citations = [
            {
                "id": f"S{i}",
                "title": chunk.title,
                "source_path": chunk.source_path,
                "snippet": chunk.content[:220].replace("\n", " ").strip(),
                "score": round(chunk.score, 4),
            }
            for i, chunk in enumerate(retrieved[:4], start=1)
        ]

        answer = str(answer_data.get("answer", "")).strip()
        answer = self._sanitize_customer_answer(answer, clean_q)
        confidence = float(answer_data.get("confidence", 0.0))
        needs_human = bool(answer_data.get("needs_human", False))

        log_row = SupportChatLog(
            id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=sid,
            question=clean_q,
            answer=answer,
            citations=citations,
            retrieved_chunks=[c.chunk_id for c in retrieved],
            confidence=confidence,
            needs_human=needs_human,
        )
        db.add(log_row)
        await db.commit()

        return {
            "session_id": sid,
            "answer": answer,
            "confidence": confidence,
            "needs_human": needs_human,
            "citations": citations,
        }

    async def health(self, db: AsyncSession) -> dict:
        docs = (await db.execute(select(KnowledgeDocument))).scalars().all()
        chunks = (await db.execute(select(KnowledgeChunk))).scalars().all()
        active_docs = [d for d in docs if d.status == "active"]
        return {
            "status": "ok",
            "llm_available": self.kimi_client is not None,
            "embedding_api_enabled": self._embedding_api_enabled,
            "documents_total": len(docs),
            "documents_active": len(active_docs),
            "chunks_total": len(chunks),
        }
