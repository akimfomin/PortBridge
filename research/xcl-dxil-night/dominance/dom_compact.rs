//! Immediate dominators by the simple Lengauer–Tarjan algorithm.

const NONE: usize = usize::MAX;

struct DfsNode {
    block: usize,
    parent: usize,
    ancestor: usize,
    semi: usize,
    label: usize,
    bucket_head: usize,
    // While queued, the next member; after evaluation, the dominator.
    bucket_link: usize,
}

struct Edge {
    from: usize,
    next: usize,
}

/// A dominator for each reachable block. The entry dominates itself.
pub(super) fn immediate_dominators<I>(
    block_count: usize,
    entry: usize,
    reachable_count: usize,
    mut successors: impl FnMut(usize) -> I,
) -> Vec<Option<usize>>
where
    I: IntoIterator<Item = usize>,
    I::IntoIter: DoubleEndedIterator,
{
    let mut seen = vec![false; block_count];
    let mut nodes = Vec::with_capacity(reachable_count);
    let mut incoming = vec![NONE; block_count];
    let mut edges = Vec::with_capacity(reachable_count);
    let mut pending = vec![(entry, 0)];
    while let Some((block, parent)) = pending.pop() {
        if std::mem::replace(&mut seen[block], true) {
            continue;
        }
        let number = nodes.len();
        nodes.push(DfsNode {
            block, parent, ancestor: NONE, semi: number, label: number,
            bucket_head: NONE, bucket_link: 0,
        });
        for target in successors(block).into_iter().rev() {
            edges.push(Edge { from: number, next: incoming[target] });
            incoming[target] = edges.len() - 1;
            pending.push((target, number));
        }
    }

    drop(seen);
    drop(pending);
    let mut path = Vec::new();
    for w in (1..nodes.len()).rev() {
        let mut edge = incoming[nodes[w].block];
        let mut semi = w;
        while edge != NONE {
            let label = evaluate(&mut nodes, edges[edge].from, &mut path);
            semi = semi.min(nodes[label].semi);
            edge = edges[edge].next;
        }
        nodes[w].semi = semi;
        nodes[w].bucket_link = nodes[semi].bucket_head;
        nodes[semi].bucket_head = w;

        let parent = nodes[w].parent;
        nodes[w].ancestor = parent;
        let mut member = std::mem::replace(&mut nodes[parent].bucket_head, NONE);
        while member != NONE {
            let label = evaluate(&mut nodes, member, &mut path);
            let next = nodes[member].bucket_link;
            nodes[member].bucket_link = if nodes[label].semi < nodes[member].semi { label } else { parent };
            member = next;
        }
    }
    drop(incoming);
    drop(edges);
    drop(path);
    for w in 1..nodes.len() {
        let candidate = nodes[w].bucket_link;
        if candidate != nodes[w].semi {
            nodes[w].bucket_link = nodes[candidate].bucket_link;
        }
    }

    let mut dominators = vec![None; block_count];
    for node in &nodes {
        dominators[node.block] = Some(nodes[node.bucket_link].block);
    }
    dominators
}

/// Return the best semidominator label along the linked path. Compress the
/// path iteratively so very deep shader graphs cannot exhaust the host stack.
fn evaluate(nodes: &mut [DfsNode], vertex: usize, path: &mut Vec<usize>) -> usize {
    let mut node = vertex;
    while nodes[node].ancestor != NONE && nodes[nodes[node].ancestor].ancestor != NONE {
        path.push(node);
        node = nodes[node].ancestor;
    }
    while let Some(node) = path.pop() {
        let ancestor = nodes[node].ancestor;
        let label = nodes[ancestor].label;
        if nodes[label].semi < nodes[nodes[node].label].semi {
            nodes[node].label = label;
        }
        nodes[node].ancestor = nodes[ancestor].ancestor;
    }
    nodes[vertex].label
}

/// Entry-order ranges for constant-time dominance queries. Each subtree
/// contains all and only the reachable blocks dominated by its root. Empty
/// ranges mark unreachable blocks and must be excluded from queries.
pub(super) fn subtree_intervals(
    parents: &[Option<usize>],
    entry: usize,
) -> Vec<std::ops::Range<usize>> {
    let mut children = vec![NONE; parents.len()];
    let mut siblings = vec![NONE; parents.len()];
    for (block, parent) in parents.iter().copied().enumerate() {
        if let Some(parent) = parent.filter(|_| block != entry) {
            siblings[block] = children[parent];
            children[parent] = block;
        }
    }
    let mut intervals = vec![0..0; parents.len()];
    let mut entered = 0;
    let mut pending = vec![(entry, false)];
    while let Some((block, exit)) = pending.pop() {
        if exit {
            intervals[block].end = entered;
            continue;
        }
        intervals[block].start = entered;
        entered += 1;
        pending.push((block, true));
        let mut child = children[block];
        while child != NONE {
            pending.push((child, false));
            child = siblings[child];
        }
    }
    intervals
}
