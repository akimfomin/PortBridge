# Partition the public preflight index

## Accepted on 2026-11-25

The public CLI, MCP server and one-PR action downloaded every public observation to run one search. The source file grows with every tracked repository. Raising its download limit preserves the immediate release window.

The static exporter now builds a separate search index. An exact source lookup fetches its compact record, related matches and any source-only fallback from a hash partition. Text and number queries fetch selected term or number postings. The same ranking code builds the cases and source suggestions used by the local path. The index keeps source URLs and the provenance of verified reports.

A shard is at most 128 KiB, and a query requests at most 20 shards. A broad text query selects eight technical terms and each term or issue number keeps at most 96 rows under its byte budget. The client reports partial coverage when those limits affect the query. Exact source lookups keep enough ranked results for the same top twenty even when the verified first check is removed as a duplicate.

The site snapshot announces a version and generation, and the search manifest identifies the matching immutable filenames. Each shard name encodes the generation and a bounded hash prefix. The exporter writes the shards before updating the manifest and site marker. It checks old generated filenames and headers before removing them. The client can revalidate the site and manifest once when the generation changes, with a shared request budget. Only a legacy site snapshot without the index marker uses the bounded bulk observations download.

The browser's public case and match lists keep their existing snapshots. The bulk observations export is still available for tools that intentionally need it. The index trades more bytes at publication and additional file entries for much smaller interactive downloads. A deployment rollback uses the previous checkout and a fresh export directory.

Optional global discovery makes a single anonymous request to GitHub's issue and pull request search using selected technical terms. It exposes external links as candidates alongside the catalog result and leaves confirmed coverage and the first test unchanged. The request runs only when the caller explicitly enables the option. [GitHub search API](https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests) · [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
