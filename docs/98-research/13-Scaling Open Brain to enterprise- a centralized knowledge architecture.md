# Scaling Open Brain to enterprise: a centralized knowledge architecture for a multinational bank

**The Open Brain pattern — PostgreSQL/pgvector, Supabase, MCP — is a sound architectural skeleton for personal semantic memory, but scaling it to serve 10,000 employees across four jurisdictions in a regulated bank requires replacing nearly every component below the conceptual layer.** The core insight (a shared, persistent semantic memory layer accessible by any AI copilot through MCP) is correct and valuable. The implementation, however, needs enterprise authentication, multi-tenant isolation, information barriers, regional data sovereignty, encrypted embeddings, hybrid retrieval, and a full governance stack that the personal tool deliberately omits. What follows is a concrete architecture for building this, grounded in what major banks are actually deploying today and what MCP's current enterprise maturity realistically supports.

The stakes are significant. JPMorgan's LLM Suite now reaches **250,000 employees**, Goldman Sachs runs a multi-model AI platform for all **46,500 staff**, and Morgan Stanley achieved **98% adoption** among wealth management advisors with RAG over 350,000+ documents. These institutions built proprietary platforms, not off-the-shelf deployments. This report maps a realistic path from Open Brain's elegant simplicity to that class of system.

---

## What Open Brain actually is and where it breaks

Nate B Jones's Open Brain (published March 2, 2026) consists of exactly two Supabase Edge Functions and one PostgreSQL table. A user types a thought into a private Slack channel. An `ingest-thought` Edge Function generates a 1536-dimensional embedding via OpenRouter's `text-embedding-3-small` and extracts metadata (people, topics, type) using `gpt-4o-mini`. Both are stored as a single row in a `thoughts` table with a `vector(1536)` column. A second Edge Function (`open-brain-mcp`) acts as a hosted MCP server, exposing three tools — semantic search, browse recent, and stats overview — to any MCP-compatible client (Claude Desktop, ChatGPT, Cursor, VS Code Copilot). Authentication is a single random 64-character hex key passed via `x-brain-key` HTTP header. Cost: **$0.10–0.30/month**.

The architecture is deliberately single-user. It uses Supabase's `service_role` key (bypasses all row-level security), has no user authentication, no multi-tenancy, no audit logging, no rate limiting, no encryption beyond Supabase defaults, no concept of shared-vs-private knowledge, and no admin tooling. Every enterprise concern is unaddressed by design. Jones himself states: "This is a single-user personal knowledge base, not a multi-tenant app."

For enterprise, this means the conceptual architecture (PostgreSQL + pgvector for storage, MCP for universal AI access) survives, but the implementation must be rebuilt from the security model up.

---

## The target architecture: regional silos with central orchestration

The recommended pattern is a **federated sovereign architecture** — identical knowledge stacks deployed in each jurisdiction, coordinated by a lightweight central control plane that contains no personal or financial data.

```
                    ┌─────────────────────────────────┐
                    │      Central Control Plane       │
                    │  ● Metadata catalog (what exists │
                    │    where, not the content)       │
                    │  ● Policy engine (OPA)           │
                    │  ● MCP Gateway (Kong/custom)     │
                    │  ● Query router + federation     │
                    │  ● Audit log aggregation         │
                    │  ● Identity provider (Okta/Entra)│
                    └──────┬──────┬──────┬─────────────┘
                           │      │      │
              ┌────────────┘      │      └────────────┐
              ▼                   ▼                    ▼
  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
  │  SA Data Plane   │ │  UK Data Plane   │ │ India Data Plane │
  │ AWS af-south-1   │ │ AWS eu-west-2    │ │ AWS ap-south-1   │
  │                  │ │                  │ │                  │
  │ PostgreSQL +     │ │ PostgreSQL +     │ │ PostgreSQL +     │
  │ pgvector (RDS)   │ │ pgvector (RDS)   │ │ pgvector (RDS)   │
  │                  │ │                  │ │                  │
  │ SageMaker        │ │ Bedrock          │ │ Bedrock          │
  │ embedding model  │ │ embedding model  │ │ embedding model  │
  │                  │ │                  │ │                  │
  │ Doc ingestion    │ │ Doc ingestion    │ │ Doc ingestion    │
  │ pipeline (Lambda)│ │ pipeline (Lambda)│ │ pipeline (Lambda)│
  │                  │ │                  │ │                  │
  │ Regional MCP     │ │ Regional MCP     │ │ Regional MCP     │
  │ server(s)        │ │ server(s)        │ │ server(s)        │
  │                  │ │                  │ │                  │
  │ RLS per tenant + │ │ RLS per tenant + │ │ RLS per tenant + │
  │ dept + barrier   │ │ dept + barrier   │ │ dept + barrier   │
  └──────────────────┘ └──────────────────┘ └──────────────────┘
```

