# eastmoney-mx-finance-mcp-server

基于 [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) 及东方财富·妙想（MX）API 实现的金融 MCP 服务端，为 AI Agent 提供资讯检索、金融数据查询、选股、自选管理及模拟交易等能力。

## 项目亮点

- **功能全面**：封装东方财富·妙想的资讯搜索、金融查数、智能选股、自选股管理及模拟交易等核心能力
- **统一响应结构**：所有接口返回标准化的 `endpoint`、`request`、`response`、`success_hint`、`error_hint` 字段，便于 Agent 进行后处理
- **智能辅助工具**：内置金额厘转元、价格精度还原等工具，简化数据处理流程
- **健壮的错误处理**：对上游 HTTP 异常、网络错误、非 JSON 响应等进行结构化封装，减少工具直接抛错

## 能力清单

| 工具函数 | 功能说明 |
|---------|---------|
| `mx_search(query)` | 资讯搜索（新闻/公告/研报/政策解读） |
| `mx_data(toolQuery)` | 金融数据查询（行情/资金/财务/高管等） |
| `mx_select_stock(keyword, pageNo=1, pageSize=20)` | 智能选股（自然语言描述选股条件） |
| `mx_selfselect_get()` | 查询自选股列表 |
| `mx_selfselect_manage(query)` | 添加/删除自选股 |
| `mx_stock_simulator_balance()` | 模拟账户资金查询 |
| `mx_stock_simulator_positions()` | 模拟账户持仓查询 |
| `mx_stock_simulator_trade(type, stockCode, quantity, useMarketPrice=False, price=None)` | 买卖委托下单 |
| `mx_stock_simulator_cancel(orderNo=None, cancelAll=False)` | 撤单（支持单笔/全部） |
| `mx_stock_simulator_orders(pageNo=1, pageSize=20, includeHistory=False)` | 委托/成交记录查询 |
| `mx_stock_simulator_summary()` | 资金+持仓汇总（自动厘转元，含前5大持仓） |
| `mx_amount_li_to_yuan(amount_li)` | 金额单位换算（厘→元，1元=1000厘） |
| `mx_price_restore(price, priceDec)` | 价格还原（`真实价格 = price / 10^priceDec`） |

## 1. 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

如果是在代理受限或离线环境中安装，可尝试：

```bash
pip install -e . --no-build-isolation
```

## 2. 配置环境变量

至少需要配置 `MX_APIKEY`（从[妙想平台](https://clawhub.ai/u/QQK000)获取）：

```powershell
# 必需：API 密钥
$env:MX_APIKEY="你的 apikey"

# 可选：MX API 地址（默认已配置，可不设置）
$env:MX_API_URL="https://mkapi2.dfcfs.com/finskillshub/api/claw"

# 可选：MCP 服务监听配置
$env:MCP_HOST="127.0.0.1"          # 监听地址
$env:MCP_PORT="8000"               # 监听端口
$env:MCP_MOUNT_PATH="/"            # 挂载路径
$env:MCP_SSE_PATH="/sse"           # SSE 端点
$env:MCP_MESSAGE_PATH="/messages/" # 消息路径
$env:MCP_STREAMABLE_HTTP_PATH="/mcp" # HTTP 传输路径

# 可选：日志与调试
$env:MCP_LOG_LEVEL="INFO"   # 日志级别：DEBUG/INFO/WARNING/ERROR/CRITICAL
$env:MCP_DEBUG="false"       # 调试模式
```

> **注意**：若未配置 `MX_APIKEY`，服务启动时会直接报错并拒绝请求。

## 3. 本地运行

```bash
# SSE 模式（默认）- HTTP/SSE 服务
eastmoney-mx-finance-mcp-server sse

# stdio 模式 - 标准输入输出，适合 MCP 客户端直接拉起子进程
eastmoney-mx-finance-mcp-server stdio
```

也可直接运行 Python 脚本：

```bash
python server.py sse
python server.py stdio
```

| 模式 | 说明 |
|-----|------|
| `sse` | HTTP/SSE 服务模式，默认监听 `127.0.0.1:8000`，可通过环境变量覆盖 |
| `stdio` | 标准输入输出模式，适合由 MCP 客户端直接拉起子进程 |

## 4. MCP Client 配置示例

### stdio

```json
{
  "command": "eastmoney-mx-finance-mcp-server",
  "args": ["stdio"],
  "env": {
    "MX_APIKEY": "your-apikey"
  }
}
```

### SSE

先本地启动：

```bash
eastmoney-mx-finance-mcp-server sse
```

然后在支持远程 MCP/SSE 的客户端中连接：

- Base URL：`http://127.0.0.1:8000`
- SSE Path：`/sse`
- Message Path：`/messages/`

## 5. 返回结构约定

所有工具接口均返回统一的标准结构：

| 字段 | 说明 |
|-----|------|
| `endpoint` | 实际调用的 API 地址 |
| `request` | 请求体内容 |
| `response` | 上游 API 原始返回（请求成功到达并拿到 JSON 响应时） |
| `success_hint` | 当上游 `status` 或 `code` 为 `0` 时为 `true`，否则为 `false` |
| `error_hint` | 已知错误码的中文提示（如密钥无效、交易失败等） |

**错误处理说明**：

若发生上游 HTTP 错误、网络异常、非 JSON 响应等传输层问题，工具会抛出 MCP tool error（而非返回 `success_hint=false` 的普通结果）。错误消息中包含结构化信息：

```json
{
  "error_type": "http_status_error | request_error | invalid_json",
  "message": "错误描述",
  "status_code": 404,
  "response_text": "..."
}
```

## 6. 使用建议

- `mx_stock_simulator_balance` / `mx_stock_simulator_positions` 返回的金额字段单位为"厘"，建议配合 `mx_amount_li_to_yuan` 进行换算
- 若持仓或委托数据中包含 `price` 与 `priceDec` 字段，可用 `mx_price_restore` 还原真实价格
- `mx_stock_simulator_summary` 会并发拉取资金与持仓数据，并按持仓市值排序输出前 5 大持仓，更适合作为 Agent 的汇总入口
  - 若持仓接口返回业务错误，`positions_overview.available` 会返回 `false`，聚合字段为 `null`，避免将上游失败误判为空仓
- `mx_select_stock` 与 `mx_stock_simulator_orders` 对分页参数做了边界校验：`pageNo >= 1`，`1 <= pageSize <= 100`

## 7. 开发与检查

语法检查：

```bash
python -m compileall server.py
```

本项目暂无自动化测试，如需补充建议优先覆盖：

- 参数校验单测（如分页边界、股票代码格式、交易数量规则等）
- `_post` 的错误分支单测（HTTP 错误、超时、非 JSON 响应）
- `mx_stock_simulator_summary` 的聚合逻辑单测
