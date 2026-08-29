# V51 客户端恢复游戏内“数据继承”入口

本文记录 CN V51 客户端中恢复现成数据继承入口的最小修改方法，便于其他项目复现。

> 适用范围：已确认适用于本项目使用的 CN V51 AIR APK。其他版本的类名和菜单顺序可能不同，应先核对原始逻辑，不要直接照搬行号。

## 结论

V51 客户端并没有删除数据继承功能。以下内容原本都还存在：

- 数据继承场景和四步界面；
- “玩家 ID + 继承密码”恢复流程；
- 设置或重设继承密码流程；
- 菜单图标和本地化文案；
- 点击菜单项后进入继承场景的处理分支。

游戏内菜单不显示“继承”，只是因为创建菜单列表时漏掉了 `MenuTopListItemKind.TakeOver`。因此，**必要的客户端逻辑修改只有一处：把这条菜单数据重新加入列表。**

## 必要修改：恢复游戏内菜单入口

### 1. 取出主 SWF

先复制一份原 APK 作为工作副本。APK 本质上是 ZIP，主程序 SWF 位于：

```text
assets/worldflipper_android_release.swf
```

可用 7-Zip、解压工具或 ZIP 库只取出这个文件。

### 2. 导出目标 AS3 类

用 FFDec 打开 SWF，定位到：

```text
pinball.scene.menuTop.MenuTopScene
```

需要修改的方法是：

```text
createMenuListData()
```

也可以使用命令行导出单个类。以下示例以 FFDec 26.2.1 为例：

```bash
java -jar ffdec.jar \
  -selectclass pinball.scene.menuTop.MenuTopScene \
  -export script export_dir worldflipper_android_release.swf
```

导出的源文件通常位于：

```text
export_dir/scripts/pinball/scene/menuTop/MenuTopScene.as
```

### 3. 把 TakeOver 菜单项加回数组

在 `createMenuListData()` 中找到 `FollowFollower` 和 `ApplicationOption` 两项，在它们之间插入：

```actionscript
{
   "kind":MenuTopListItemKind.FollowFollower,
   "content":MenuListContentKind.IconAndText(
      "scene/general/sprite_sheet/vector_icon-assets/follow",
      "menu_follow_and_follower"
   )
},{
   "kind":MenuTopListItemKind.TakeOver,
   "content":MenuListContentKind.IconAndText(
      "scene/general/sprite_sheet/vector_icon-assets/take_over",
      "title_menu_take_over"
   )
},{
   "kind":MenuTopListItemKind.ApplicationOption,
   "content":MenuListContentKind.IconAndText(
      "scene/general/sprite_sheet/vector_icon-assets/option",
      "menu_option"
   )
}
```

对应的最小差异是：

```diff
 {
    "kind":MenuTopListItemKind.FollowFollower,
    "content":MenuListContentKind.IconAndText("scene/general/sprite_sheet/vector_icon-assets/follow","menu_follow_and_follower")
+},{
+   "kind":MenuTopListItemKind.TakeOver,
+   "content":MenuListContentKind.IconAndText("scene/general/sprite_sheet/vector_icon-assets/take_over","title_menu_take_over")
 },{
    "kind":MenuTopListItemKind.ApplicationOption,
    "content":MenuListContentKind.IconAndText("scene/general/sprite_sheet/vector_icon-assets/option","menu_option")
 }
```

V51 原本已经有对应的点击处理，不需要再次添加：

```actionscript
case 8:
   changeSceneWithLoading(
      LoadingTaskKind.TakeOver,
      ChangeSceneBackKind.AddCurrent
   );
   break;
```

如果其他版本不存在 `MenuTopListItemKind.TakeOver`、上述 `case 8`、`LoadingTaskKind.TakeOver` 或 `SceneKind.TakeOver`，说明该版本不是单纯隐藏入口，不能只套用这一处补丁。

### 4. 制作 carrier 并只移植目标方法体

完整类导入或完整类替换只能用于制作临时 carrier，不能把 carrier SWF 直接回封发版。FFDec 可能
重编译常量池和大量无关方法体，即使源码只改了一处也不能证明其他客户端功能没有变化。

可先用 FFDec 把修改后的类导入临时 carrier：

```bash
java -jar ffdec.jar -onerror abort \
  -replace worldflipper_android_release.swf carrier.swf \
  pinball.scene.menuTop.MenuTopScene \
  export_dir/scripts/pinball/scene/menuTop/MenuTopScene.as
```

随后从 carrier 导出 P-code，只截取 `createMenuListData` 方法，并在干净基线中重新定位方法体索引后，
用 FFDec `-replace <P-code> <methodBodyIndex>` 移植。标题菜单应对
`TitleMenuDialogContentView.setupContents` 使用同一方法体移植流程。最终必须使用全方法体比较器证明
只变化这两个目标方法体。

本项目当前已把这两个载荷、精确局域网 Rush 基线和自动门禁固化在
[`client-patch/account-takeover`](../client-patch/account-takeover/README.md)，应优先使用该构建器，
不要再按本文手工回封完整类。

