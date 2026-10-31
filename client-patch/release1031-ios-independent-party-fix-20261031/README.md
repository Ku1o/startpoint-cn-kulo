# iOS independent Rush party native repair

Three original iOS native entries still use legacy party category 4 although their complete ABC already selects independent Rush parties. The repair compiles the methods in their real owner classes, updates both native method tables, and binds the original entry branches:

| Method | MID | Contract |
| --- | ---: | --- |
| RushEventLoadingTask.summaryRemoteInput | 42394 | receiver x0, input x1, MethodEnv x2 |
| EventRushPartyRealRemote constructor | 52468 | receiver x0, nullable RealRemote x1, nullable HookEntrance x2, MethodEnv x3 |
| RushEventPartyGroupHolder.getPartyCategory | 22164 | receiver x0, MethodEnv x1, int result w0 |

The existing independent-party helper maps normal Abyss 700099 to category 5, EX 700100 to 6, Fantasy 700098 to 7, and other Rush events to 4. No methods or storage fields are added. The F1069 getter, complete ABC, runtime declarations, SWF, bundle and admission pairing are retained. This corrects a client/server party mismatch; the reported C2620 disappearance still needs a matching iOS device retest.

The direct input IPA is `67dcd483aa3f7e500b9d2ed494b2106fe8b30da0f1c5f05415828563e7ac5b78`. The registered output IPA is `1990178abd4078beb39e26e5c2f985b6cc1af4900c72868f5b79221fcc21e907`, 183619451 bytes. Only the native member changes; 3567 other compressed members retain their bytes. `package.py` is the native-only packaging entry used for this output.

Source roles, external artifact graph, bounded execution and evidence limits are described in [FOLLOWUPS.md](../release-20261031/ios/FOLLOWUPS.md). The original package has three-function/45-relocation readback, six table bindings, actual ARM64 ABI checks, 80 desktop AIR assertions and server party-contract evidence. These are offline results; iOS native execution and device acceptance remain untested. See [registration](../ACCEPTANCE-RELEASE1031-IOS-INDEPENDENT-PARTY-20261031.md).
