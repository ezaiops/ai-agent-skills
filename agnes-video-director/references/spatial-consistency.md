# 空间一致性（Spatial Consistency）

AI 视频模型没有记忆，也**不追踪场景内物体的坐标**。它每一段、每一帧都在重新"猜测"画面，追求"看起来合理"而非"逻辑正确"。所以"灯笼本来在左边、结尾跑到右边"这类位置漂移是常态，不是偶发 bug。

解决思路：**别指望模型想明白，要给它画明白**。三道防线，强度递增。

---

## 防线 1：场景护照 + 空间锚定（提示词层）

角色有护照，场景也要有护照。每段 prompt 开头声明完整场景状态，并**反复重申关键物体的固定位置**。

模板：

```text
single continuous shot. The same [place type]:
[object A] on the LEFT [anchor point] and stays on the LEFT for the entire shot,
[object B] on the RIGHT [anchor point],
[ground material], [weather/light].

0-4s   ... [object A] glows on the left as the camera pushes in ...
4-8s   ... [object A] stays visible on the LEFT edge ...
8-12s  ... [object A] still on the LEFT as [character] walks away ...
```

规则：
- **空间锚定（Environmental Anchoring）**：场景里散布稳定的静态几何参照（墙、柱、拱门、灯笼、木桶、山崖）——模型有背景做视差，主体才不容易乱飘；用背景掠过来体现速度，而不是让主体糊掉。
- **写"是什么"而非"别是什么"**：`lantern on the LEFT` 重复三次，比 `don't move the lantern` 有效得多。正向描述 > 负向禁止。
- **`single continuous shot` 前置**：段首声明，强制时间一致性，减少插值伪影。
- **每段交代相对位置**：时间戳分段里，让关键物体在每段出现一次位置提示，锁死坐标。

---

## 防线 2：首尾帧锁 + 链式延伸（最强手段）

位置漂移的**真正答案**是图钉，不是嘴说。

| 手段 | 做法 | 效果 |
|---|---|---|
| **首帧锁** | 先 text2img / img2img 生成起始构图，作 `first_frame` 提交 | 开头构图 100% 锁定 |
| **首尾帧** | `first_frame` + `last_frame` 同时给 | 模型必须在两个锚点间插值——物体跑不过锚点 |
| **链式延伸** | 段1 的尾帧 = 段2 的首帧 | 跨段状态继承：道具、姿态、场景损伤连续 |

### 链式工作流（agnes 实现）

```
s01: 首帧A(独立) → 尾帧B
s02: 首帧B(上段尾帧) → 尾帧C
s03: 首帧C(上段尾帧) → 尾帧D
```

1. 第 1 段：`first_frame` 给手绘/生成的关键帧 A。
2. 每段生成完后，**抽该段尾帧**（`ffmpeg -sseof -0.2 -i s01.mp4 -frames:v 1 tail.png` 或取 12s 处帧）。
3. 下一段的 `first_frame` = 上一段的尾帧图（Data-URI base64 即可，无需托管）。
4. prompt 写：`The [passport] continues from this exact composition, [new action], transition smoothly to the last-frame composition`。

道具、姿态、光照在切点处完全连续——跨镜头一致性工业级做法。

### 尾帧截取命令

```bash
# 取 12s 段的最后一帧（偏移 -0.3s 避开黑场）
ffmpeg -y -sseof -0.3 -i segments/s01.mp4 -frames:v 1 chain_s01_tail.png -loglevel error
# 下一段 first_frame 用这个 Data-URI
python3 scripts/gen_image.py --prompt "use this as first frame" ...
# 或直接塞 scenes.json 的 first_frame 字段
```

---

## 防线 3：生成策略——短段、少动作、抽卡

- 12 秒塞 3 个以上逻辑动作，出错率指数上涨。复杂动作拆成 4-6s 段，每段 ≤ 2-3 个实体动作。
- 高难物理交互（刀插墙、物体碰撞、穿模高发）最易翻车：写轨迹拆解，或直接简化成"刀落地"。
- **抽卡大法**：同一 prompt 换 seed 多生成几条挑。一致性崩了时，抽卡比重写词快。

---

## 物理/逻辑错误的特解：轨迹拆解

错误写法（写结果）：`the sword sticks into the wall` → 模型瞎猜"怎么插进去的"，容易穿模。

正确写法（写轨迹，四步链）：

```text
the sword leaves his hand → spins half a turn in the air →
sinks diagonally into the mud wall point-first →
the hilt remains stuck outside the wall, quivering
```

每步都是"中间状态"，模型逐帧可执行，插入路径是确定的。

---

## 速查表

| 问题 | 手段 | 强度 |
|---|---|---|
| 位置漂移（灯笼左→右） | **首尾帧 keyframe** | ★★★ |
| 跨段状态不连续（道具/姿态） | **链式：尾帧→首帧** | ★★★ |
| 角色漂移（脸/服装） | 角色护照 + reference 模式 | ★★★ |
| 物理错误（刀挂墙） | 轨迹拆解 + 简化动作 + 短段 | ★★ |
| 背景/道具轻微漂移 | 场景护照 + 空间锚定 + continuous shot | ★★ |

## QA 追加项

- [ ] 场景护照段存在，关键物体左右位置已声明
- [ ] 每段时间戳里关键物体位置至少出现一次
- [ ] 涉及跨段状态（道具/姿态/损伤）时用了链式尾帧→首帧
- [ ] 高难物理交互写了轨迹拆解
- [ ] 每段动作 ≤ 2-3 个实体动作