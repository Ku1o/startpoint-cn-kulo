# Android content operations bridge

The bridge makes existing native pages follow the authenticated operations snapshot delivered on normal login/load. After an administrator opens A and closes B, a complete logout and login obtains the new snapshot: native activity enumeration, gacha eligibility and the current pass follow the new A/B decisions. The helper creates no player controls, history menu, period selector or alternate navigation. There is no periodic network refresh, foreground refresh request or automatic activity-page transition. Operators can require everyone to log in again when publishing new settings; the server remains authoritative for mutations while an older session is open.

The reserved relogin protocol is `result_code = 101` with `data.message` exactly equal to `活动与卡池配置已更新，请重新登录。`. `Logic.remoteCommonInput` recognizes only `WholeMaintenanceError` index 9 with that single unchanged message, after the original crash and attention error notifications. It invokes the existing `Logic.openDateChangedDialog`, which reads `change_date_dialog_message` and supplies the original title-scene callback. Both diagnostic timestamps receive the same current real-time sample; no `Clock` state, epoch or elapsed duration is changed to simulate a new day. Ordinary maintenance and unrelated errors keep their original switch and messages. RequestQueue, RemoteUtil, native date-dialog and title methods remain unchanged. The response marker does not create a new dialog or display the maintenance error object with `No.A101` on the reserved route.

The initial bridge builder continues the accepted Android public APK from `android-accepted.json` `variants.public`. It adds an independent state class and bounded hooks to the actual main ABC. Existing class layouts, method signatures, unrelated bodies, original instruction order and control flow are preserved. APK signing, endpoint conversion and AIR/DEX cache identity rotation are separate steps. This entry describes the initial bridge, not a complete rebuild recipe for the later cumulative client.

Full snapshots carry independent action overrides plus `default_policy.actions[action].closed_keys`, `qualified_rights_keys` and `legacy_keys`; explicit actions take priority. Missing unreviewed seasonal entries close, while explicitly reviewed core shops/missions retain their native qualification rules. Corrupt or stale controlled snapshots cannot reopen content. Snapshot processing does not reset saved progress, inventory or earned rights.

`GlobalLogic.getTime` and `getOptionTime` synchronize the existing `ComplexTime` server epoch with `server_time_ms` plus monotonic elapsed time. Frame elapsed duration and `Option.None` behavior stay intact. Scene updates perform only local clock, cache and expiry maintenance. Gacha, native event enumeration, exact quest/mission scopes, pass/active/collect periods, box periods, shop products and parent gates consume the snapshot. Resource availability and original entitlement, stock, currency, ticket, prerequisite and recurrence checks remain required.

The current native pass is selected from operator-visible periods. Multiple visible periods fail closed. Claim rights alone never select a hidden old pass or revive an entrance. Original master dates can select a pass only through the explicit reviewed legacy visibility whitelist. Closing the entrance leaves stored pass progress and server claim rights intact; an operator may show that period again when appropriate.

Native special, StartDash and multi-special self-select exchange flows remain in the original client. Their period and action predicates follow the snapshot without a new menu or retained-history route. Native box draw/reset/close calls retain the passive action guard and original execution path when allowed. Date labels update existing text controls; the helper does not construct UI widgets.

Event identity follows the existing native `getEventId()` accessor and its `EventIdKind` result. Most activity classes store `id`, while the sealed ScoreAttack and SoloTimeAttack classes store `eventId`; reading a uniform `id` throws AS3 #1069. Campaign-derived activities may inherit their accessor. The helper uses the shared accessor instead of deriving identity from class names and assumed fields. Unsupported non-event inputs keep the original fallback.

## Cumulative source and client compatibility

The isolated Android implementation progressed through the following cumulative
source areas. These labels identify the historical increments and their guarded
inputs; they do not promote any artifact into the accepted registry.

