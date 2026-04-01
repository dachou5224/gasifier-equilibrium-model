# gasifier-model 与 Chem Portal 集成说明

## 目标
本项目不是独立部署为单独 Web 服务，而是作为 `chem_portal` 的外挂子模块接入。  
门户页通过动态导入本仓库根目录下的 `gasifier_ui.py`，并调用其中的 `run()`。

## 当前接入方式

### 1. 页面桥接
`chem_portal` 中的桥接页是：
- `chem_portal/pages/3_Gasifier_Model.py`

其逻辑是：
- 在 Docker 中优先查找 `/app/modules/gasifier`
- 本地开发时回退到与 `chem_portal` 平级的 `../gasifier-model`
- 将该目录加入 `sys.path`
- 导入 `gasifier_ui`
- 执行 `gasifier_ui.run()`

因此，本仓库对门户的最核心接口约定只有一个：
- `gasifier_ui.py` 必须存在
- `gasifier_ui.py` 必须暴露 `run()`

### 2. Docker 挂载
`chem_portal/docker-compose.yml` 中通过 volume 将本仓库挂入容器：

```yaml
- ../gasifier-model:/app/modules/gasifier
```

这意味着 VPS 或本地开发机上，两个仓库需要是平级目录：

```text
parent_dir/
├── chem_portal/
└── gasifier-model/
```

在线上默认约定为：

```text
/root/
├── chem_portal/
└── gasifier-model/
```

## UI 与验证主线的关系
当前 `gasifier_ui.py` 已经对齐本仓库最近的验证/调参主线：
- 默认 profile：`tuned-19cases`
- 数据源：`generated/validation_cases_from_kinetic.json`
- 验证快照：`generated/validation/validation_results.json`（若不存在则回退到 `tests/validation_results.json`）
- 页面支持展示：
  - 当前推荐 profile
  - 19 案验证总览
  - 当前工况自动候选策略结果
  - 最近审计快照中的该案例表现

## 自动更新链路

### 路径 A：chem_portal 仓库触发部署
`chem_portal/.github/workflows/deploy.yml` 会：
- SSH 到 VPS
- 更新多个平级仓库
- 对 `gasifier-model` 与 `gasifier-1d-kinetic` 做严格 `checkout main + pull --ff-only`
- 重建 `chem_portal` 容器

因此当 `chem_portal` 自己更新时，也会顺带刷新本子页面。

### 路径 B：gasifier-model 仓库触发部署
本仓库新增了：
- `.github/workflows/deploy-to-vps.yml`

该 workflow 会在 `main` 更新时：
1. SSH 到 VPS
2. 更新 `gasifier-model`
3. 进入 `chem_portal`
4. 执行 `docker compose up -d --build`

因此当本仓库自身更新时，也能主动触发门户刷新。

## 需要配置的 GitHub Secrets

本仓库 `deploy-to-vps.yml` 需要以下 Secrets：

### 必填
- `VPS_HOST`
  - VPS 公网 IP 或域名
- `VPS_USER`
  - SSH 用户名
- `VPS_KEY`
  - SSH 私钥全文（PEM）

### 可选
- `VPS_REPO_PATH`
  - 默认 `/root/gasifier-model`
- `VPS_DEPLOY_ROOT`
  - 默认 `/root`
  - workflow 会据此推导 `chem_portal` 路径为 `${VPS_DEPLOY_ROOT}/chem_portal`

## 目录假设
当前 workflow / deploy 脚本的默认目录假设是：

```text
/root/
├── chem_portal/
├── gasifier-model/
├── gasifier-1d-kinetic/
├── reh_app/
├── mto-ai-apps/
└── pid-loop-simulator/
```

如果你的 VPS 不采用 `/root` 作为平级父目录，请至少配置：
- `VPS_REPO_PATH`
- `VPS_DEPLOY_ROOT`

注意：
- `gasifier-model` 自己的 workflow 已支持这两个可选参数
- `chem_portal` 当前 workflow 仍更偏向 `/root` 约定

## 本地开发建议

### 直接跑本仓库 UI
```bash
cd gasifier-model
streamlit run gasifier_ui.py
```

### 以门户方式联调
```bash
cd ../chem_portal
streamlit run app.py
```

如果在本地联调时出现：
- `ModuleNotFoundError: plotly`

这通常表示当前 Python 环境没装齐 portal/UI 依赖，而不是桥接逻辑有问题。

## 故障排查
- 页面提示找不到模块路径：
  - 检查 `chem_portal` 与 `gasifier-model` 是否平级
- 页面提示 `gasifier_ui.py` 导入失败：
  - 检查本地/容器里是否安装了 `streamlit`、`plotly`、`pandas`、`numpy`、`scipy`
- 页面提示 `run()` 不存在：
  - 检查 `gasifier_ui.py` 是否仍保留 `run()` 入口
- 本仓库 push 后门户未刷新：
  - 检查本仓库 Actions 中的 `VPS_HOST` / `VPS_USER` / `VPS_KEY`
  - 检查 VPS 上 `chem_portal` 路径是否符合 `${VPS_DEPLOY_ROOT}/chem_portal`
