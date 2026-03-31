"""
MCP 服务集成测试脚本

测试所有 MCP 工具接口的连接和调用。
需要设置环境变量 MX_APIKEY 才能运行。

使用方法：
    python test_mcp_integration.py              # 运行所有测试
    python test_mcp_integration.py --tool mx_search  # 只测试指定工具
    python test_mcp_integration.py --list        # 列出所有可用工具
"""

import asyncio
import json
import os
import sys
import time
from typing import Any

import httpx


# 配置
BASE_URL = os.getenv("MX_API_URL", "https://mkapi2.dfcfs.com/finskillshub/api/claw").rstrip("/")
API_KEY = os.getenv("MX_APIKEY", "")
TIMEOUT = 30.0

# 颜色输出
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def success(msg: str):
    print(f"{Colors.GREEN}✓ {msg}{Colors.RESET}")


def error(msg: str):
    print(f"{Colors.RED}✗ {msg}{Colors.RESET}")


def warning(msg: str):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.RESET}")


def info(msg: str):
    print(f"{Colors.BLUE}ℹ {msg}{Colors.RESET}")


def header(msg: str):
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{msg}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")


# 工具定义
TOOLS = [
    {
        "name": "mx_search",
        "description": "资讯检索",
        "path": "/news-search",
        "payload": {"query": "贵州茅台最新研报"},
    },
    {
        "name": "mx_data",
        "description": "金融数据查询",
        "path": "/query",
        "payload": {"toolQuery": "东方财富最新价"},
    },
    {
        "name": "mx_select_stock",
        "description": "智能选股",
        "path": "/stock-screen",
        "payload": {"keyword": "今日涨幅2%的股票", "pageNo": 1, "pageSize": 5},
    },
    {
        "name": "mx_selfselect_get",
        "description": "查询自选股",
        "path": "/self-select/get",
        "payload": {},
    },
    {
        "name": "mx_selfselect_manage",
        "description": "管理自选股",
        "path": "/self-select/manage",
        "payload": {"query": "查询我的自选股"},
    },
    {
        "name": "mx_stock_simulator_balance",
        "description": "模拟交易资金查询",
        "path": "/mockTrading/balance",
        "payload": {},
    },
    {
        "name": "mx_stock_simulator_positions",
        "description": "模拟交易持仓查询",
        "path": "/mockTrading/positions",
        "payload": {},
    },
    {
        "name": "mx_stock_simulator_orders",
        "description": "模拟交易委托查询",
        "path": "/mockTrading/orders",
        "payload": {"pageNo": 1, "pageSize": 5, "includeHistory": False},
    },
    {
        "name": "mx_stock_simulator_summary",
        "description": "模拟交易汇总视图",
        "path": "组合接口",
        "payload": None,  # 特殊处理
    },
    {
        "name": "mx_amount_li_to_yuan",
        "description": "金额单位转换（厘->元）",
        "path": None,  # 本地工具
        "payload": {"amount_li": 123456},
        "local": True,
    },
    {
        "name": "mx_price_restore",
        "description": "价格还原工具",
        "path": None,  # 本地工具
        "payload": {"price": 18500, "priceDec": 3},
        "local": True,
    },
]


async def test_connection() -> bool:
    """测试 MCP 服务连接"""
    header("测试 1: 服务连接")
    
    if not API_KEY:
        error("未设置 MX_APIKEY 环境变量")
        print("请设置环境变量: export MX_APIKEY=your_api_key")
        return False
    
    info(f"API 地址: {BASE_URL}")
    info(f"API Key: {API_KEY[:10]}...")
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # 测试一个简单的接口
            response = await client.post(
                f"{BASE_URL}/news-search",
                headers={
                    "Content-Type": "application/json",
                    "apikey": API_KEY,
                },
                json={"query": "测试"},
            )
            
            if response.status_code == 200:
                success(f"连接成功 (HTTP {response.status_code})")
                return True
            else:
                warning(f"连接异常 (HTTP {response.status_code})")
                print(f"响应: {response.text[:200]}")
                return False
                
    except httpx.ConnectError as e:
        error(f"连接失败: {e}")
        return False
    except Exception as e:
        error(f"测试失败: {e}")
        return False