This design is driven by three non-negotiable constraints. First, **India's RBI mandate requires all payment system data to stay exclusively within India** — no mirroring abroad. Second, **South Africa's National Data and Cloud Policy (May 2024) mandates that government-related data stay in SA**, and SARB guidance signals stronger localization expectations for financial data. Third, **the UK's FCA requires a documented data residency policy** with demonstrated regulatory access. A federated architecture satisfies all three by keeping data in-region and only routing metadata centrally.

**AWS is the only viable primary cloud** for this deployment. It has regions in all three jurisdictions: Cape Town (`af-south-1`), London (`eu-west-2`), and Mumbai (`ap-south-1`). GCP has no South Africa region at all. Azure has South Africa North but limited AI service availability there. Supabase Cloud is not available in South Africa, so the SA data plane requires either self-hosted Supabase on AWS or direct RDS PostgreSQL with pgvector.

---

## The data layer: pgvector today, hybrid graph+vector tomorrow

Open Brain uses a single `thoughts` table with a `vector(1536)` column. For enterprise, the data model expands significantly but pgvector remains a defensible starting choice — with caveats.

**pgvector scales to roughly 10–50 million vectors** before performance degrades non-linearly. For a 10,000-employee bank with ~1,500 applications, the knowledge corpus per region will likely stay within this range for the first 1–2 years if you chunk intelligently. Aurora PostgreSQL with pgvector 0.8.0 delivers **up to 9.4x faster queries** than earlier versions, and pgvectorscale achieves **471 QPS at 99% recall on 50 million vectors** — 11.4x better than Qdrant at the same recall level.

The recommended schema per regional database:

```sql
CREATE TABLE knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    embedding vector(1536),
    content TEXT,
    content_hash TEXT,
    source_document_id UUID REFERENCES documents(id),
    tenant_id UUID NOT NULL,
    business_unit TEXT NOT NULL,  -- 'investment_banking','retail','wealth_mgmt'
    department TEXT,
    classification TEXT DEFAULT 'internal',  -- public/internal/confidential/restricted/mnpi
    barrier_group TEXT,  -- information barrier partition
    jurisdiction TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ
);

ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;

-- Tenant isolation
CREATE POLICY tenant_iso ON knowledge_chunks
    USING (tenant_id = current_setting('app.tenant_id')::uuid);

-- Information barrier enforcement
CREATE POLICY barrier_policy ON knowledge_chunks AS RESTRICTIVE
    USING (
        barrier_group = ANY(string_to_array(
            current_setting('app.allowed_barriers'), ','))
        OR classification = 'public'
    );

-- Department access
CREATE POLICY dept_policy ON knowledge_chunks AS RESTRICTIVE
    USING (
        department = ANY(string_to_array(
            current_setting('app.departments'), ','))
        OR current_setting('app.role') = 'admin'
    );

CREATE INDEX ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON knowledge_chunks (tenant_id, business_unit, barrier_group);
```

**When to graduate beyond pgvector**: If any single regional corpus exceeds 50 million vectors, or if you need sub-10ms p50 latency at scale, move to **Milvus** (open-source, Kubernetes-native, supports billions of vectors with GPU acceleration, used by PayPal and Salesforce) or **Pinecone** (fully managed, billions of vectors, but vendor lock-in with no self-hosted option). The migration path is straightforward: the retrieval API layer abstracts the vector store, so swapping backends doesn't affect the MCP servers or AI clients.

