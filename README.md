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
| **Heat Loss Tuning** | 热损自校准 | Auto-tune Heat Loss to match Target T | 自动反算热损以匹配目标温度 |
| **Diagnostic** | 智能诊断 | Check physical validity | 负热损警告、氧煤比建议 |
| **RGibbs Solver** | RGibbs求解器 | scipy.optimize with SLSQP | scipy.optimize配合SLSQP方法 |
| **Thermodynamics** | 热力学 | NIST Shomate equations | NIST Shomate方程（高/低温切换） |
| **Coal Utilities** | 煤质工具 | NICE1 & SIMTECH algorithms | NICE1热值估算、SIMTECH生成焓计算 |

---

## 2. File Structure | 文件结构

```text
gasifier-model/
├── src/
│   └── gasifier/          # Core model logic (Package)
│       ├── gasifier.py    # Physics engine & Diagnostics
│       ├── coal_props.py  # Coal properties & Unit conversion
│       └── thermo_data.py # Thermodynamic database
├── tests/                 # Validation tests
│   ├── test_validation.py # Validation script
│   └── validation_cases.py# Literature cases
├── debug_tools/           # Debugging scripts
├── gasifier_ui.py         # Streamlit Web App Entry
└── validation_results.json# Test results
```

---

## 3. Recent Modifications | 最近修改 (2026-01)

### 3.1 Physics & Units | 物理引擎与单位修复
> **Fix**: Standardized all internal energy units to **Joules (J)** and **Moles (mol)**. Fixed a 1000x scaling error in gas enthalpy.
> **Fix**: Corrected coal formation enthalpy mixing units (kJ vs J).

### 3.2 Auto-Calibration | 自动校准
> **Feature**: Added `calibrate_heat_loss` method.
> **Feature**: Added safety checks for negative heat loss (forcing to 0% and suggesting O/C ratio adjustment).

### 3.3 Project Structure | 项目重构
> **Refactor**: Moved core logic to `src/gasifier` for better packaging.
> **Integration**: Updated `gasifier_ui.py` to auto-detect source paths for seamless Docker integration in Chem Portal.

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
# 提示: gasifier_ui.py 会自动添加 src/ 目录到路径，无需额外配置 PYTHONPATH
```

### Method 2: Validation | 方法2：运行验证
```bash
python tests/test_validation.py
```

### Method 3: Module Import | 方法3：模块导入
```python
import sys
import os
sys.path.append("/path/to/gasifier-model/src")

from gasifier.gasifier import GasifierModel
# ...
```

---

## 5. Validation | 验证案例

| Case 案例 | Description 描述 | Target T (°C) | Error (°C) |
|-----------|------------------|---------------|------------|
| Paper_Case_6 | Base Case | 1370 | ~0.9 |
| Paper_Case_1 | Variation 1 | 1333 | ~1.8 |
| Paper_Case_2 | Variation 2 | 1452 | ~1.6 |

---

## 6. License | 许可证

This project is for research and educational purposes.

本项目仅用于研究和教育目的。

---

*Last Updated 最后更新: 2026-01-30*