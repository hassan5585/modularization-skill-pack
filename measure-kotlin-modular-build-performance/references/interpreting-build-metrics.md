# Interpreting build metrics

| Signal | Possible cause |
|---|---|
| UI change recompiles many features | Over-broad `api` edges or shared root coupling |
| Domain change always rebuilds app fully | Missing ABI isolation / too few modules |
| Convention change invalidates everything | Expected; measure size of blast radius |
| Configuration cache never reused | Build logic or env inputs unstable |
| Clean build much slower after split | Too many modules / configuration overhead |

Performance findings are **informational** for architecture verification — they
do not override correctness gates.
