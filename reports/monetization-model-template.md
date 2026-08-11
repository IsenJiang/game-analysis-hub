# ⚔️ [游戏名称] 核心战斗与操作手感 (Game Feel) 深度拆解

> **分析维度**：Moment-to-Moment Gameplay / Hitstop & Camera / Skill Floor vs. Ceiling
> **标的/竞品**：[标的 A] vs [标的 B]  |  **分析人**：Your Name

---

## 1. 核心战斗微循环 (Moment-to-Moment Micro Loop)

```mermaid
graph LR
    A[信息输入: 敌方前摇/环境/音效] -->|决策判断 < 200ms| B[按键输入: 帧窗口/指令预输入]
    B -->|物理与动画反馈| C[打击打击感: Hitstop/震动/特效]
    C -->|状态改变| D[数值/姿态/硬直硬直削减]
    D --> A
