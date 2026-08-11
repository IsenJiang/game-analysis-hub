# ⚔️ [游戏名称] 核心战斗与操作手感 (Game Feel) 深度拆解

> **分析维度**：Moment-to-Moment Gameplay / Combat Loop / Input & Feedback
> **标的/竞品**：[标的 A] vs [标的 B]

---

## 1. 核心战斗循环 (The Moment-to-Moment Loop)

```mermaid
graph LR
    A[观察与预判 (Read)] --> B[输入与决策 (Input)]
    B --> C[视觉/音效反馈 (Impact)]
    C --> D[环境/数值状态改变 (Result)]
    D --> A
