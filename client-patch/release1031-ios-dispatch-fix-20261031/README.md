# iOS cumulative dispatch repair

The reviewed 25 instance helpers previously changed original inherited dispatch/field contracts. The repair moves them into `cn.release::DispatchHelpers20261031`, preserves original classes and storage, and recompiles the independently audited caller closure. Existing MethodInfo, activation and script contracts remain guarded. Native linking also preserves loader data and old unwind boundaries; exact compact-unwind page payloads may share storage without losing entries.

The direct public input IPA is `f4e08c4e5a65de080ca323eaaa35c6a0af90280bf942edcfab050d73f84d3bd8`; the original output IPA is `8e6845291b3b83a41844c241c562961dc097cf2297599f2940cacffec220011c`. The latter has complete ABC `7568bf806d123809c89a0d1ad7882135299f229778887bfd300b24c8d165a530` and 101872 methods. It is a historical input to the subsequent getter repair.

Source roles, external artifact graph, bounded execution and evidence limits are described in [FOLLOWUPS.md](../release-20261031/ios/FOLLOWUPS.md). `SOURCE-MANIFEST.json` pins this source closure. The audit/prepare/native/verify scripts are implementation sources, not private receipt copies. No iOS device execution is claimed by this source export.
