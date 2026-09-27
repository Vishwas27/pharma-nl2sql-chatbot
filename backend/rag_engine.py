"""
Multi-Domain RAG (Retrieval-Augmented Generation) Knowledge Engine.
Segregates documentation into distinct knowledge domains (Metrics, Products, Accounts/Data Sources, Glossary),
chunks content with semantic metadata, and retrieves relevant business context dynamically.
Keeps RBAC Security completely isolated as a hard architectural constraint.
"""

import os
import re
import math
from pathlib import Path
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).parent.parent
DOCS_DIR = BASE_DIR / "docs"
if not DOCS_DIR.exists():
    DOCS_DIR = BASE_DIR / "nl2sql-assignment-main" / "nl2sql-assignment-main" / "docs"

# Domain Categorization for Segregated Knowledge Bases
DOMAIN_CATEGORIES = {
    "metrics": ["metric_definitions.md", "period_offsets.md"],
    "products": ["market_classification.md", "product_analytics.md"],
    "accounts_and_sources": ["org_hierarchy.md", "account_analytics.md", "data_source_guide.md"],
}

# Pharma Commercial Glossary for instant domain grounding
GLOSSARY_ITEMS = [
    {"term": "WAC", "domain": "metrics", "definition": "Wholesale Acquisition Cost - publisher list price for pharmaceuticals. Restricted to Executive role."},
    {"term": "R3M", "domain": "metrics", "definition": "Rolling 3 Months - calculated using mo_offset IN (0, 1, 2)."},
    {"term": "R6M", "domain": "metrics", "definition": "Rolling 6 Months - mo_offset IN (0, 1, 2, 3, 4, 5). Prior 3M is mo_offset IN (3, 4, 5)."},
    {"term": "Distributor Data", "domain": "accounts_and_sources", "definition": "NovaPharma paid shipments (demand). Used for all brand volume and revenue calculations with brand_flag = 1."},
    {"term": "Hub Dispense", "domain": "accounts_and_sources", "definition": "Patient Assistance Program (PAP) free drug dispenses. wac = 0. Only include when user asks for free drug or PAP."},
    {"term": "Market Data", "domain": "accounts_and_sources", "definition": "Third-party competitor volume. Used for Market Share calculation denominator and market size."},
    {"term": "340B", "domain": "accounts_and_sources", "definition": "Federal drug pricing program for safety-net healthcare organizations (is_340b = 1)."},
    {"term": "IDN / Grandparent", "domain": "accounts_and_sources", "definition": "Integrated Delivery Network. Top-level health system hierarchy (grandparent_org_name)."},
    {"term": "Market Share", "domain": "metrics", "definition": "NovaPharma Branded Equivalents (distributor) / Total Market Equivalents (market_data) for the same therapeutic subcategory."},
]


class KnowledgeChunk:
    def __init__(self, text: str, domain: str, source_file: str, title: str):
        self.text = text
        self.domain = domain
        self.source_file = source_file
        self.title = title
        self.tokens = self._tokenize(text)

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b[a-zA-Z0-9_]{2,}\b", text.lower())


