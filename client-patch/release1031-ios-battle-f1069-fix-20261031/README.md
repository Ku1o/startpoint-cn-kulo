# iOS battle F1069 getter repair

The cumulative caller code references `BattleAbilityTotalizerImpl.getTotalDashParameter(index:int):Number`, but an Android method unchanged from its donor was omitted by the earlier iOS difference selection. The sealed iOS receiver therefore lacks the method. `prepare/prepare_getter.py` appends the real getter using the existing field and `DuringCheckerWithDecimal.sum`; native stages compile and bind that one method without changing the old field or inherited-slot layout.

The direct input IPA is `8e6845291b3b83a41844c241c562961dc097cf2297599f2940cacffec220011c`. The historical output IPA is `67dcd483aa3f7e500b9d2ed494b2106fe8b30da0f1c5f05415828563e7ac5b78`; complete ABC `ccb1e564a5650b57219cf7f7354ba1da971f5702a0cbc503ce165ca58bfaee8e` contains 101873 methods. This IPA is the direct input to the later independent-party native repair.

Source roles, external artifact graph, bounded execution and evidence limits are described in [FOLLOWUPS.md](../release-20261031/ios/FOLLOWUPS.md). The original package's 60 desktop AIR assertions and native readback remain bounded offline evidence. A newly relocated recipe has not produced a new IPA. See [historical registration](../ACCEPTANCE-RELEASE1031-IOS-BATTLE-F1069-20261031.md).
