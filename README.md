# eastmoney-mx-finance-mcp-server

基于 [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) 及 [东方财富·妙想Skills](https://clawhub.ai/u/QQK000) 实现的东方财富·妙想（MX）金融 MCP 服务端。

## 项目亮点

- 封装东方财富·妙想的资讯、查数、选股、自选股、模拟交易等能力。
- 返回统一结构，便于 MCP Client 或 Agent 做后处理。
- 提供金额厘转元、价格精度还原等辅助工具。
- 对上游 HTTP 异常、网络异常、非 JSON 响应补充结构化错误输出，减少工具直接抛错的情况。

## 能力清单

- `mx_search(query)`：资讯搜索（新闻/公告/研报/政策）
- `mx_data(toolQuery)`：金融数据查询（行情/资金/财务等）
- `mx_select_stock(keyword, pageNo=1, pageSize=20)`：智能选股
- `mx_selfselect_get()`：查询自选股
- `mx_selfselect_manage(query)`：添加/删除自选股
- `mx_stock_simulator_balance()`：模拟账户资金
- `mx_stock_simulator_positions()`：模拟账户持仓
- `mx_stock_simulator_trade(type, stockCode, quantity, useMarketPrice=False, price=None)`：买卖委托
- `mx_stock_simulator_cancel(orderNo=None, cancelAll=False)`：撤单
- `mx_stock_simulator_orders(pageNo=1, pageSize=20, includeHistory=False)`：委托/成交查询
- `mx_stock_simulator_summary()`：资金 + 持仓汇总（含厘转元与前 5 大持仓）
- `mx_amount_li_to_yuan(amount_li)`：金额单位换算（厘 -> 元）
- `mx_price_restore(price, priceDec)`：价格还原（`price / 10^priceDec`）

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

至少需要 `MX_APIKEY`：

```powershell
$env:MX_APIKEY="你的 apikey"

# 可选：MX API 地址
$env:MX_API_URL="https://mkapi2.dfcfs.com/finskillshub/api/claw"

# 可选：MCP 服务监听配置
$env:MCP_HOST="127.0.0.1"
$env:MCP_PORT="8000"
$env:MCP_MOUNT_PATH="/"
$env:MCP_SSE_PATH="/sse"
$env:MCP_MESSAGE_PATH="/messages/"
$env:MCP_STREAMABLE_HTTP_PATH="/mcp"

# 可选：日志与调试
$env:MCP_LOG_LEVEL="INFO"   # DEBUG/INFO/WARNING/ERROR/CRITICAL
$env:MCP_DEBUG="false"
```

> `MX_APIKEY` 缺失时，服务会直接报错并拒绝请求。

## 3. 本地运行

```bash
# SSE 模式（默认）
eastmoney-mx-finance-mcp-server sse

# stdio 模式
eastmoney-mx-finance-mcp-server stdio
```

- `sse`：HTTP/SSE 服务模式，默认监听 `127.0.0.1:8000`，可通过环境变量覆盖。
- `stdio`：标准输入输出模式，适合由 MCP 客户端直接拉起子进程。

也可以直接运行：

```bash
python server.py sse
python server.py stdio
```

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

每个接口默认返回统一结构：

- `endpoint`：实际调用 URL
- `request`：请求体
- `response`：上游 API 原始返回（适用于请求成功到达并拿到 JSON 响应的情况）
- `success_hint`：当上游 `status` 或 `code` 为 `0` 时为 `true`
- `error_hint`：已知错误码映射

若发生上游 HTTP / 网络 / 非 JSON 响应等传输层失败，工具会直接抛出 MCP tool error，而不是返回 `success_hint=false` 的普通结果；错误消息中会附带结构化细节（包含 `error_type`、`message`、`status_code`、`response_text` 等字段），方便客户端按“调用失败”语义重试或中止。

## 6. 使用建议

- `mx_stock_simulator_balance` / `mx_stock_simulator_positions` 返回中的金额字段通常是“厘”，可配合 `mx_amount_li_to_yuan` 使用。
- 若持仓或委托数据中包含 `price` 与 `priceDec`，可用 `mx_price_restore` 还原真实价格。
- `mx_stock_simulator_summary` 会并发拉取资金与持仓数据，并按持仓市值输出前 5 大持仓，更适合作为 Agent 的汇总入口。若持仓接口返回业务错误，`positions_overview.available` 会是 `false`，聚合字段会保留为 `null`，避免把上游失败误判为空仓。
- `mx_select_stock` 与 `mx_stock_simulator_orders` 对分页参数做了边界检查：`pageNo >= 1`、`1 <= pageSize <= 100`。

## 7. 开发与检查

```bash
python -m compileall server.py
```

当前仓库未提供自动化测试；如需补充，建议优先增加：

- 参数校验单测
- `_post` 的错误分支单测（HTTP 错误、超时、非 JSON）
- `mx_stock_simulator_summary` 的聚合逻辑单测
