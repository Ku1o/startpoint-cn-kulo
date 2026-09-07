# 希耶提视觉资源恢复审计（1.4.98 → 1.4.99）

- 输出包：`pinball-1.4.98-1.4.99-1-siete-ui-restore.zip`
- 输出 SHA-256：`3a024838a67eecd8bc8a7cd853b50b45f1072dea3372fdaf8cf4b538ddad1d7b`
- 成员：29（25 PNG + 2 Android ATF + 2 iOS ATF）
- 源包：`pinball-1.4.89-1.4.90-1-0827-trio-ui-refresh.zip`（SHA-256 `827d8550fe14400df26c5ff4fc2f3309b8a9cea15d6203d35b153dfb64529cba`）
- 仅写入 `assets/asset-patch/active/` 和本审计目录；未修改 `.cdn/`、`manifest.json`。
- 目标只覆盖 `character/seofon_wind/ui/`，不含 ActionDSL/主表/文本。

## 成员哈希（恢复后）

- `character/seofon_wind/ui/battle_control_board_0.png` [medium] — `production/medium_upload/35/39416307eae2b336829a889f434b3ac553a7b0` — 53841 bytes — `09f87c3b0443270bcd741badd4ecd9ed7c161750a6891ea8b2e82b6f24b0bbed`
- `character/seofon_wind/ui/battle_control_board_1.png` [medium] — `production/medium_upload/b0/01a6f82056ee21c9c57d70621a27ed248c1d7c` — 53630 bytes — `29c30a1f3926c667f95041a18f6a5c67d665bd2eff2b84125ffef02f234f84c5`
- `character/seofon_wind/ui/battle_member_status_0.png` [medium] — `production/medium_upload/fb/411b02417803df1fb9d9eda6b84b3df459f5e0` — 13155 bytes — `c7071bf3aa2f89301a8c178c195dfa26c9bfdd62f2ee8960aa011ac3f78fddf0`
- `character/seofon_wind/ui/battle_member_status_1.png` [medium] — `production/medium_upload/15/a3e4fa936f3510a0b07c49826ed8a48be3a62f` — 13299 bytes — `ba4b910ac6b1884483c9f5111f11430e728b350c1f3615d30cf9b36ff65c2abe`
- `character/seofon_wind/ui/cutin_skill_chain_0.png` [medium] — `production/medium_upload/fe/8852e93862f16652277ddf19760dd935888458` — 173272 bytes — `261103dd084b2f03350ec6d00af9a0e461b2def0797add06158115be92d8b176`
- `character/seofon_wind/ui/cutin_skill_chain_1.png` [medium] — `production/medium_upload/9c/4839f9b2aeed59fc90e6a2e4009cf566689fda` — 167665 bytes — `2222ea82a99a7b8f7593424f94792ad08dcc547b067c3e33617225ddc7e580be`
- `character/seofon_wind/ui/full_shot_1440_1920_0.png` [medium] — `production/medium_upload/58/37896ccbf02c4d0f03013325c373798f300039` — 1600418 bytes — `7ef9d54f2afbef0a67bc2edd8726265239057f0c9acad1b8e64ad5d59020af20`
- `character/seofon_wind/ui/full_shot_1440_1920_1.png` [medium] — `production/medium_upload/9b/e5ada29ae297cb7b2adc63df7596f4226c07d9` — 4594328 bytes — `a38807324c7134b08e7b1147167202d472a55f11da91882051c72fe7b2918419`
- `character/seofon_wind/ui/illustration_setting_sprite_sheet.png` [medium] — `production/medium_upload/82/afc8200078e9a47824288bad614d08edaadd7b` — 454981 bytes — `b09b5c6614cbc3ea353ae1e66ed278a4e465bc496d09ce7fa637360cbd494c61`
- `character/seofon_wind/ui/skill_cutin_0.png` [medium] — `production/medium_upload/40/8fee3e1a1857eb4a9ee6ff1d4b36bda8741136` — 506982 bytes — `5dcff3fa0bd1c2fde29c96037b4e6d6281d99edb9fdc0bb27c4783fa3ca99281`
- `character/seofon_wind/ui/skill_cutin_1.png` [medium] — `production/medium_upload/07/031f0ce7c605eb129226613727708b998d10b8` — 766458 bytes — `00a4773b99864f464a0fb0ec02a538739fce8028dd64434369a3a41422ecce0e`
- `character/seofon_wind/ui/square_0.png` [medium] — `production/medium_upload/4e/ee888c94e6ed5b8e652877a1bbc8e853025a4d` — 104424 bytes — `e85595ac3c660f91dded01d5c2b5cff4360d6d11fcd8a63ba3a42f05dc169e48`
- `character/seofon_wind/ui/square_1.png` [medium] — `production/medium_upload/0a/6f1fc6aaefa45709eddd87cc35c42aee210914` — 80153 bytes — `4b6a5dc397c5c710620c4876f13f2a1f8ba7e9accb37c021d3d476abeacf0b01`
- `character/seofon_wind/ui/square_132_132_0.png` [medium] — `production/medium_upload/6e/158911105e5b38e11ff14970538f21263606af` — 48979 bytes — `671aeb204867a2f99b8be0b1b98edadc143e0bc71c9af897d8497dbfdb89fc0a`
- `character/seofon_wind/ui/square_132_132_1.png` [medium] — `production/medium_upload/b0/0620f60cfcddad31d3ac47884d2a52e4b223b1` — 43641 bytes — `f032914dfa40e7adb246aa79cccd783d3ea426e5e5aeda878ab0f78e741f6fdd`
- `character/seofon_wind/ui/square_round_136_136_0.png` [medium] — `production/medium_upload/da/341fec8cbe569d76ad35e586ee2a63d369e6f7` — 51663 bytes — `a7ac467f8192f00d1984e21335a06f21329f860e6585c20702c9ef497e1e6c44`
- `character/seofon_wind/ui/square_round_136_136_1.png` [medium] — `production/medium_upload/46/dcf4b634d2129329bc1627783008e5763e2c16` — 45810 bytes — `da958a7a99f552ed3ebb993d744b71173c89f87aee720cfbf6ba788b06249ac4`
- `character/seofon_wind/ui/square_round_95_95_0.png` [medium] — `production/medium_upload/63/78f12dc0da0d713df499623e30b3ee35ad0a9c` — 27710 bytes — `d1b8deb4e6c31c345626a4c134fd8c323c3cda8959920b1344ea8e4f7eed8977`
- `character/seofon_wind/ui/square_round_95_95_1.png` [medium] — `production/medium_upload/7d/439bef73b176602a591c21e87a9796a3351828` — 25716 bytes — `d585a97ac66f716367bfb364b2f5c7c75e6d6d3542b179bfa633765e0d210028`
- `character/seofon_wind/ui/thumb_level_up_0.png` [medium] — `production/medium_upload/b8/2049d0730a8a1438bb42c2b47026cfaaec383c` — 166401 bytes — `ca5928aaf674d62b7e5656f444d795d6e507396183bcbee3661272e87aa6ffb8`
- `character/seofon_wind/ui/thumb_level_up_1.png` [medium] — `production/medium_upload/a5/baee2a4f2e5180ae52b1846de8942101802722` — 133716 bytes — `e7deab4427b4a9ab779d2d295715f1ac83d9b4b156db51bb75a02706713d5989`
- `character/seofon_wind/ui/thumb_party_main_0.png` [medium] — `production/medium_upload/5e/507f5c41142573efa535bb38190d1d5c371621` — 161318 bytes — `b5db05787347e106059250252b78498920f990435894a2efd3f4bbeb98c24687`
- `character/seofon_wind/ui/thumb_party_main_1.png` [medium] — `production/medium_upload/24/95833545f5dd9b0d7e387fc7db44f9193751e5` — 144580 bytes — `aab07393f31b49a9c70b5fa15cf07e24cd6e2cc9d3a2f7aac899ef7115dd266a`
- `character/seofon_wind/ui/thumb_party_unison_0.png` [medium] — `production/medium_upload/f4/02ee5ec61361cc7042957b4b7cbb2e42af2925` — 69733 bytes — `afbf0bd5cbe6c4254b8c2f6b20571fbe805d33507dcf888384c6b392fb097f47`
- `character/seofon_wind/ui/thumb_party_unison_1.png` [medium] — `production/medium_upload/90/7357bae524a6db26c69996ab99200477c8dcba` — 57322 bytes — `4ff801b5e5edd03fd932002387be4875f0676a8b1acc8b40ec5517de4743a71e`
- `character/seofon_wind/ui/skill_cutin_0.atf.deflate` [android] — `production/android_upload/6c/7673801cc6b8c76ebf7f6688415cb37775c7e2` — 154233 bytes — `81089f684690a513ee8d696d6fd07b22c28e00a322022c4e47a6dbf5c342a658`
- `character/seofon_wind/ui/skill_cutin_0.atf.deflate` [ios] — `production/ios_upload/6c/7673801cc6b8c76ebf7f6688415cb37775c7e2` — 173379 bytes — `2d46ac303b9342a744db10c9ee0fde2a68fc55de70dde5a6a9dac3cfc5735d37`
- `character/seofon_wind/ui/skill_cutin_1.atf.deflate` [android] — `production/android_upload/27/9a6414cae68c729c11d055dcac5fca68713aee` — 210062 bytes — `27b6855dc22f68b95f273d2e1ef7f87217a5cd2b78ba0bcfb6f160710f2c6abd`
- `character/seofon_wind/ui/skill_cutin_1.atf.deflate` [ios] — `production/ios_upload/27/9a6414cae68c729c11d055dcac5fca68713aee` — 264010 bytes — `636b74c8fc3ffaa32b92eea796502cc46ee5a32cbddacc922385385c5e9af703`
