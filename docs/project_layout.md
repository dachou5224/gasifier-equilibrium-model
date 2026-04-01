# 项目结构与整理说明

## 当前建议结构
```text
gasifier-model/
├── src/gasifier/                # 核心模型代码
├── scripts/                     # 运行脚本
├── tests/                       # pytest 与验证快照
├── generated/
│   ├── validation/              # 规范验证结果输出
│   └── equilibrium_scans/       # 参数扫描输出
├── docs/                        # 维护文档
├── gasifier_ui.py               # 当前 UI 主入口
├── main_gui.py                  # 历史 GUI 入口
└── path_utils.py                # 历史路径辅助
```

## 本次整理原则
- 不移动核心求解包 `src/gasifier/`
- 不删除历史入口，先在文档中明确 `legacy` 身份
- 将“未来应该写到哪里”先定清楚，再逐步迁移旧产物
- 优先让脚本默认输出落到规范目录，避免继续制造散落文件

## 已识别的历史遗留
- `main_gui.py`
  - 仍使用旧导入方式
  - 暂保留，仅作为历史参考
- `path_utils.py`
  - 目前未形成统一入口，属于早期路径辅助文件
- 根目录 `validation_results.json`
  - 为历史验证结果产物，不再建议作为主输出位置
- `debug_tools/`
  - 目前仍是独立目录，后续可视情况并入 `scripts/debug/`
  - 本次未移动，避免破坏内部路径假设

## 结果文件约定
- `generated/validation/validation_results.json`
  - 推荐作为当前批量验证主输出
- `generated/validation/*.json`
  - 其它验证类输出
- `generated/equilibrium_scans/*.json`
  - 平衡参数扫描输出
- `tests/validation_results.json`
  - 保留为当前已跟踪快照，方便直接查看和比较

## 建议但尚未执行的进一步整理
- 将 `main_gui.py` 移入 `legacy/`
- 将 `path_utils.py` 移入 `legacy/`
- 将 `debug_tools/` 并入 `scripts/debug/`
- 将 `generated/` 下历史 `tmp_*.json` 收到单独归档目录
