# eastmoney-mx-finance-mcp-server

基于 [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) 实现的东方财富·妙想（MX）金融 MCP 服务端。

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
- `mx_stock_simulator_summary()`：资金+持仓汇总（含厘转元）
- `mx_amount_li_to_yuan(amount_li)`：金额单位换算（厘 -> 元）
- `mx_price_restore(price, priceDec)`：价格还原（`price / 10^priceDec`）

## 1. 安装

```bash
cd C:/Users/Xpk22/Desktop/code/mx_mcp_server
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -e .
```

## 2. 配置环境变量

至少需要 `MX_APIKEY`：

```powershell
$env:MX_APIKEY="你的apikey"

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

## 3. 本地运行

```bash
# SSE 模式（默认）
eastmoney-mx-finance-mcp-server sse
# 或省略参数
eastmoney-mx-finance-mcp-server

# stdio 模式
eastmoney-mx-finance-mcp-server stdio
```

- `sse`：HTTP/SSE 服务模式，默认监听 `127.0.0.1:8000`（可通过环境变量覆盖）。
- `stdio`：标准输入输出模式，适合由 MCP 客户端直接拉起子进程。

## 4. 在 MCP Client 中配置示例

请按你的客户端配置格式写入命令和环境变量。核心是：

- 启动命令：`python C:/Users/Xpk22/Desktop/code/mx_mcp_server/server.py`
- 环境变量：至少包含 `MX_APIKEY`

## 5. 返回约定

每个接口返回统一结构：

- `endpoint`：实际调用 URL
- `request`：请求体
- `response`：API 原始返回
- `success_hint`：`status` 或 `code` 为 `0` 时为 `true`
- `error_hint`：命中已知错误码时返回可读提示


