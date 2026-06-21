# GEMS CLI

> 封装 xGEMS 库的热力学模拟 CLI 工具和 MCP Server，供 AI Agent 和研究者调用。

## 项目结构

```
gemscli/
├── gems_cli/                    # Python 包
│   ├── engine.py                # GemsEngine 核心封装 + GemsExplorer
│   ├── cli.py                   # CLI 入口 (gems-cli)
│   ├── mcp_server.py            # MCP Server (gems-mcp)，4 个工具
│   ├── utils.py                 # 单位转换、路径解析
│   └── templates/               # JSON 模拟模板
├── data/systems/                # 7 个预导出的 GEMS3K 热力学系统
├── examples/                    # 使用示例 + 论文复现脚本
├── docs/                        # 技术文档
├── GEMS3.11.2/                  # GEM-Selektor 分发包（二进制 + 数据库）
└── pyproject.toml
```

## 快速开始

### 1. 安装依赖

```bash
conda config --add channels conda-forge
conda create -n gems python=3.11 -y
conda activate gems
conda install xgems -y
pip install mcp                    # MCP Server 依赖
pip install -e .                   # 开发模式安装
```

### 2. 使用 CLI

```bash
# 列出可用系统
gems-cli --list-systems

# 查看系统元数据
gems-cli --system-info calcite

# 运行平衡计算（内联参数）
gems-cli --system calcite --T 25 --P 1 \
  --bulk-composition '{"Ca":0.01,"C":0.01,"H":111,"O":55.5}'

# 运行平衡计算（JSON 文件）
gems-cli --input gems_cli/templates/aragonite_calcite.json
```

### 3. 启动 MCP Server

```bash
gems-mcp                                    # stdio 模式（默认）
gems-mcp --transport sse --port 8765        # SSE 模式
```

## 可用系统

| 系统 | 元素 | 相 | 说明 |
|------|------|-----|------|
| `calcite` | 10 | 13 | Ca-C-O-H 地球化学，文石/方解石平衡 |
| `cement_hydration` | 24 | 110 | 完整水泥水化（C-S-H, CH, AFt, AFm 等） |
| `iron_redox` | 7 | 4 | Fe²⁺/Fe³⁺ 氧化还原体系 |
| `exchange_sorption` | 8 | 7 | 铀在粘土矿物上的离子交换吸附 |
| `PC_leaching` | 13 | 84 | 硅酸盐水泥浸出 |
| `mortar_dissolution` | 13 | 81 | 砂浆骨料溶解 |
| `ferrite_carbonation` | 8 | ~30 | C4AF 铁铝酸盐强制碳化（从 PC_leaching 精简） |

## 文档

- [技术文档](docs/TECHNICAL_DOC.md) — 架构、API、使用方式的完整参考
- [故障排查](docs/troubleshooting.md) — 常见问题与解决方案
- [输出格式规范](docs/output-schema.md) — CLI/MCP 输出 JSON 结构
- [输入模板格式](docs/template-format.md) — JSON 输入模板说明
- [API 覆盖率计划](docs/gemscli-api-coverage-plan.md) — 功能差距分析与改进路线图
- [可行性分析](docs/01-feasibility-analysis.md) — 开发前技术评估（历史文档）

## 相关资源

- xGEMS 源码: https://bitbucket.org/gems4/xgems
- xGEMS Jupyter 示例: https://github.com/gemshub/xgems-jupyter
- GEM-Selektor 文档: https://gemshub.github.io/start/gemselektor/documentation/
