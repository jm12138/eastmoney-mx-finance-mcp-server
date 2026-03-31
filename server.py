import asyncio
import json
import logging
import os
import re
import sys
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_BASE_URL = "https://mkapi2.dfcfs.com/finskillshub/api/claw"
SERVER_NAME = "eastmoney-mx-finance-mcp-server"
SERVER_VERSION = "0.2.1"
SERVER_WEBSITE_URL = "https://marketing.dfcfs.com/views/finskillshub/indexIoMv0EzE"
SERVER_INSTRUCTIONS = (
    "Eastmoney MX finance MCP server. "
    f"Version: {SERVER_VERSION}. "
    "Provides tools for MX news search, financial data query, stock screening, "
    "self-select management, and stock simulator workflows."
)
DEFAULT_TIMEOUT_SECONDS = 30.0


def _get_env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_env_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_log_level(default: str = "INFO") -> str:
    allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    value = os.getenv("MCP_LOG_LEVEL", default).upper()
    return value if value in allowed else default


MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = _get_env_int("MCP_PORT", 8000)
MCP_MOUNT_PATH = os.getenv("MCP_MOUNT_PATH", "/")
MCP_SSE_PATH = os.getenv("MCP_SSE_PATH", "/sse")
MCP_MESSAGE_PATH = os.getenv("MCP_MESSAGE_PATH", "/messages/")
MCP_STREAMABLE_HTTP_PATH = os.getenv("MCP_STREAMABLE_HTTP_PATH", "/mcp")
MCP_DEBUG = _get_env_bool("MCP_DEBUG", False)
MCP_LOG_LEVEL = _get_env_log_level("INFO")

logger = logging.getLogger(SERVER_NAME)
logger.setLevel(getattr(logging, MCP_LOG_LEVEL))
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

ERROR_HINTS = {
    113: "调用次数达到上限，请在妙想页面更新或升级 apikey。",
    114: "密钥无效，请检查请求头中的 apikey。",
    116: "密钥无效，请检查请求头中的 apikey。",
    404: "未绑定模拟账户，请前往 https://dl.dfcfs.com/m/itc4 绑定。",
    501: "交易失败，常见原因：非交易时段、余额不足、价格不符合规则。",
}

mcp = FastMCP(
    name=SERVER_NAME,
    instructions=SERVER_INSTRUCTIONS,
    website_url=SERVER_WEBSITE_URL,
    debug=MCP_DEBUG,
    log_level=MCP_LOG_LEVEL,
    host=MCP_HOST,
    port=MCP_PORT,
    mount_path=MCP_MOUNT_PATH,
    sse_path=MCP_SSE_PATH,
    message_path=MCP_MESSAGE_PATH,
    streamable_http_path=MCP_STREAMABLE_HTTP_PATH,
)


def _get_apikey() -> str:
    apikey = os.getenv("MX_APIKEY")
    if not apikey:
        raise ValueError("Missing MX_APIKEY. Please set environment variable MX_APIKEY.")
    return apikey


def _get_base_url() -> str:
    return os.getenv("MX_API_URL", DEFAULT_BASE_URL).rstrip("/")