| Increment | Source responsibility |
| --- | --- |
| R5 / R6 | Core login snapshot bridge, native event identifiers, activity and gacha routes in `build_bridge.py` and `ContentOperationsState.as`. |
| R7 | Request identity preservation and native historical entry hooks in `build_request_identity.py`. |
| R8 | Existing native date controls and bounded text display in `build_period_display.py`. |
| R9 | Exchange and native period-consumer repairs in `build_exchange_repair.py`. |
| R10 | Permanent personal-history access and unknown-date rendering in `build_player_history.py`. Daily mission restoration is a separate server change. |
| R11 | Login-scoped town selection in the adjacent [town-theme source](../town-theme/README.md), preserving the preceding operations and profile patches. |

The AS helper is cumulative source. The incremental builders intentionally
retain exact historical APK/SWF input hashes and method-preservation guards;
the table is not an instruction to run every builder against the latest
accepted package or against each other's freshly compiled helper. Reproducing
a historical increment requires its exact input and matching source revision.
For new client work, select the platform's accepted registry entry first and
audit its existing cumulative methods before choosing a builder. A mismatched
input must fail rather than bypass its guard or rewrite a historical hash.

The complete isolated feature set requires a client carrying the cumulative
operations, profile and town protocol hooks. Merging these source files does
not rebuild or distribute the isolated R11 APK, update an accepted registry,
change admission settings, or provide an iOS counterpart. APK/IPA, SWF/ABC,
signing material and local build reports stay outside Git. Package readback,
device acceptance and any later registry promotion remain separate steps.

## Initial bridge build and verify

Use an exclusive task directory for `--work`; pass an existing AIR SDK and Java runtime. The builder keeps its accepted APK/SWF hash assertions. No accepted-registry, CDN or service changes occur. The commands below cover the initial bridge workflow; they do not reproduce the complete cumulative R11 package.

```powershell
python -B client-patch/content-operations/build_bridge.py --work <TASK>/android-admin-only-r5 --sdk <AIR_SDK> --java <JAVA_EXE>
python -B client-patch/content-operations/offline_runtime_test.py --work <TASK>/android-admin-only-r5 --sdk <AIR_SDK> --java <JAVA_EXE>
python -B client-patch/content-operations/verify_android_bridge.py --work <TASK>/android-admin-only-r5
```

The AIR harness imports the complete compiled production helper, patched production `GlobalLogic` getters, the patched `Logic.remoteCommonInput` and unchanged `Logic.openDateChangedDialog` into isolated fixtures, comparing normalized instructions and control flow before execution. Its assertions cover login snapshot A/B changes, closed passes with retained claims and live legacy dates, reviewed legacy fallback, repository invalidation, independent action scopes and original fallback rules. It executes the real native error routing and date-dialog bodies to verify the exact marker, ordinary maintenance fallback, preserved crash/attention notifications, unchanged clock fields and confirmation callback. Call traps verify that local updates do not request network refresh or change scenes. Readback rejects player-selector, network-request and scene-transition symbols in the helper and proves the original Home, manual pass, Clock and RequestQueue bodies unchanged.

Event regressions use sealed inheritance fixtures with the native identifier slots for all 15 event families. Their actual production `getEventId`, enum constructors and `EventLogicBase` period/date bodies are imported with exact normalized instruction/control-flow comparison. This covers ScoreAttack/SoloTimeAttack without a fictional `id` slot and a campaign subclass inheriting its accessor. Verification records each real getter and slot in `native-event-accessor-abi.json`; no original event-class layout or getter is modified in the game candidate. For an R4 reproduction input copied to a separate evidence directory, `offline_runtime_test.py --expect-f1069` requires both affected sealed classes to reproduce the original #1069 through the native period chain; its production-import receipt identifies the old SWF. Normal R5 scenarios must execute successfully instead of catching the defect.

Reports, counts and hashes belong to each task output directory. AIR fixtures and static readback do not establish game execution or Android device acceptance. A game-level acceptance run still needs the administrator to change A/B, force a full relogin, and verify the existing native pages plus normal gacha, reward and exchange behavior.