**The hybrid graph+vector play is where differentiated value lives.** Microsoft's GraphRAG, Amazon Bedrock GraphRAG (GA March 2025), and Neo4j's native vector search all demonstrate that combining structured knowledge graphs with vector embeddings yields measurably better results for complex financial queries. A query like "How did FX rate changes impact our EMEA client portfolio performance across Q3 and Q4" requires graph traversal across entities (clients, products, markets, time periods) that pure vector similarity cannot reliably handle. **Neo4j is the leading graph database in financial services** — UBS uses it for data lineage, a Latin American Global 50 Bank manages 1 trillion data relationships on it, and the FIBO (Financial Industry Business Ontology) ontology provides a W3C-standard knowledge model for financial entity relationships.

The recommended evolution path: start with pgvector for semantic search (Phase 1), add BM25 keyword search via PostgreSQL full-text search for hybrid retrieval (Phase 2), then introduce Neo4j for entity relationships and regulatory knowledge graphs (Phase 3). This matches how banks like Morgan Stanley and Deutsche Bank actually scaled — starting with document RAG and layering structured knowledge on top.

---

## MCP at enterprise scale: promising protocol, immature security

MCP has achieved genuine critical mass. The protocol has **97 million+ monthly SDK downloads**, is governed by the Linux Foundation's Agentic AI Foundation (with Anthropic, OpenAI, AWS, Google, Microsoft, and Bloomberg as platinum members), and the November 2025 spec update added asynchronous Tasks, modernized M2M authorization, and lifecycle governance. It is the emerging standard for connecting AI agents to tools and data.

However, deploying MCP in a regulated bank requires confronting significant security gaps head-on.

**What MCP provides natively**: OAuth 2.1 with mandatory PKCE for HTTP transports, Resource Indicators (RFC 8707) to prevent token mis-redemption, Protected Resource Metadata (RFC 9728), and three transport mechanisms (stdio for local tools, streamable HTTP for remote services, legacy HTTP+SSE). The spec defines tools, resources, and prompts as first-class primitives with JSON-RPC 2.0 semantics.

**What MCP does not provide and you must build**: Fine-grained RBAC/ABAC (spec only offers OAuth scopes), enterprise SSO integration, tamper-proof audit logging meeting SOX/GDPR standards, multi-tenancy, tool provenance verification, and prompt injection defenses. These are not small gaps for a bank.

**The critical attack surface** is well-documented. Invariant Labs demonstrated tool poisoning attacks that exfiltrated WhatsApp histories and private GitHub data through hidden instructions in MCP tool descriptions. The Supabase/Cursor incident (mid-2025) showed a privileged agent processing support tickets containing injection payloads, leading to a data breach. CVE-2025-6514 was a critical OS command injection in `mcp-remote` that compromised **437,000+ developer environments**. Equixly's security assessment found **command injection in 43% of tested MCP implementations**, SSRF in 30%, and arbitrary file access in 22%.

**The solution is an MCP gateway.** This is the single most important infrastructure component for enterprise MCP. Several are emerging:

- **Kong AI Gateway 3.12**: Auto-generates MCP servers from REST APIs, centralizes OAuth 2.1, provides MCP-specific observability, integrates with SIEM
- **MintMCP Gateway**: SOC 2 Type II compliant, purpose-built for regulated industries, automatic OAuth wrapping, RBAC, comprehensive audit trails
- **Traefik Hub**: Task-Based Access Control (TBAC) across tasks/tools/transactions, JWT integration, auto-generated Protected Resource Metadata

The gateway architecture for this bank:

```
AI Copilot (Claude/ChatGPT/Copilot)
    │
    ▼
MCP Gateway (Kong or custom)
    ● OAuth 2.1 + enterprise IdP (Okta/Entra ID)
    ● Per-tool authorization (OPA policy engine)
    ● Tool description scanning (injection detection)
    ● Tool hash verification (rug-pull prevention)
    ● Rate limiting + quota management
    ● Immutable audit logging (all tool calls)
    ● User context injection (tenant, dept, barriers)
    │
    ▼
Regional MCP Servers (streamable HTTP)
    ● Knowledge search tools
    ● Document retrieval tools
    ● Read-only by default
    ● Write tools behind human-in-the-loop
```