def _extract_status_code(body: dict[str, Any]) -> int | None:
    for key in ("status", "code"):
        value = body.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _with_common_meta(url: str, payload: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    code = _extract_status_code(body)
    return {
        "endpoint": url,
        "request": payload,
        "response": body,
        "success_hint": code == 0,
        "error_hint": ERROR_HINTS.get(code),
    }


def _build_error_response(
    url: str,
    payload: dict[str, Any],
    *,
    error_type: str,
    message: str,
    status_code: int | None = None,
    response_text: str | None = None,
) -> dict[str, Any]:
    error_body: dict[str, Any] = {
        "error_type": error_type,
        "message": message,
    }
    if status_code is not None:
        error_body["status_code"] = status_code
    if response_text:
        error_body["response_text"] = response_text[:500]

    return {
        "endpoint": url,
        "request": payload,
        "response": error_body,
        "success_hint": False,
        "error_hint": message,
    }


class UpstreamAPIError(RuntimeError):
    def __init__(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        error_type: str,
        message: str,
        status_code: int | None = None,
        response_text: str | None = None,
    ) -> None:
        self.details = _build_error_response(
            url,
            payload,
            error_type=error_type,
            message=message,
            status_code=status_code,
            response_text=response_text,
        )
        super().__init__(json.dumps(self.details, ensure_ascii=False))


def _li_to_yuan(value: float | int) -> float:
    """将厘单位金额转换为元（1 元 = 1000 厘）。"""
    return round(float(value) / 1000.0, 3)


def _restore_price(price: float | int, price_dec: int) -> float:
    """还原价格：真实价格 = price / 10^priceDec。"""
    return round(float(price) / (10**price_dec), price_dec)


def _walk_json(node: Any, path: str = "") -> list[tuple[str, Any]]:
    """递归遍历 JSON 树，返回所有叶子节点的 (路径, 值) 对。"""
    items: list[tuple[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else key
            items.extend(_walk_json(value, child_path))
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            child_path = f"{path}[{idx}]"
            items.extend(_walk_json(value, child_path))
    else:
        items.append((path, node))
    return items


def _collect_money_candidates(node: Any) -> list[dict[str, Any]]:
    """从 JSON 中提取常见金额字段，并返回厘/元双单位值。"""
    money_keys = {
        "totalAssets",
        "availableAssets",
        "availableAmount",
        "frozenAmount",
        "marketValue",
        "value",
        "positionValue",
        "cost",
        "costAmount",
        "profit",
        "profitAmount",
        "floatProfit",
    }
    rows: list[dict[str, Any]] = []
    for path, value in _walk_json(node):
        if not path:
            continue
        key = path.split(".")[-1]
        if "[" in key:
            key = key.split("[", 1)[0]
        if key not in money_keys:
            continue
        if isinstance(value, (int, float)):
            rows.append(
                {
                    "path": path,
                    "value_li": value,
                    "value_yuan": _li_to_yuan(value),
                }
            )
    return rows


def _find_data_list(node: Any, max_depth: int = 20, _depth: int = 0) -> list[dict[str, Any]]:
    """递归查找所有 dataList 字段并合并返回，限制最大深度防止无限递归。"""
    if _depth > max_depth:
        return []
    results: list[dict[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "dataList" and isinstance(value, list):
                results.extend(item for item in value if isinstance(item, dict))
            results.extend(_find_data_list(value, max_depth, _depth + 1))
    elif isinstance(node, list):
        for item in node:
            results.extend(_find_data_list(item, max_depth, _depth + 1))
    return results


def _pick_value(row: dict[str, Any], keys: tuple[str, ...]) -> float:
    """从字典中按优先级尝试获取数值，找不到返回 0.0。"""
    for key in keys:
        value = row.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def _validate_pagination(page_no: int, page_size: int) -> None:
    """验证分页参数：pageNo >= 1，pageSize 在 1~100 之间。"""
    if page_no < 1:
        raise ValueError("pageNo must be >= 1")
    if page_size < 1 or page_size > 100:
        raise ValueError("pageSize must be between 1 and 100")


async def _post(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request_payload = payload or {}
    url = f"{_get_base_url()}{path}"
    headers = {
        "Content-Type": "application/json",
        "apikey": _get_apikey(),
    }

    logger.debug("POST %s with payload: %s", url, request_payload)

    response = None
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers=headers, json=request_payload)
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as exc:
        logger.error("HTTP error %d from %s: %s", exc.response.status_code, url, exc.response.text[:200])
        raise UpstreamAPIError(
            url,
            request_payload,
            error_type="http_status_error",
            message=f"HTTP {exc.response.status_code} returned by upstream API.",
            status_code=exc.response.status_code,
            response_text=exc.response.text,
        ) from exc
    except httpx.RequestError as exc:
        logger.error("Request error to %s: %s", url, exc)
        raise UpstreamAPIError(
            url,
            request_payload,
            error_type="request_error",
            message=f"Request to upstream API failed: {exc}",
        ) from exc
    except json.JSONDecodeError as exc:
        logger.error("JSON decode error from %s: %s", url, exc)
        raise UpstreamAPIError(
            url,
            request_payload,
            error_type="invalid_json",
            message="Upstream API returned a non-JSON response.",
            status_code=response.status_code if response else None,
            response_text=response.text if response else None,
        ) from exc

    logger.debug("Response from %s: success=%s", url, _extract_status_code(body) == 0)
    return _with_common_meta(url, request_payload, body)


def _validate_stock_code(stock_code: str) -> None:
    if not re.fullmatch(r"\d{6}", stock_code):
        raise ValueError("stockCode must be a 6-digit A-share code, e.g. 600519")


@mcp.tool()
async def mx_search(query: str) -> dict[str, Any]:
    """东方财富妙想资讯检索（news-search）。

    适用场景：
    - 个股新闻、公告、研报、机构观点
    - 板块/主题事件、政策解读
    - 需要时效性和权威信源的金融信息检索

    参数：
    - query: 自然语言搜索问句，例如“贵州茅台最新研报”。

    返回：
    - endpoint/request/response/success_hint/error_hint 统一结构。
    - response 常见核心字段：title、secuList、trunk。
    """
    return await _post("/news-search", {"query": query})


@mcp.tool()
async def mx_data(toolQuery: str) -> dict[str, Any]:
    """东方财富妙想金融数据查询（query）。

    适用场景：
    - 实时行情、主力资金、估值指标
    - 财务指标、公司信息、高管信息
    - 企业关系与经营相关数据

    参数：
    - toolQuery: 自然语言查数指令，例如“东方财富最新价”。

    返回：
    - 统一结构，原始数据位于 response。
    - 重点可关注 response.data.dataTableDTOList / nameMap / table。
    """
    return await _post("/query", {"toolQuery": toolQuery})


@mcp.tool()
async def mx_select_stock(keyword: str, pageNo: int = 1, pageSize: int = 20) -> dict[str, Any]:
    """东方财富妙想智能选股（stock-screen）。

    参数：
    - keyword: 选股条件，自然语言描述，例如“今日涨幅2%的股票”。
    - pageNo: 页码，>=1。
    - pageSize: 每页条数，范围 1~100。

    返回：
    - 统一结构，原始结果在 response.data.data.result。
    - 常见核心字段：columns、dataList、responseConditionList、totalCondition。
    """
    _validate_pagination(pageNo, pageSize)

    return await _post(
        "/stock-screen",
        {
            "keyword": keyword,
            "pageNo": pageNo,
            "pageSize": pageSize,
        },
    )


@mcp.tool()
async def mx_selfselect_get() -> dict[str, Any]:
    """查询东方财富账户自选股列表（self-select/get）。

    返回：
    - 统一结构。
    - 自选列表通常位于 response.data.allResults.result.dataList（以实际返回为准）。
    """
    return await _post("/self-select/get", {})


@mcp.tool()
async def mx_selfselect_manage(query: str) -> dict[str, Any]:
    """管理自选股（self-select/manage），支持添加/删除。

    参数：
    - query: 自然语言操作指令，例如“把贵州茅台加入自选”。

    返回：
    - 统一结构，具体执行结果在 response 中。
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string describing the operation.")

    return await _post("/self-select/manage", {"query": query.strip()})


@mcp.tool()
async def mx_stock_simulator_balance() -> dict[str, Any]:
    """模拟交易资金查询（mockTrading/balance）。

    返回：
    - 总资产、可用资金、仓位等信息（具体字段以 response 为准）。
    - 金额字段通常单位为“厘”（1/1000 元）。
    """
    result = await _post("/mockTrading/balance", {})
    result["unit_hint"] = "金额字段单位为厘(1/1000 元)。"
    return result


@mcp.tool()
async def mx_stock_simulator_positions() -> dict[str, Any]:
    """模拟交易持仓查询（mockTrading/positions）。

    返回：
    - 持仓明细、成本、盈亏等信息。
    - 金额字段通常单位为“厘”（1/1000 元）。
    - 若存在 price 与 priceDec，可用 mx_price_restore 还原真实价格。
    """
    result = await _post("/mockTrading/positions", {})
    result["unit_hint"] = "金额字段单位为厘(1/1000 元)；如存在 price+priceDec，可用 mx_price_restore 转换价格。"
    return result


@mcp.tool()
async def mx_stock_simulator_trade(
    trade_type: str,
    stockCode: str,
    quantity: int,
    useMarketPrice: bool = False,
    price: float | None = None,
) -> dict[str, Any]:
    """模拟交易下单（mockTrading/trade）。

    参数：
    - trade_type: 交易方向，仅支持 `buy` / `sell`。
    - stockCode: 6 位 A 股代码，如 `600519`。
    - quantity: 委托数量，必须 > 0；买入时必须是 100 的整数倍。
    - useMarketPrice: 是否使用市价单。True 时忽略 price。
    - price: 限价单价格，useMarketPrice=False 时必填且 > 0。

    返回：
    - 统一结构，交易受理结果在 response 中。
    - 常见失败码：501（交易时段/余额/价格规则等）。
    """
    action = trade_type.lower().strip()
    if action not in {"buy", "sell"}:
        raise ValueError("type must be 'buy' or 'sell'")

    _validate_stock_code(stockCode)

    if quantity <= 0:
        raise ValueError("quantity must be > 0")
    if action == "buy" and quantity % 100 != 0:
        raise ValueError("buy quantity must be a multiple of 100")

    if useMarketPrice:
        payload = {
            "type": action,
            "stockCode": stockCode,
            "quantity": quantity,
            "useMarketPrice": True,
        }
    else:
        if price is None or price <= 0:
            raise ValueError("price must be > 0 when useMarketPrice is false")
        payload = {
            "type": action,
            "stockCode": stockCode,
            "price": price,
            "quantity": quantity,
            "useMarketPrice": False,
        }

    return await _post("/mockTrading/trade", payload)


@mcp.tool()
async def mx_stock_simulator_cancel(orderNo: str | None = None, cancelAll: bool = False) -> dict[str, Any]:
    """模拟交易撤单（mockTrading/cancel）。

    参数：
    - orderNo: 指定撤单的委托单号。
    - cancelAll: 是否一键撤回全部未成交单。

    说明：
    - 传 orderNo：按单号撤单。
    - cancelAll=True：批量撤单。
    """
    payload: dict[str, Any] = {"cancelAll": cancelAll}
    if orderNo:
        payload["orderNo"] = orderNo

    return await _post("/mockTrading/cancel", payload)


@mcp.tool()
async def mx_stock_simulator_orders(
    pageNo: int = 1,
    pageSize: int = 20,
    includeHistory: bool = False,
) -> dict[str, Any]:
    """模拟交易委托查询（mockTrading/orders）。

    参数：
    - pageNo: 页码，>=1。
    - pageSize: 每页条数，范围 1~100。
    - includeHistory: 是否包含历史委托/成交记录。
    """
    _validate_pagination(pageNo, pageSize)

    payload = {
        "pageNo": pageNo,
        "pageSize": pageSize,
        "includeHistory": includeHistory,
    }

    return await _post("/mockTrading/orders", payload)


@mcp.tool()
async def mx_stock_simulator_summary() -> dict[str, Any]:
    """模拟交易汇总视图（组合 balance + positions）。

    功能：
    - 拉取资金与持仓两个接口并聚合。
    - 自动提取常见金额字段，并给出“厘 -> 元”换算结果。
    - 输出持仓概览：持仓数量、总市值、总盈亏、前5大持仓。

    返回：
    - balance_status / positions_status / error_hint
    - balance_money_fields / positions_money_fields（含 value_li 与 value_yuan）
    - positions_overview（若持仓接口返回业务错误，则 available=false 且聚合字段为 None）
    - raw（完整原始响应，便于二次解析）
    """
    balance_result, positions_result = await asyncio.gather(
        _post("/mockTrading/balance", {}),
        _post("/mockTrading/positions", {}),
    )

    positions_ok = positions_result.get("success_hint") is True
    position_rows = _find_data_list(positions_result.get("response", {})) if positions_ok else []
    total_market_value_li = 0.0
    total_profit_li = 0.0
    for row in position_rows:
        total_market_value_li += _pick_value(row, ("value", "marketValue", "positionValue"))
        total_profit_li += _pick_value(row, ("profit", "floatProfit", "profitAmount"))

    sorted_rows = sorted(
        position_rows,
        key=lambda row: _pick_value(row, ("value", "marketValue", "positionValue")),
        reverse=True,
    )

    top_positions = []
    for row in sorted_rows[:5]:
        market_value_li = _pick_value(row, ("value", "marketValue", "positionValue"))
        profit_li = _pick_value(row, ("profit", "floatProfit", "profitAmount"))
        top_positions.append(
            {
                "stockCode": row.get("stockCode") or row.get("code"),
                "stockName": row.get("stockName") or row.get("name"),
                "quantity": row.get("quantity") or row.get("holdCount"),
                "marketValue_li": market_value_li,
                "marketValue_yuan": _li_to_yuan(market_value_li),
                "profit_li": profit_li,
                "profit_yuan": _li_to_yuan(profit_li),
            }
        )

    positions_overview = {
        "available": positions_ok,
        "position_count": len(position_rows) if positions_ok else None,
        "total_market_value_li": total_market_value_li if positions_ok else None,
        "total_market_value_yuan": _li_to_yuan(total_market_value_li) if positions_ok else None,
        "total_profit_li": total_profit_li if positions_ok else None,
        "total_profit_yuan": _li_to_yuan(total_profit_li) if positions_ok else None,
        "top_positions": top_positions if positions_ok else None,
    }
    if not positions_ok:
        positions_overview["error_hint"] = positions_result.get("error_hint") or "持仓查询失败，未返回有效数据。"

    return {
        "balance_status": balance_result.get("success_hint"),
        "positions_status": positions_result.get("success_hint"),
        "error_hint": balance_result.get("error_hint") or positions_result.get("error_hint"),
        "balance_money_fields": _collect_money_candidates(balance_result.get("response", {})),
        "positions_money_fields": _collect_money_candidates(positions_result.get("response", {})),
        "positions_overview": positions_overview,
        "raw": {
            "balance": balance_result,
            "positions": positions_result,
        },
    }


@mcp.tool()
def mx_amount_li_to_yuan(amount_li: float) -> dict[str, float]:
    """金额单位转换工具：厘 -> 元。

    参数：
    - amount_li: 以厘为单位的金额（1 元 = 1000 厘）。
    """
    return {
        "amount_li": amount_li,
        "amount_yuan": _li_to_yuan(amount_li),
    }


@mcp.tool()
def mx_price_restore(price: float, priceDec: int) -> dict[str, float | int]:
    """价格还原工具：真实价格 = price / 10^priceDec。

    参数：
    - price: 接口返回的原始价格值。
    - priceDec: 价格小数位精度（必须 >= 0）。
    """
    if priceDec < 0:
        raise ValueError("priceDec must be >= 0")

    return {
        "price": price,
        "priceDec": priceDec,
        "real_price": _restore_price(price, priceDec),
    }


def main() -> None:
    mode = "sse"
    if len(sys.argv) > 1:
        mode = sys.argv[1].strip().lower()

    if mode not in {"sse", "stdio"}:
        raise ValueError("Usage: eastmoney-mx-finance-mcp-server [sse|stdio]")

    mcp.run(transport=mode)


if __name__ == "__main__":
    main()
