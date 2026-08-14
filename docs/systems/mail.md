# 邮件系统(Mail)
> 状态: 已实现   关键文件: assets/item_ids.json, assets/character.json   相关端点: /mail/send, /mail/index

本文档描述邮件系统的实现:邮件 CDN 附件校验,以及邮件到达通知的动态计算。

## Mail notification
- **Mail notification**: `mail_arrived` is computed dynamically from `players_mails` table (unreceived count > 0).

## Mail CDN validation
`/mail/send` (Dashboard group mail) validates `type_id` against CDN data before inserting:
- CHARACTER (type=5): checked against `assets/character.json` (505 IDs)
- ITEM (type=1): checked against `assets/item_ids.json` (1284 IDs)
- EQUIPMENT (type=6): not yet validated (no converted equipment asset)
- Invalid IDs → redirect with error message, mail NOT sent

`assets/item_ids.json` extracted from `wf-assets-cn/orderedmap/item/item.json` — 1284 item IDs matching `docs/邮件附件对照表.xlsx` 道具对照表 count.
`assets/item_data.json` only contains 100 stamina-related items with effect info — for `/item/use_item` endpoint, NOT for validation.
