# Entrained Flow Gasifier Equilibrium Model
# 气流床气化炉平衡模型

本项目用于气流床煤气化炉的热力学平衡计算，支持 `RGibbs` 与 `Stoic` 两类求解路径，并提供 19 个文献案例的批量验证、参数扫描、结果审计与简单 UI 入口。

## 项目现状
当前验证主 profile 为 `tuned-19cases`，核心特点包括：
- `Stoic` 求解器作为 19 案默认验证器
- `effective_split_v2`：将总热损拆为真实热损与模型修正项
- `grouped_default_v1` / `grouped_default_v2`：分组式 `CarbonConversion` 与 `DeltaT`
- `correlation_v2` + 逐案 `char extent` 候选搜索
- 对有目标温度案例执行 `heat_loss_only`、`oc_first_then_heat_loss` 与 `char_extent_search_*` 候选择优

最新 19 案汇总结果见 `tests/validation_results.json`，当前摘要为：
- `avg_comp_mae = 2.8440`
- `avg_temp_abs_error_C = 9.93e-05`
- `avg_final_warnings = 0.0`
- `avg_candidate_failures = 0.0`

## 目录结构
```text
gasifier-model/
├── src/gasifier/                # 核心模型与物性/热力学/求解器
├── scripts/                     # 审计、扫描、打印与辅助脚本
├── tests/                       # pytest 与回归快照
├── generated/                   # 生成结果与扫描产物
│   ├── validation/              # 验证结果的规范落盘目录
│   └── equilibrium_scans/       # 参数扫描结果
├── docs/                        # 面向后续维护的说明文档
├── gasifier_ui.py               # 现行 Streamlit UI 入口
├── main_gui.py                  # 历史 Tk 入口，保留作 legacy 参考
└── path_utils.py                # 早期路径辅助，保留作 legacy 参考
```

## 核心文件
- `src/gasifier/gasifier.py`：主模型、输入预处理、热损拆分、char state 与求解调度
- `src/gasifier/stoic_solver.py`：Stoic 平衡方程与扩展反应集
- `src/gasifier/thermo_data.py`：Shomate 热力学数据与标准态性质
- `scripts/validation_profile.py`：当前 19 案的共享 profile 与候选选择逻辑
- `scripts/audit_validation_cases.py`：批量审计并输出综合结果 JSON
- `scripts/print_validation_table.py`：打印精简验证表
- `tests/test_tuning_modes.py`：调参模式与 profile 相关测试

## 常用命令
启动 UI：
```bash
streamlit run gasifier_ui.py
```

作为 `chem_portal` 子页面调试：
```bash
# 目录需与 chem_portal 平级
cd ../chem_portal
streamlit run app.py
```

运行调参模式测试：
```bash
python3 -m pytest tests/test_tuning_modes.py
```

运行 19 案审计：
```bash
python3 scripts/audit_validation_cases.py --profile tuned-19cases --output generated/validation/validation_results.json
```

打印验证表：
```bash
python3 scripts/print_validation_table.py
```

扫描平衡参数：
```bash
python3 scripts/scan_equilibrium_parameters.py
```

## 维护说明
- 规范验证结果应优先写入 `generated/validation/`
- `tests/validation_results.json` 当前保留为已跟踪快照，便于直接比较
- 根目录 `validation_results.json` 属于历史遗留产物，后续不建议继续作为主输出
- `main_gui.py` 与 `path_utils.py` 暂未删除，是为了避免误伤历史工作流
- `gasifier_ui.py` 当前默认读取 `generated/validation_cases_from_kinetic.json` 与 `generated/validation/validation_results.json`
- `chem_portal` 通过 `pages/3_Gasifier_Model.py` 动态导入 `gasifier_ui.run()`
- 本仓库已提供 `.github/workflows/deploy-to-vps.yml`，当 `main` 更新时会拉取 `gasifier-model` 并重建 `chem_portal`，从而自动刷新门户里的该子页面

## 进一步说明
- 当前调参与目录整理说明：`docs/tuning_notes_2026-04.md`
- 当前结构与整理建议：`docs/project_layout.md`
- 与 `chem_portal` 的接入/自动部署说明：`docs/chem_portal_integration.md`

## 许可证
本项目仅用于研究和教育目的。