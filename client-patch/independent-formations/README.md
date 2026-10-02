# Rush independent party sets

This opt-in Android patch keeps the exact `generic-damage-8001-public-31cfc4bd.apk`
as its input. The client sends the Rush event id in `event/rush/party` and uses
party categories 5/6/7 for Abyss normal, Abyss EX, and Fantasy respectively.
Legacy clients and unknown events continue to use category 4 (`RUSH`).

The candidate uses Android admission id `android-181-independent-party-20260923`.

The helper ABC is appended to the existing main SWF. Only the event loading
event-id handoff, Rush-party request body, and party-holder category accessor are
changed; existing ABC layouts and unrelated APK members are preserved.

## SET 编辑 C8601 公网修复

独立编队把普通深渊、深渊 EX、幻想连战分别映射到分类 5/6/7。SET 编辑界面的旧标题分支只覆盖 1–4；`refreshPartyCategory` 将 UI 标题显示值归一到现有 Rush 标题，并为默认分支补上非空标题键。编队保存和请求携带的原分类不变。

Android 公网包以已修复的内网 APK 为输入，只把源包中的内网主机转换为 `175.178.160.158` 的 ABC 端点字符串，并更新 AIR UUID、重新签名。iOS 以此前的独立编队公网 IPA 为输入，在完整 ABC 中导入同一 SET 方法体，追加编译 hook，并把原 AOT 方法槽指向该 hook。两端准入 ID 和密钥沿用独立编队版本。

构建入口为 `package_set_edit_public_android.py`、`prepare_set_edit_ios.py`、`compile_set_edit_ios.py` 和 `link_set_edit_ios.py`；离线验收入口为 `verify_set_edit_release.py`。精确成品、范围及未测项见 `../ACCEPTANCE-SET-EDIT-C8601-20260924.md`。
