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

## 验证

本项目已通过以下文献的热力学模拟结果验证：

1. Ma Z, Jiang Y, Ding T, et al. Elucidating the behaviours and mechanisms of enforced carbonation in ferrite. *Cement and Concrete Research*, 2025, 195: 107916. [DOI: 10.1016/j.cemconres.2025.107916](https://doi.org/10.1016/j.cemconres.2025.107916)
2. Kim N, Seo J, Jang J G, et al. Thermodynamic modeling of carbonated Portland cement under groundwater and seawater conditions. *Cement and Concrete Composites*, 2025, 162: 106141. [DOI: 10.1016/j.cemconcomp.2025.106141](https://doi.org/10.1016/j.cemconcomp.2025.106141)
3. Gao W, Zhao M, Li C, et al. Synergistic mechanisms of multiple components in lithium slag-based low-carbon cement: Multi-scale insights from thermodynamic modeling to hydration-driven microstructural evolution. *Cement and Concrete Composites*, 2026, 162: 106508. [DOI: 10.1016/j.cemconcomp.2026.106508](https://doi.org/10.1016/j.cemconcomp.2026.106508)
4. Pang L, Sun J, Provis J L, et al. Thermodynamic simulation-assisted design of the electrolytic manganese residue-slag-Ca(OH)₂ cementitious system. *Cement and Concrete Research*, 2025. [DOI: 10.1016/j.cemconres.2025.108119](https://doi.org/10.1016/j.cemconres.2025.108119)


## 相关资源

- xGEMS 源码: https://bitbucket.org/gems4/xgems
- xGEMS Jupyter 示例: https://github.com/gemshub/xgems-jupyter
- GEM-Selektor 文档: https://gemshub.github.io/start/gemselektor/documentation/
