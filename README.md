# Entrained Flow Gasifier Equilibrium Model (EFG-EM)
# 气流床气化炉平衡模型

---

## 1. Project Overview | 项目概述

This project implements a comprehensive **thermodynamic equilibrium model** for entrained flow coal gasifiers (e.g., GE/Texaco, Shell). It predicts reactor performance, syngas composition, and quench outlet conditions based on coal properties and operating parameters.

本项目实现了一个完整的**热力学平衡模型**，用于气流床煤气化炉（如GE/Texaco、Shell炉型）。基于煤质特性和操作参数，预测反应器性能、合成气组成和激冷出口条件。

The core algorithm uses **Gibbs Free Energy Minimization** (RGibbs) with mechanism constraints to handle high-pressure methanation issues.

核心算法采用**吉布斯自由能最小化**（RGibbs）方法，并结合机理约束处理高压甲烷化问题。

### Key Features | 主要功能

| Feature | 功能 | Description | 描述 |
|---------|------|-------------|------|
| **Web UI** | Web界面 | Streamlit dashboard with charts | Streamlit交互式仪表盘（已集成至Chem Portal） |
| **Desktop UI** | 桌面界面 | Tkinter lightweight interface | Tkinter轻量化界面 |
| **RGibbs Solver** | RGibbs求解器 | scipy.optimize with SLSQP | scipy.optimize配合SLSQP方法 |
| **Thermodynamics** | 热力学 | NIST Shomate equations | NIST Shomate方程（高/低温切换） |
| **Quench Model** | 激冷模型 | Antoine saturation calculation | Antoine方程饱和度计算 |
| **Coal Utilities** | 煤质工具 | NICE1 & SIMTECH algorithms | NICE1热值估算、SIMTECH生成焓计算 |
| **Smart Calibration** | 智能校正 | Auto-tune Heat Loss or O/C | 自动反算热损或氧煤比 |
| **Diagnostics** | 诊断系统 | Convergence & balance checks | 收敛警告、质量平衡检查（新增） |

---

## 2. File Structure | 文件结构

| File 文件 | Description 描述 |
|-----------|------------------|
| `gasifier_ui.py` | **[推荐]** Streamlit Web应用（集成至Chem Portal） |
| `gasifier.py` | 物理引擎（Gibbs求解器、能量平衡、激冷逻辑、**诊断系统**） |
| `coal_props.py` | 煤质计算与数据库（**含单位自动转换**） |
| `thermo_data.py` | 热力学数据库（NIST Shomate系数） |
| `validation_cases.py` | 文献验证数据集 |
| `main_gui.py` | Tkinter桌面GUI |

---

## 3. Recent Modifications | 最近修改 (2026-01)

### 3.1 UI Refactoring | UI重构: `app.py` → `gasifier_ui.py`

> **Summary 摘要**: Streamlit UI已重构，集成至 **Chem Portal** 框架。

| Change 修改 | 说明 |
|-------------|------|
| Rename | 从 `app.py` 重命名为 `gasifier_ui.py` |
| Layout | 从 Sidebar 改为**双列布局** |
| API | 封装 `run()` 函数支持外部调用 |

### 3.2 Physics Engine | 物理引擎增强: `gasifier.py`

> **Summary 摘要**: 新增多起点优化、物理边界约束、诊断系统。

| Fix/Feature | 修改内容 |
|-------------|----------|
| Fix 1 | 消除全局变量 `T_calc_global`，温度作为参数传递 |
| Fix 5 | 根据O/C比动态调整温度搜索区间 |
| Fix 6 | 多起点优化策略（reducing/balanced/oxidizing） |
| Fix 7 | 物理结果校验 `_validate_physical_results` |
| New | 诊断系统 `diagnostics` 追踪收敛警告/质量平衡/约束违反 |
| New | H2物理下限约束，防止H2归零 |

### 3.3 Unit Handling | 单位处理: `coal_props.py`

> **Summary 摘要**: 修复HHV单位不一致问题，自动检测与转换。

| Change 修改 | 说明 |
|-------------|------|
| Auto-detect | 输入值 <1000 识别为 MJ/kg，自动转换为 kJ/kg |
| Database | 数据库统一使用 kJ/kg |
| Unit test | 新增 `test_hhv_units()` 验证函数 |

---

## 4. Installation & Usage | 安装与使用

### Prerequisites | 环境要求
* Python 3.8+
* Required libraries | 依赖库:
    ```bash
    pip install numpy scipy pandas streamlit plotly
    ```

### Method 1: Web App | 方法1：Web应用（推荐）
```bash
streamlit run gasifier_ui.py
```

### Method 2: Desktop GUI | 方法2：桌面应用
```bash
python main_gui.py
```

### Method 3: Module Import | 方法3：模块导入
```python
from gasifier_ui import run        # UI函数
from gasifier import GasifierModel # 核心模型
```

---

## 5. Validation | 验证案例

| Case 案例 | Description 描述 | Target T (°C) |
|-----------|------------------|---------------|
| Paper_Case_6 (Calibrated) | 基准工况（校正热损） | 1370 |
| Paper_Case_6 (Base) | 基准工况（标准条件） | 1370 |
| Paper_Case_1 | 变化工况1（不同O/C） | 1333 |
| Paper_Case_2 | 变化工况2（高O/C和S/C） | 1452 |

---

## 6. License | 许可证

This project is for research and educational purposes.

本项目仅用于研究和教育目的。

---

*Last Updated 最后更新: 2026-01-29*