class MultiDomainRAGEngine:
    def __init__(self):
        self.domain_stores: Dict[str, List[KnowledgeChunk]] = {
            "metrics": [],
            "products": [],
            "accounts_and_sources": []
        }
        self.all_chunks: List[KnowledgeChunk] = []
        self._load_and_index_documents()

    def _load_and_index_documents(self):
        """Reads and chunks all markdown files from docs directory, or seeds built-in fallback knowledge."""
        self.domain_stores = {"metrics": [], "products": [], "accounts_and_sources": []}
        self.all_chunks = []

        if DOCS_DIR.exists():
            for domain, filenames in DOMAIN_CATEGORIES.items():
                for filename in filenames:
                    file_path = DOCS_DIR / filename
                    if file_path.exists():
                        self._index_file(file_path, domain)

        # If docs folder is not bundled or produced 0 chunks, seed fallback domain knowledge chunks
        if len(self.all_chunks) == 0:
            print("[RAG] Seeding built-in domain knowledge chunks...")
            for g in GLOSSARY_ITEMS:
                chunk = KnowledgeChunk(
                    text=f"{g['term']}: {g['definition']}",
                    domain=g["domain"],
                    source_file="builtin_glossary",
                    title=g["term"]
                )
                self.domain_stores[g["domain"]].append(chunk)
                self.all_chunks.append(chunk)

        print(f"[RAG] Initialized Multi-Domain RAG with {len(self.all_chunks)} semantic chunks across {len(self.domain_stores)} domains.")

    def _index_file(self, file_path: Path, domain: str):
        """Splits markdown file into logical section chunks by headers."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Split by Markdown H1/H2/H3 headers
            sections = re.split(r"\n(?=#{1,3}\s)", content)
            for section in sections:
                cleaned = section.strip()
                if len(cleaned) < 25:
                    continue

                # Extract title header if present
                title_match = re.match(r"^#{1,3}\s*(.+)", cleaned)
                title = title_match.group(1) if title_match else file_path.stem.replace("_", " ").title()

                chunk = KnowledgeChunk(
                    text=cleaned,
                    domain=domain,
                    source_file=file_path.name,
                    title=title
                )
                self.domain_stores[domain].append(chunk)
                self.all_chunks.append(chunk)
        except Exception as e:
            print(f"[RAG] Error indexing {file_path.name}: {e}")

    def route_query_domains(self, query: str) -> List[str]:
        """Detects relevant domains based on query keywords."""
        q = query.lower()
        matched_domains = set()

        # Metrics triggers
        if any(w in q for w in ["share", "trend", "revenue", "wac", "offset", "rolling", "r3m", "r6m", "month", "quarter", "growth", "volume", "equivalent", "pack"]):
            matched_domains.add("metrics")

        # Products triggers
        if any(w in q for w in ["zenovax", "carbotrel", "gemtara", "paxelium", "oncosetron", "cyclonova", "luprex", "docetaxel", "carboplatin", "gemcitabine", "pemetrexed", "competitor", "brand", "generic", "drug", "oncology", "urology"]):
            matched_domains.add("products")

        # Accounts & Sources triggers
        if any(w in q for w in ["account", "hospital", "clinic", "idn", "grandparent", "parent", "340b", "distributor", "hub", "pap", "free drug", "gpo", "facility"]):
            matched_domains.add("accounts_and_sources")

        return list(matched_domains) if matched_domains else list(self.domain_stores.keys())

    def retrieve_relevant_context(self, query: str, top_k: int = 4, target_domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Performs domain-routed semantic relevance scoring to retrieve top knowledge chunks.
        """
        query_tokens = re.findall(r"\b[a-zA-Z0-9_]{2,}\b", query.lower())
        if not query_tokens:
            return []

        active_domains = [target_domain] if target_domain else self.route_query_domains(query)
        chunks_to_search = []
        for d in active_domains:
            chunks_to_search.extend(self.domain_stores.get(d, []))

        if not chunks_to_search:
            chunks_to_search = self.all_chunks

        scored_chunks = []
        for chunk in chunks_to_search:
            score = self._compute_similarity(query_tokens, chunk)
            if score > 0:
                scored_chunks.append((score, chunk))

        # Sort by relevance score descending
        scored_chunks.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, chunk in scored_chunks[:top_k]:
            results.append({
                "domain": chunk.domain,
                "source_file": chunk.source_file,
                "title": chunk.title,
                "text": chunk.text,
                "score": round(score, 3)
            })

        return results

    def _compute_similarity(self, query_tokens: List[str], chunk: KnowledgeChunk) -> float:
        """Computes TF-IDF based term overlap with title weighting."""
        chunk_token_set = set(chunk.tokens)
        title_token_set = set(re.findall(r"\b[a-zA-Z0-9_]{2,}\b", chunk.title.lower()))

        score = 0.0
        for token in query_tokens:
            if token in title_token_set:
                score += 3.5  # High boost for title match
            elif token in chunk_token_set:
                score += 1.0  # Content match

        # Normalize by chunk length to avoid bias towards large chunks
        if len(chunk.tokens) > 0:
            score = score / math.sqrt(len(chunk.tokens))

        return score

    def format_context_for_prompt(self, query: str) -> str:
        """Formats retrieved chunks into clean markdown instructions for LLM prompt."""
        retrieved = self.retrieve_relevant_context(query, top_k=4)
        if not retrieved:
            return ""

        formatted_parts = ["### RELEVANT BUSINESS & DOMAIN KNOWLEDGE (RETRIEVED VIA MULTI-DOMAIN RAG):"]
        for idx, item in enumerate(retrieved, 1):
            formatted_parts.append(
                f"\n--- [Domain: {item['domain'].upper()} | Source: {item['source_file']}] ---\n"
                f"**{item['title']}**\n{item['text']}\n"
            )

        return "\n".join(formatted_parts)

    def get_indexed_summary(self) -> Dict[str, Any]:
        """Returns statistics of all indexed knowledge domains and files."""
        summary = {}
        for domain, chunks in self.domain_stores.items():
            files = list(set(c.source_file for c in chunks))
            summary[domain] = {
                "chunk_count": len(chunks),
                "source_files": files
            }
        return {
            "total_chunks": len(self.all_chunks),
            "domains": summary,
            "glossary_count": len(GLOSSARY_ITEMS)
        }


# Global singleton RAG Engine
rag_engine = MultiDomainRAGEngine()