**Block (formerly Square) provides the best enterprise reference.** Thousands of employees use their open-source "Goose" MCP agent daily. All internal MCP servers are authored by Block engineers — they never deploy unvetted community servers. They use Databricks for LLM hosting, OAuth for service-level authorization, and explicitly annotate tools as read-only or destructive.

---

## Information barriers are the hardest problem in the architecture

For an investment bank or diversified financial services firm, Chinese walls between business units are a regulatory requirement, not a nice-to-have. The SEC fined a major investment bank in January 2024 for information barrier failures. The FCA expects robust governance under SM&CR. And a unified AI knowledge store that allows semantic search across business units is inherently a barrier violation — **the data flow itself violates the barrier regardless of whether a human sees the output**.

The implementation requires three reinforcing layers:

**Layer 1 — Physical namespace isolation**: Separate vector collections or database schemas per barrier group (Investment Banking MNPI, Retail, Wealth Management, Treasury). Each barrier group has independent HNSW indexes and independent access policies.

**Layer 2 — Attribute-Based Access Control**: Every query carries the user's barrier group membership (extracted from JWT claims, sourced from the enterprise IdP). The retrieval layer applies these as pre-filters before vector search. A research analyst's copilot physically cannot execute a similarity search against IB deal documents.

**Layer 3 — DLP monitoring**: A Data Loss Prevention layer monitors all data flows between AI system components, detecting and blocking any cross-barrier information movement. Microsoft Presidio (open source) or Palo Alto Networks' DLP scan both ingestion inputs and generation outputs.

**The critical anti-pattern**: deploying a shared knowledge store across business units without barrier enforcement, even internally. If an AI copilot in retail banking can semantically match against investment banking deal memos, that is a compliance violation under MiFID II, SEC regulations, and FCA expectations. Design barriers into the data model from day one.

---

## The ingestion pipeline: where security is won or lost

The document ingestion pipeline is the highest-leverage security control point. Once data enters the vector store as embeddings, remediation is expensive (re-embedding, re-indexing). Getting ingestion right means errors are caught before they become embedded.

```
Source Documents (Confluence, SharePoint, S3, internal systems)
    │
    ▼
Document Parsing (LlamaParse or Unstructured.io)
    ● Handles PDFs with tables, financial statements, contracts
    ● Extracts text, tables, images with layout awareness
    │
    ▼
DLP Scanning + Classification
    ● PII detection (Microsoft Presidio, open-source)
    ● PAN/CVV pattern blocking (PCI-DSS compliance)
    ● MNPI flagging for barrier classification
    ● Sensitivity classification: public/internal/confidential/restricted
    ● Prompt injection pattern detection in source documents
    │
    ▼
PII Redaction/Masking
    ● Replace PII with typed placeholders [PERSON_1], [ACCOUNT_NUMBER]
    ● Preserve semantic structure for meaningful embeddings
    ● Never embed: card numbers, CVVs, passwords, API keys, biometrics
    │
    ▼
Chunking
    ● Semantic chunking respecting document structure (400-800 tokens)
    ● Parent-child linking for context retrieval
    ● Metadata enrichment: source, date, author, department, classification
    │
    ▼
Regional Embedding Generation
    ● CRITICAL: Raw text must NOT cross jurisdiction borders
    ● Deploy embedding model in-region (Bedrock in UK/India, SageMaker in SA)
    ● Same model version across all regions for consistent vector spaces
    │
    ▼
Encrypted Vector Storage
    ● Application-layer encryption before storage (IronCore Labs Cloaked AI)
    ● Per-tenant encryption keys for cross-tenant isolation
    ● Store in regional PostgreSQL/pgvector with RLS policies active
```

