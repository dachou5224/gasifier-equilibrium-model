# Entrained Flow Gasifier Equilibrium Model (EFG-EM)
# 气流床气化炉平衡模型

---

## 1. Project Overview | 项目概述

This project implements a comprehensive **thermodynamic equilibrium model** for entrained flow coal gasifiers (e.g., GE/Texaco, Shell). It predicts reactor performance, syngas composition, and quench outlet conditions based on coal properties and operating parameters.

本项目实现了一个完整的**热力学平衡模型**，用于气流床煤气化炉（如GE/Texaco、Shell炉型）。基于煤质特性和操作参数，预测反应器性能、合成气组成和激冷出口条件。

### Key Features | 主要功能

| Feature | 功能 | Description | 描述 |
|---------|------|-------------|------|
| **Web UI** | Web界面 | Streamlit dashboard with charts | Streamlit交互式仪表盘（已集成至Chem Portal） |
| **Solver Strategy** | 求解策略 | **RGibbs** (Global Energy Min) or **Stoichiometric** (Temp Approach) | 可选吉布斯最小化或温差模型 |
| **Heat Loss Tuning** | 热损自校准 | Auto-tune Heat Loss to match Target T | 自动反算热损以匹配目标温度 |
| **Diagnostic** | 智能诊断 | Check physical validity | 负热损警告、氧煤比建议 |
| **Thermodynamics** | 热力学 | NIST Shomate equations | NIST Shomate方程（已修正高温H2系数） |

---

## 2. File Structure | 文件结构

```text
gasifier-model/
├── src/
│   └── gasifier/          # Core model logic (Package)
│       ├── gasifier.py    # Physics engine & Main Interface
│       ├── stoic_solver.py# Stoichiometric Solver (Temperature Approach)
│       ├── coal_props.py  # Coal properties & Unit conversion
│       ├── thermo_data.py # Thermodynamic database
│       └── validation_cases.py # Literature cases
├── tests/                 # Validation tests
│   ├── test_validation.py # Validation script
│   └── test_stoic.py      # Stoic solver test
├── debug_tools/           # Debugging scripts
├── gasifier_ui.py         # Streamlit Web App Entry
└── validation_results.json# Test results
```

---

## 3. Algorithm Details | 算法详解

### 3.1 RGibbs Solver (Non-Stoichiometric)
*   **Principle**: Minimizes total Gibbs Free Energy of the system ($G_{total} = \sum n_i \mu_i$).
*   **Pros**: General purpose, no need to specify reaction pathways.
*   **Cons**: Can be sensitive to initial guess and thermodynamic data accuracy.

### 3.2 Temperature Approach Solver (Stoichiometric)
*   **Principle**: Solves a system of non-linear equations based on element balances and equilibrium constants ($K_{eq}$).
*   **Features**:
    *   **Temperature Approach ($\Delta T$)**: Allows specifying a temperature deviation for key reactions (WGS, Methanation) to mimic non-equilibrium conditions ($K_{eq}$ calculated at $T + \Delta T$).
    *   **Robustness**: Often more stable for specific gasifier configurations.

---

## 4. Recent Modifications | 最近修改 (2026-01)

### 4.1 Physics & Units | 物理引擎与单位修复
> **Fix**: Standardized all internal energy units to **Joules (J)** and **Moles (mol)**. 
> **Critical Fix**: Corrected **H2 Shomate coefficients** for high temperature (1000-2500K), resolving incorrect methanation predictions.

### 4.2 Parameter Optimization | 参数调优
> **Update**: Adjusted default **Oxygen/Coal Ratio (O/C)** from 0.86 to **1.05** to match literature validation temperatures (~1370°C).

### 4.3 New Features | 新功能
> **Feature**: Added **Stoichiometric Solver** with Temperature Approach parameters.
> **Feature**: Added **Solver Settings** in UI to switch between RGibbs and Stoic methods.

### 4.4 Equilibrium Solver Overhaul & Debugging | 平衡求解器重构与调试 (2026-03)
> **Debug**: 移除了原先强制设定的 `co2_min` 和 `h2_min` 非物理硬约束，解放了 Gibbs 能量最小化的寻优空间。
> **Update**: 将 Gibbs 优化算法从收敛受限的 `SLSQP` 升级为 `trust-constr` 内点法，不仅提高了稳定性，并扩充了 `typical, reducing, oxidizing, stoic_based` 等多种初值探索策略。
> **Update**: 通过利用对数标度（log-scale），改进了 `stoic_solver.py` 中甲烷化方程在高温下的强数值跨度阻碍，消散了非物理的高温不收敛。
> **Result**: 成功将高温下的非物理组分预测（如极高的 CO2）修正回物理真实的平衡态，并彻底排除了越界等求解假报警。

---

## 5. Installation & Usage | 安装与使用

### Method 1: Web App | 方法1：Web应用（推荐）
```bash
streamlit run gasifier_ui.py
```

### Method 2: Validation | 方法2：运行验证
```bash
python tests/test_validation.py
```

---

## 6. License | 许可证

This project is for research and educational purposes.

本项目仅用于研究和教育目的。

---

*Last Updated 最后更新: 2026-01-30 v2.2*