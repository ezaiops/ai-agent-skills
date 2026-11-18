# 运镜词库（Camera Lexicon）

## 铁则

- 运镜必须有**物理动机**的动词（dive, slingshot, whip, dart, orbit, push-in），不要写 "dynamic camera / camera moves dynamically" 这类空泛词——模型不知道该干嘛。
- **Continuous Shot Lock**：段首声明 `single continuous shot`，强制时间一致性，减少插值伪影。
- **Environmental Anchoring**：场景中散布静态参考几何（墙、柱、拱门、山崖、悬垂物），让模型有稳定背景做视差——用背景掠过体现速度，而不是让主体糊掉。

## 基础运镜（中英对照）

| 英文写法（直接入 prompt） | 说明 |
|---|---|
| slow push-in / dolly in | 推镜头，向主体靠近 |
| pull back / dolly out | 拉镜头，远离主体，揭示环境 |
| pan left / pan right | 摇镜头，水平旋转 |
| tilt up / tilt down | 俯仰摇，垂直旋转 |
| tracking shot / follow shot | 跟拍，镜头随主体移动 |
| orbit / circular dolly | 环绕镜头，绕主体旋转 |
| one continuous take | 一镜到底，全程无剪辑 |
| handheld shot with subtle shake | 手持纪实质感，微微抖动 |

## 高级运镜

| 英文写法 | 说明 |
|---|---|
| Hitchcock zoom / dolly zoom | 希区柯克变焦（推拉+变焦的眩晕） |
| fisheye lens | 鱼眼超广角畸变 |
| low-angle hero shot | 低角度仰拍，增加英雄感 |
| bird's-eye / overhead shot | 俯拍/鸟瞰 |
| POV / first-person shot | 第一人称主观视角 |
| whip pan | 极速水平旋转产生运动模糊 |
| crane / jib shot | 机械臂升降，多角度跟随视线 |
| Dutch angle | 倾斜机位（紧张感；负向里常禁） |

## 景别（Shot Size）

| 英文写法 | 说明 |
|---|---|
| extreme close-up | 极致特写（眼睛、嘴、刀刃） |
| close-up | 面部特写 |
| medium close-up | 中近景（头肩） |
| medium shot | 中景（腰部以上） |
| full shot / wide shot | 全景（完整人物） |
| establishing shot / extreme wide | 远景/建立镜头（完整环境） |

## 运镜-动作匹配（爆发段贴身，余韵段缓推）

- 蓄力段：slow orbit / push-in，制造张力。
- 爆发段：whip pan 跟动作、手持震动贴身跟拍、动作瞬间 dolly-in。
- 余韵段：slow pull-back 定帧收尾。
- 命中瞬间：`0.2-0.3s micro slow-motion, then back to real time`（每段最多一次）。