**Embedding inversion is a real, demonstrated attack, not theoretical.** Research shows **50–70% word recovery** (F1 scores 0.5–0.7) from sentence embeddings, and transfer attacks work even without knowing the original embedding model. OWASP's 2025 LLM Top 10 introduced "Vector and Embedding Weaknesses" as a new leading vulnerability. **Embeddings must be treated as sensitive as the source data.** IronCore Labs' Cloaked AI uses a Scale and Perturb algorithm that encrypts embedding values while preserving approximate distance relationships for search — inversion of encrypted embeddings produces nonsense. Deploy this or equivalent application-layer encryption for all embedding storage.

---

## Retrieval architecture: hybrid search is the production standard

Pure vector similarity search is insufficient for enterprise financial knowledge. The production standard at leading banks is **hybrid retrieval: BM25 keyword search + dense vector search + cross-encoder reranking**.

```python
# Simplified retrieval pipeline
async def retrieve(query: str, user_context: UserContext) -> list[Chunk]:
    # 1. Generate query embedding (in-region)
    query_embedding = await embed(query, region=user_context.jurisdiction)
    
    # 2. Parallel hybrid search
    semantic_results = await pgvector_search(
        embedding=query_embedding,
        tenant_id=user_context.tenant_id,
        barriers=user_context.barrier_groups,
        departments=user_context.departments,
        top_k=20
    )
    keyword_results = await pg_fulltext_search(
        query=query,
        tenant_id=user_context.tenant_id,
        barriers=user_context.barrier_groups,
        top_k=20
    )
    
    # 3. Reciprocal Rank Fusion
    merged = reciprocal_rank_fusion(semantic_results, keyword_results, k=60)
    
    # 4. Cross-encoder reranking (Cohere Rerank or similar)
    reranked = await rerank(query, merged[:30])
    
    # 5. Post-retrieval authorization check
    authorized = await check_permissions(reranked, user_context)
    
    # 6. DLP output scan
    safe_results = await dlp_scan_output(authorized[:10])
    
    return safe_results
```

Cohere's Rerank 3.5 delivers a **23.4% improvement** over hybrid search alone. The combination of BM25 + dense + reranking reduces irrelevant passages from 30–40% to under 10%. For financial documents — where precision of terminology matters (e.g., "Basel III" must match exactly, not just semantically similar concepts) — this hybrid approach is essential.

**For cross-region federated queries**, the pattern is fan-out with Reciprocal Rank Fusion:

1. Query router determines scope (single-region or multi-region) based on user context and query classification
2. Fan-out queries to relevant regional vector stores in parallel
3. Each region returns top-k results (filtered by RLS)
4. Central orchestrator merges via RRF
5. Latency budget: intra-region **10–50ms**, cross-region adds **100–250ms** per additional region

Most queries will be single-region. Only cross-region discovery queries (e.g., "What's our global policy on X?") need federation, and those tolerate higher latency.

---

## Regulatory compliance across four jurisdictions

The regulatory landscape creates concrete technical requirements:

**India (most restrictive)**: RBI mandates all payment system data stay exclusively within India. No mirroring abroad. SEBI requires critical financial data in India. The DPDP Act 2023 allows cross-border transfers by default (negative-list approach) but sector regulators override. **Design: all Indian financial/personal data in `ap-south-1`, embedding generation in-region, no raw text leaving India.**

**South Africa**: POPIA requires adequate protection for cross-border transfers but doesn't mandate localization for private sector. However, the May 2024 National Data and Cloud Policy signals stronger sovereignty requirements, and SARB expects risk-managed offshoring. **Design: SA personal and financial data in `af-south-1`, proactively treating it as localization-required.** Note that Bedrock is limited in Cape Town — use SageMaker with a self-hosted embedding model (sentence-transformers or similar).

**United Kingdom**: UK GDPR requires lawful basis for processing, DPIA for high-risk AI, and right-to-erasure compliance. FCA/PRA require documented data residency policy, cloud outsourcing governance (PRA SS2/21), and SM&CR accountability. EU adequacy valid until December 2031. **Design: UK data in `eu-west-2`, full Bedrock availability, standard compliance controls.**

**Cross-border transfers**: The safest architecture transfers only anonymized/aggregated metadata across borders. For necessary transfers, use POPIA binding agreements (SA↔UK/India), UK IDTA or SCCs (UK↔SA/India), and DPDP mechanisms once notified (India↔UK/SA). **The critical often-overlooked requirement: embedding generation must happen in-region.** Sending raw document text to a remote embedding API constitutes cross-border data transfer.

