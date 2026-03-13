"""Stage 3: Rank — PageRank symbol importance scoring.

Runs PageRank on the cross-reference graph. Symbols referenced more
frequently from more files score higher. A reference from an important
symbol matters more than one from an obscure one.

No external dependencies — implements PageRank from scratch using
the power iteration method.
"""

from __future__ import annotations

from collections import defaultdict

from modules.backend.services.code_map.types import ReferenceGraph


def rank_symbols(
    graph: ReferenceGraph,
    damping: float = 0.85,
    max_iterations: int = 100,
    tolerance: float = 1e-6,
) -> dict[str, float]:
    """Compute PageRank scores for all nodes in the reference graph.

    Args:
        graph: The cross-reference graph from build_reference_graph().
        damping: Damping factor (probability of following an edge).
            Standard default is 0.85.
        max_iterations: Maximum number of power iterations.
        tolerance: Convergence threshold (L1 norm of score delta).

    Returns:
        Mapping of qualified name → PageRank score (0.0–1.0, normalized
        so the maximum score is 1.0).
    """
    if not graph.nodes:
        return {}

    n = len(graph.nodes)
    node_index = {name: i for i, name in enumerate(graph.nodes)}

    # Build adjacency: outgoing edges per node
    outgoing: dict[int, list[int]] = defaultdict(list)
    incoming: dict[int, list[int]] = defaultdict(list)

    for edge in graph.edges:
        src_idx = node_index.get(edge.source)
        tgt_idx = node_index.get(edge.target)
        if src_idx is not None and tgt_idx is not None and src_idx != tgt_idx:
            outgoing[src_idx].append(tgt_idx)
            incoming[tgt_idx].append(src_idx)

    # Initialize scores uniformly
    scores = [1.0 / n] * n
    teleport = (1.0 - damping) / n

    for _ in range(max_iterations):
        new_scores = [0.0] * n

        # Accumulate dangling node mass (nodes with no outgoing edges)
        dangling_sum = sum(
            scores[i] for i in range(n) if not outgoing[i]
        )
        dangling_contribution = damping * dangling_sum / n

        for i in range(n):
            rank_sum = sum(
                scores[src] / len(outgoing[src])
                for src in incoming[i]
            )
            new_scores[i] = teleport + dangling_contribution + damping * rank_sum

        # Check convergence
        delta = sum(abs(new_scores[i] - scores[i]) for i in range(n))
        scores = new_scores
        if delta < tolerance:
            break

    # Normalize to 0.0–1.0 range (max score = 1.0)
    max_score = max(scores) if scores else 1.0
    if max_score > 0:
        scores = [s / max_score for s in scores]

    return {graph.nodes[i]: scores[i] for i in range(n)}
