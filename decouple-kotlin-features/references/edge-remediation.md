# Cross-feature edge remediation

Choose the smallest semantic boundary that preserves behavior:

| Observed dependency | Preferred response |
|---|---|
| UI consumes another feature’s reusable widget | Move provider-owned surface and resources to provider `shared-ui` |
| Feature navigates to another feature | Depend on the provider navigation contract |
| Consumer needs a stable capability/query | Define an owner domain port; bind its implementation outside the consumer |
| Consumer reacts to a completed action | Publish an owner-defined event/fact |
| Multiple features share a stable app-wide concept | Consider a reviewed core foundation |
| Consumer imports another feature’s data/UI implementation | Cut the edge; implementation modules are not contracts |

Do not introduce callbacks, events, or core models merely to make a graph look
clean. A direct domain or navigation dependency can be correct when ownership
and stability are explicit. Shared UI belongs to the provider and must not
depend on another shared-UI or consumer UI module.