**PCI-DSS**: If any knowledge source contains payment card data, the entire RAG pipeline falls in PCI scope. The correct design is **hard-blocking PAN patterns in the DLP ingestion scanner**. Never embed payment card data. This keeps the knowledge system out of PCI scope entirely.

---

## Recommended technology stack

| Layer | Component | Technology | Rationale |
|-------|-----------|------------|-----------|
| **Vector Store** | Primary | Aurora PostgreSQL + pgvector 0.8.0 | ACID compliance, RLS, mature ops, sufficient for <50M vectors/region |
| **Vector Store** | Scale-out path | Milvus (self-hosted on EKS) | When any region exceeds 50M vectors; K8s-native, GPU acceleration |
| **Knowledge Graph** | Phase 2+ | Neo4j AuraDB or self-hosted | Entity relationships, regulatory ontologies, FIBO alignment |
| **Embedding** | UK/India | Amazon Bedrock (Titan Embeddings or Cohere Embed) | Managed, in-region, no raw text leaves |
| **Embedding** | SA | SageMaker + BGE-large-en or E5-large | Bedrock limited in af-south-1; self-host open-source model |
| **Doc Parsing** | All regions | LlamaParse (LlamaIndex) | Best handling of financial PDFs, tables, contracts |
| **DLP/PII** | Ingestion | Microsoft Presidio (open-source) | On-premise, customizable, no data sent externally |
| **Reranking** | Retrieval | Cohere Rerank 3.5 or cross-encoder on SageMaker | 23.4% improvement over hybrid search alone |
| **MCP Gateway** | Central | Kong AI Gateway 3.12 or custom (FastAPI + OPA) | OAuth 2.1, tool-level authz, audit logging, SIEM integration |
| **MCP Servers** | Per-region | Custom (Python, FastMCP framework) | Streamable HTTP transport, scoped tools per business unit |
| **Identity** | Enterprise | Okta or Microsoft Entra ID | SSO, MFA, group management, OAuth 2.1 provider |
| **Policy Engine** | Authorization | Open Policy Agent (OPA) | Fine-grained ABAC, information barrier enforcement, policy-as-code |
| **Audit** | Logging | CloudWatch Logs → S3 (immutable) → SIEM | Tamper-proof, 7-year retention, regulatory compliance |
| **Orchestration** | RAG pipeline | LangGraph or custom Python | Agentic retrieval, multi-step reasoning, tool orchestration |
| **Observability** | Monitoring | OpenTelemetry → Datadog/Grafana | Distributed tracing across MCP calls, latency, error rates |
| **Infrastructure** | All regions | AWS CDK / Terraform | Infrastructure-as-code for consistent multi-region deployment |
| **Embedding Encryption** | Storage | IronCore Labs Cloaked AI or custom ALE | Embedding inversion attack prevention |

---

## Eight anti-patterns that will sink this project

**1. "God Mode" AI agents.** Giving copilots broad service-account access to the full knowledge store. In 2024, an attacker tricked a reconciliation agent into exporting 45,000 customer records because it had unrestricted read access. Every AI agent must inherit the querying user's permissions, never its own superuser access.

**2. Shared knowledge store without barrier enforcement.** The single most dangerous architectural decision. If an investment banking copilot can semantically search retail customer data, that data flow is a regulatory violation regardless of output. Build barriers into the data model at the schema level, not the application level.

**3. Treating embeddings as "safe" abstract numbers.** Embeddings can be inverted to recover 50–70% of original words. They must be encrypted with application-layer encryption and treated as sensitive as source data.

**4. Prompt-based security.** System prompts like "never reveal confidential information" are trivially bypassed by prompt injection. Security must be architectural — RLS, ABAC, encrypted embeddings, output DLP — not prompt-based.

**5. Deploying community MCP servers in production.** CVE-2025-6514 compromised 437,000+ environments through a malicious MCP package. Only internally-authored, reviewed MCP servers should run in production. Follow Block's model: all MCP servers authored by internal engineers.

