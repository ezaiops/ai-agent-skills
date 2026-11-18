# 角色护照（Asset Passport）

AI 模型没有跨段记忆——角色在段与段之间漂移（脸变、服装换、武器消失）的根因，是每个 prompt 没有重新声明外观。护照就是一段**逐字复制**的固定文本块。

## 护照模板

```text
<CHARACTER> the same [name/type]: [face — 脸型/年龄/五官特征], [hair — 发型/颜色],
[sclera/eyes — 眼神特征], [build — 身形/体态], [outfit — 服装: 上衣/下装/颜色/材质/破损],
[props — 武器/饰品: 名称/形态/材质], appearance unchanged for the entire video.
</CHARACTER>
```

## 使用规则

1. **逐字复制**：护照文本写好后，复制粘贴进每个相关场景 prompt 的最前面（六段式的 PASSPORT 段），一字不改。
2. **每场景一个**：主角色每段都带；配角出现哪段带哪段。
3. **多角色用编号**：`Character A = ...`, `Character B = ...`，并在参考图映射里写死 `Picture 1 = Character A, Picture 2 = Character B`，防止模型结构混淆。
4. **冲突时信任护照**：如果生成画面与护照冲突，修改生成参数而不是改护照——护照是整个项目的"法律"。
5. **护照图锁定**（更强手段）：用 img2img 从护照图衍生各姿态关键帧（`--image base.png --prompt "NEW COMPOSITION: same character ..."`），再走 keyframe 模式锁定首帧。

## 示例（墨韵剑客）

```text
<CHARACTER> the same swordsman: lean young man, sharp jawline, dark narrow eyes,
black topknot hair with a single grey streak, pale grey hanfu robes with black sash,
a long thin jian sword in a bamboo scabbard, appearance unchanged for the entire video.
</CHARACTER>
```

## 护照 + keyframe 流程（agnes 实测推荐）

1. 先生成护照基准图（text-to-image，正面全身）。
2. 每个场景用 img2img 衍生该场景的姿态/机位首帧。
3. scenes.json 该场景填 `first_frame`（Data-URI base64 即可，无需托管）。
4. prompt 开头写 `The [passport] moves from this exact composition ...`，首帧构图即被锁定，跨段漂移大幅下降。