async def test_tool(tool: dict) -> dict[str, Any]:
    """测试单个工具接口"""
    name = tool["name"]
    desc = tool["description"]
    payload = tool.get("payload")
    is_local = tool.get("local", False)
    
    print(f"\n{Colors.BOLD}测试: {name}{Colors.RESET}")
    print(f"描述: {desc}")
    
    start_time = time.time()
    
    try:
        if is_local:
            # 本地工具，直接导入测试
            from server import mx_amount_li_to_yuan, mx_price_restore
            
            if name == "mx_amount_li_to_yuan":
                result = mx_amount_li_to_yuan(**payload)
            elif name == "mx_price_restore":
                result = mx_price_restore(**payload)
            else:
                raise ValueError(f"未知的本地工具: {name}")
        else:
            # 远程工具，通过 HTTP 调用
            if tool.get("path") == "组合接口":
                # 特殊处理 summary 接口
                from server import mx_stock_simulator_summary
                result = await mx_stock_simulator_summary()
            else:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    response = await client.post(
                        f"{BASE_URL}{tool['path']}",
                        headers={
                            "Content-Type": "application/json",
                            "apikey": API_KEY,
                        },
                        json=payload,
                    )
                    response.raise_for_status()
                    result = response.json()
        
        elapsed = time.time() - start_time
        
        # 检查结果
        success_hint = result.get("success_hint", True)
        if success_hint or is_local:
            success(f"调用成功 ({elapsed:.2f}s)")
            print(f"  请求参数: {json.dumps(payload, ensure_ascii=False)}")
            
            # 显示关键结果
            if is_local:
                print(f"  返回结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
            else:
                response_data = result.get("response", {})
                if isinstance(response_data, dict):
                    # 显示前几个键
                    keys = list(response_data.keys())[:5]
                    print(f"  响应字段: {', '.join(keys)}")
                elif isinstance(response_data, list):
                    print(f"  响应类型: 列表 (长度: {len(response_data)})")
                else:
                    print(f"  响应类型: {type(response_data).__name__}")
            
            return {"name": name, "status": "success", "time": elapsed}
        else:
            warning(f"调用完成但有错误提示 ({elapsed:.2f}s)")
            error_hint = result.get("error_hint")
            if error_hint:
                print(f"  错误提示: {error_hint}")
            return {"name": name, "status": "warning", "time": elapsed, "hint": error_hint}
            
    except httpx.HTTPStatusError as e:
        elapsed = time.time() - start_time
        error(f"HTTP 错误 ({elapsed:.2f}s): {e.response.status_code}")
        print(f"  响应: {e.response.text[:200]}")
        return {"name": name, "status": "error", "time": elapsed, "error": str(e)}
        
    except Exception as e:
        elapsed = time.time() - start_time
        error(f"调用失败 ({elapsed:.2f}s): {e}")
        return {"name": name, "status": "error", "time": elapsed, "error": str(e)}


async def run_all_tests(tool_filter: str = None):
    """运行所有测试"""
    header("MCP 服务集成测试")
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API 地址: {BASE_URL}")
    
    # 测试连接
    connected = await test_connection()
    if not connected:
        error("服务连接失败，跳过接口测试")
        return
    
    # 筛选工具
    tools_to_test = TOOLS
    if tool_filter:
        tools_to_test = [t for t in TOOLS if tool_filter in t["name"]]
        if not tools_to_test:
            error(f"未找到匹配的工具: {tool_filter}")
            return
    
    header(f"测试接口 ({len(tools_to_test)} 个)")
    
    results = []
    for tool in tools_to_test:
        result = await test_tool(tool)
        results.append(result)
    
    # 汇总结果
    header("测试汇总")
    success_count = sum(1 for r in results if r["status"] == "success")
    warning_count = sum(1 for r in results if r["status"] == "warning")
    error_count = sum(1 for r in results if r["status"] == "error")
    total_time = sum(r["time"] for r in results)
    
    print(f"\n{Colors.BOLD}总计: {len(results)} 个接口{Colors.RESET}")
    print(f"  {Colors.GREEN}成功: {success_count}{Colors.RESET}")
    print(f"  {Colors.YELLOW}警告: {warning_count}{Colors.RESET}")
    print(f"  {Colors.RED}失败: {error_count}{Colors.RESET}")
    print(f"  总耗时: {total_time:.2f}s")
    
    print(f"\n{Colors.BOLD}详细结果:{Colors.RESET}")
    for r in results:
        status_icon = "✓" if r["status"] == "success" else ("⚠" if r["status"] == "warning" else "✗")
        status_color = Colors.GREEN if r["status"] == "success" else (Colors.YELLOW if r["status"] == "warning" else Colors.RED)
        print(f"  {status_color}{status_icon} {r['name']}{Colors.RESET} ({r['time']:.2f}s)")
        if r.get("hint"):
            print(f"    提示: {r['hint']}")
        if r.get("error"):
            print(f"    错误: {r['error'][:100]}")
    
    if error_count == 0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}所有测试通过！{Colors.RESET}")
    else:
        print(f"\n{Colors.YELLOW}部分测试失败，请检查上述错误信息{Colors.RESET}")


def list_tools():
    """列出所有可用工具"""
    header("可用工具列表")
    for i, tool in enumerate(TOOLS, 1):
        local_tag = " [本地]" if tool.get("local") else ""
        print(f"{i}. {tool['name']}{local_tag}")
        print(f"   {tool['description']}")
        if tool.get("path"):
            print(f"   路径: {tool['path']}")
        print()


def main():
    # 解析参数
    args = sys.argv[1:]
    
    if "--list" in args:
        list_tools()
        return
    
    tool_filter = None
    if "--tool" in args:
        idx = args.index("--tool")
        if idx + 1 < len(args):
            tool_filter = args[idx + 1]
    
    # 运行测试
    asyncio.run(run_all_tests(tool_filter))


if __name__ == "__main__":
    main()