2026-08-30 真机验收后的权威公网 APK SHA-256 为
`0C7BBA3D8E2EF07B8AC9E98B11AAF257008A0B373950FD98332047C727064857`，内嵌 SWF SHA-256 为
`7EEA1972F568E31CE5B708E057EB7FEF306E2B25BA5CF7C6A198557914623CA7`。后续修改必须从该公网
成品开始；累计构建器的 `--target public` 用于重建同一 SWF 并自动检查继承入口、Rush 排行榜、角色
轮播和公网地址没有丢失。公网模式还会以 V51 SWF
`EB7962184DF5E7D1DA112E4BEF9DED8DB8526E14A6F6F1710E051063A8F1D17C` 为历史参照，严格核对
后续 19 个方法体变化，确保 MOD 五合一和幻想连战客户端实现同样没有被覆盖。

### 5. 放回 APK、对齐并签名

用只完成目标方法体移植的 SWF 替换 APK 中同路径文件：

```text
assets/worldflipper_android_release.swf
```

随后执行 APK 对齐和签名，例如：

```bash
zipalign -p -f 4 unsigned.apk aligned.apk
apksigner sign --ks your.keystore --out final.apk aligned.apk
apksigner verify --verbose --print-certs final.apk
```

只要 SWF 载荷变化，就必须在同一包中生成全新的 AIR `uniqueappversionid`。回封后还必须回读实际
APK，验证 SWF 哈希、UUID 唯一性、无关 ZIP 成员保持、zipalign、v1/v2 签名和证书指纹。

覆盖安装时必须使用与设备上旧 APK 相同的签名证书；否则 Android 不允许覆盖安装。更换签名通常只能卸载后重装，而卸载可能清除本地数据。

## 最小验证

只验证“入口恢复”时按以下步骤即可：

1. 安装修改后的 APK 并进入游戏。
2. 打开底部“菜单”。
3. 在“关注·关注者”和“设置”之间确认出现“继承”。
4. 点击“继承”，确认能进入客户端原有的数据继承场景。

如果按钮已经显示，但点击后出现网络错误，说明客户端入口补丁已经生效，问题在服务端接口，不应继续修改菜单代码。

## 标题菜单：把“下载设定”替换为“数据继承”

如果需要让尚未创建临时账号的新设备直接恢复账号，就必须修改标题菜单的实际显示列表。只调整
`TitleMenuDialog.prepare()` 的按钮逻辑顺序不会改变四个可见槽位，已经由真机截图证明无效。

V51 的标题菜单同样已经有按钮 ID `0` 的处理：

```actionscript
case 0:
   logicScene.changeSceneWithDetail(
      ChangeSceneNextKind.Scene(SceneKind.TakeOver(Option.None)),
      ChangeSceneBackKind.AddCurrent
   );
   break;
```

四个可见按钮实际由下列方法硬编码：

```text
pinball.dialog.titleMenu.TitleMenuDialogContentView.setupContents()
```

把最后一个“下载设定”按钮 ID `6` 替换为继承按钮 ID `0`：

```diff
-_loc1_ = _loc1_.concat([11,12,4,6]);
+_loc1_ = _loc1_.concat([11,12,4,0]);
```

这样标题菜单右下角会由“下载设定”直接变成“数据继承”，并进入现成的数据继承流程。
`TitleMenuDialog.prepare()` 应保持原版不变。

## 可选配套：让继承功能真正可用

以下内容不影响菜单项是否显示，但服务端若不实现，玩家只能看到界面，不能完成设置密码或迁移账号：

```text
/take_over_register/get_take_over_setting
/take_over_register/register_take_over_data
/take_over/get_user_data_by_take_over_data
/take_over/take_over_by_take_over_data
```

客户端原有逻辑会根据 `get_take_over_setting` 的响应判断账号是否已设置继承密码，并显示“设置继承密码”或“重置继承密码”。这部分通常不需要继续修改 APK。

服务端迁移时还应自行保证：

- 同一恢复操作只能成功一次；
- 新设备的临时账号不会残留；
- 老账号的存档、玩家 ID 和管理备注保留；
- 旧设备不能继续同时使用同一账号；
- 数据库修改在一个事务中完成。

本项目的服务端实现和测试说明见 [数据继承服务端说明](./account-takeover-server.md)。

## 与本补丁无关的改动

以下常见改动都不是“游戏内显示继承”所必需的，应根据各自项目决定是否使用：

- `sdkDummy=true`：跳过雷霆 SDK 登录；
- 修改 API host 和 HTTP/HTTPS：让客户端连接自建服务器；
- 标题菜单数据继承入口；
- 管理端重置继承密码；
- 账号备注迁移和旧设备失效策略；
- 隐藏 Google 账号绑定入口。

尤其不要为了显示继承入口把 `sdkDummy` 改回 `false`。那会重新进入雷霆 SDK 登录流程，但不会解决自建服务端的账号迁移问题。

本次验证中，尝试隐藏继承页面里的 Google 账号入口没有稳定生效，相关版本已撤销。因此本文不把“隐藏 Google 入口”作为已验证方案，也不要将它与恢复游戏内继承入口混为一谈。