**6. Skipping PII scanning before ingestion.** Once PII is embedded in vectors, remediation requires re-embedding the entire affected corpus. Scan at ingestion. Block PAN patterns. Redact before embedding. The cost of getting this wrong is enormous.

**7. Flat RBAC metadata in vector databases.** Attempting to flatten complex enterprise permission hierarchies into simple key-value metadata tags creates synchronization lag, metadata explosion, and security gaps when permissions change. Use post-retrieval authorization via a proper policy engine (OPA/SpiceDB), or the Honeybee framework's role-based partitioning approach.

**8. Starting with multi-region before single-region works.** Get the architecture right in one region (UK is recommended — best AWS AI service availability, simplest regulatory posture). Prove retrieval quality, security controls, and MCP integration. Then replicate to SA and India. Attempting simultaneous multi-region launch multiplies every problem by three.

---

## Phased implementation roadmap

**Phase 1 (Months 1–3): Single-region MVP in UK.** Deploy PostgreSQL + pgvector on Aurora in `eu-west-2`. Build the ingestion pipeline with LlamaParse + Presidio + regional embedding. Implement RLS with tenant and department isolation. Deploy 2–3 internal MCP servers (knowledge search, document retrieval, stats) behind a Kong gateway with OAuth 2.1 tied to your enterprise IdP. Target: 50–100 internal users in a single business unit, read-only, non-customer-facing knowledge (internal policies, technical documentation, operational runbooks). This validates the core pattern.

**Phase 2 (Months 3–6): Security hardening and information barriers.** Add barrier_group enforcement to RLS. Implement OPA policies for fine-grained authorization. Deploy embedding encryption (IronCore Cloaked AI). Build immutable audit logging pipeline to SIEM. Add DLP output scanning. Deploy cross-encoder reranking. Red-team the system with prompt injection, data exfiltration, and barrier bypass attempts. Expand to 500–1,000 users across multiple business units. This proves the security model.

**Phase 3 (Months 6–9): Multi-region expansion.** Deploy identical stacks to SA (`af-south-1`, self-hosted) and India (`ap-south-1`). Build the federated query router. Establish cross-border transfer agreements (POPIA binding agreements, UK IDTA). Deploy regional embedding generation (SageMaker in SA, Bedrock in India). Validate data residency compliance with legal/compliance teams.

**Phase 4 (Months 9–12): Advanced capabilities.** Introduce Neo4j for entity-relationship knowledge graphs. Implement GraphRAG for complex multi-hop queries. Build agentic RAG with LangGraph for autonomous retrieval planning. Deploy write-capable MCP tools (capture knowledge, update metadata) with human-in-the-loop approval. Expand to full 10,000-employee availability. Evaluate Milvus migration if any region approaches 50M vectors.

---

## Conclusion

The Open Brain pattern identifies the right architectural insight: a persistent, portable semantic memory layer accessible through MCP creates genuine value by eliminating the cold-start problem across AI copilots. The path from personal tool to enterprise system is not incremental improvement — it requires a ground-up rebuild of the security, isolation, and governance layers while preserving the conceptual elegance.

**Three decisions matter most.** First, federated regional data planes are non-negotiable given India's RBI mandate and South Africa's data sovereignty trajectory — centralized architectures cannot comply. Second, the MCP gateway is the critical chokepoint where authentication, authorization, audit, and injection defense converge — invest heavily here rather than distributing security across individual MCP servers. Third, information barriers must be enforced at the data model level (RLS barrier_group policies), not the application level — architectural security beats prompt-based security every time.

The technology is ready. pgvector handles the vector storage needs at current scale. MCP provides the universal protocol, despite needing gateway-mediated security hardening. Hybrid retrieval (BM25 + dense + reranking) is a proven production pattern. The hard problems are organizational: data classification discipline, barrier policy definition, cross-jurisdictional legal agreements, and the governance structures that keep the system compliant as it scales. The banks that have succeeded — Morgan Stanley's 98% adoption, JPMorgan's 250,000-user deployment — built proprietary platforms that embedded these governance structures from inception, not bolted them on afterward. Start with security architecture. The AI features follow naturally.