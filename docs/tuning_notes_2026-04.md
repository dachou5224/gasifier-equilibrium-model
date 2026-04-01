# 调参与验证记录（2026-04）

## 目的
本文档用于沉淀本轮 `gasifier-model` 调参与验证工作，避免后续重复摸索。

## 本轮已落地的关键改动
- 在 `gasifier.py` 中引入 `effective_split_v2`，将总热损拆分为：
  - `PhysicalHeatLossPercent`
  - `ModelCorrectionPercent`
- 明确允许 split 模式下出现负的 `ModelCorrectionPercent`，用于表达“模型修正项”而非真实负热损
- 将 `CarbonConversion`、`DeltaT_WGS`、`DeltaT_Meth` 改为支持分组默认模式
- 引入 `char extent` / `residual carbon` 的显式状态与结果输出
- 增加 `CharExtentMode="correlation_v2"`，作为温和经验相关式
- 在验证流程中新增逐案 `char extent` 候选搜索，并与其它校准策略逐案比优
- 将验证流程的共享逻辑抽取到 `scripts/validation_profile.py`

## 当前推荐 profile
推荐使用：
- `SolverMethod = "Stoic"`
- `HeatLossMode = "effective_split_v2"`
- `CarbonConversionMode = "grouped_default_v1"`
- `DeltaTMode = "grouped_default_v2"`
- `CharExtentMode = "correlation_v2"`

如需运行完整 19 案：
```bash
python3 scripts/audit_validation_cases.py --profile tuned-19cases --output generated/validation/validation_results.json
```

## 当前 19 案表现
基于 `tests/validation_results.json`：
- `avg_comp_mae = 2.844019352505436`
- `avg_temp_abs_error_C = 9.929722500601201e-05`
- `avg_final_warnings = 0.0`
- `avg_candidate_failures = 0.0`

## 当前最差案例
按 `comp_mae` 排序，当前主要瓶颈仍集中在工业浆态与部分 pilot dry：
1. `Industrial-Slurry-fed-Illinois_No6`：`5.6410`
2. `Industrial-Slurry-fed-Australia_UBE`：`5.3389`
3. `Pilot-Dry-fed-Texaco_I-1`：`3.6286`
4. `Industrial-Slurry-fed-Fluid_Coke`：`2.9357`
5. `Industrial-Slurry-fed-LuNan_Texaco`：`2.8855`
6. `Pilot-Dry-fed-Texaco_I-2`：`2.8195`

## 已验证有效的经验
- 小试装置真实热损通常高于工业装置，这一规律已体现在 `effective_split_v2`
- 仅靠统一热损难以同时压低所有 worst cases
- `O/C` 优先校准对有目标温度的个别案例有效，但不能直接全局替代其它策略
- 把 `char extent` 作为逐案候选标量搜索，能在不破坏收敛性的前提下继续降低全局 `avg_comp_mae`
- 扩展反应网络（Boudouard / Steam gasification）当前实现仍偏实验性，暂不宜作为默认主线路

## 当前目录约定
- 规范验证结果目录：`generated/validation/`
- 参数扫描结果目录：`generated/equilibrium_scans/`
- 已跟踪验证快照：`tests/validation_results.json`
- 历史遗留结果：根目录 `validation_results.json`

## 后续建议
- 若继续优化，优先只盯最差的工业浆态案例，而不是继续增加全局复杂度
- 若要进一步“工程化”，下一步应考虑把验证 profile 正式做成可复用配置对象，而非继续堆叠脚本参数
