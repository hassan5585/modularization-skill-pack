# Module consolidation criteria

Strong evidence includes repeated configuration/task overhead, no meaningful
incremental-build isolation, extremely small modules with identical owners and
release cadence, inseparable public APIs, or redundant aggregation layers.

Weak evidence includes module count alone, an unfamiliar graph, or one noisy
build. Preserve boundaries that isolate volatility, platform targets, public
contracts, reusable capabilities, test support, persistence schemas, or native
exports. Simulate dependency replacement before moving files and compare the
same build scenarios after consolidation.
