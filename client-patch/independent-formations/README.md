# Rush independent party sets

This opt-in Android patch keeps the exact `generic-damage-8001-public-31cfc4bd.apk`
as its input. The client sends the Rush event id in `event/rush/party` and uses
party categories 5/6/7 for Abyss normal, Abyss EX, and Fantasy respectively.
Legacy clients and unknown events continue to use category 4 (`RUSH`).

The candidate uses Android admission id `android-181-independent-party-20260923`.

The helper ABC is appended to the existing main SWF. Only the event loading
event-id handoff, Rush-party request body, and party-holder category accessor are
changed; existing ABC layouts and unrelated APK members are preserved.
