import os
import sys
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from typing import Dict, List, Optional, Any
from filelock import FileLock
from pathlib import Path
# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
import json

from tools.general_tools import get_config_value, write_config_value
from tools.fee_tools import (
    calculate_commission,
    money,
    quantity,
    validate_trade_value,
)
from tools.price_tools import (get_latest_position, get_open_prices,
                               get_yesterday_date,
                               get_yesterday_open_and_close_price,
                               get_yesterday_profit)

mcp = FastMCP("TradeTools")


def _position_file_path(signature: str, log_path: str = "./data/agent_data") -> str:
    """Return the position path using the same convention as price_tools."""
    normalized = log_path[7:] if log_path.startswith("./data/") else log_path
    path = Path(project_root) / "data" / normalized / signature / "position" / "position.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _append_transaction(
    position_file_path: str,
    today_date: str,
    action_id: int,
    action: Dict[str, Any],
    positions: Dict[str, Any],
    costs: Optional[Dict[str, Any]] = None,
) -> None:
    record: Dict[str, Any] = {
        "date": today_date,
        "id": action_id,
        "this_action": action,
        "positions": positions,
    }
    if costs:
        record["costs"] = costs
    with open(position_file_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

def _position_lock(signature: str):
    """
    创建位置文件锁
    
    Args:
        signature: 代理签名，用于确定锁文件路径
    
    Returns:
        FileLock: 文件锁对象
    """
    # 创建锁文件路径
    base_dir = Path(project_root) / "data" / "agent_data" / signature
    base_dir.mkdir(parents=True, exist_ok=True)
    lock_file = base_dir / "position.lock"
    
    # 返回 FileLock 对象
    return FileLock(str(lock_file))



@mcp.tool()
def buy(symbol: str, amount: int) -> Dict[str, Any]:
    """
    Buy stock function

    This function simulates stock buying operations, including the following steps:
    1. Get current position and operation ID
    2. Get stock opening price for the day
    3. Validate buy conditions (sufficient cash, lot size for CN market)
    4. Update position (increase stock quantity, decrease cash)
    5. Record transaction to position.jsonl file

    Args:
        symbol: Stock symbol, such as "AAPL", "MSFT", etc.
        amount: Buy quantity, must be a positive integer, indicating how many shares to buy
                For Chinese A-shares (symbols ending with .SH or .SZ), must be multiples of 100

    Returns:
        Dict[str, Any]:
          - Success: Returns new position dictionary (containing stock quantity and cash balance)
          - Failure: Returns {"error": error message, ...} dictionary

    Raises:
        ValueError: Raised when SIGNATURE environment variable is not set

    Example:
        >>> result = buy("AAPL", 10)
        >>> print(result)  # {"AAPL": 110, "MSFT": 5, "CASH": 5000.0, ...}
        >>> result = buy("600519.SH", 100)  # Chinese A-shares must be multiples of 100
        >>> print(result)  # {"600519.SH": 100, "CASH": 85000.0, ...}
    """
    # Step 1: Get environment variables and basic information
    # Get signature (model name) from environment variable, used to determine data storage path
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")

    # Get current trading date from environment variable
    today_date = get_config_value("TODAY_DATE")

    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        return {"error": "amount must be a positive integer number of shares", "symbol": symbol, "amount": amount}

    # Auto-detect market type based on symbol format
    market = "cn" if symbol.endswith((".SH", ".SZ")) else "us"

    # 🇨🇳 Chinese A-shares trading rule: Must trade in lots of 100 shares (一手 = 100股)
    if market == "cn" and amount % 100 != 0:
        return {
            "error": f"Chinese A-shares must be traded in multiples of 100 shares (1 lot = 100 shares). You tried to buy {amount} shares.",
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
            "suggestion": f"Please use {(amount // 100) * 100} or {((amount // 100) + 1) * 100} shares instead.",
        }

    # Step 2: Get current latest position and operation ID
    # get_latest_position returns two values: position dictionary and current maximum operation ID
    # This ID is used to ensure each operation has a unique identifier
    # Acquire lock for atomic read-modify-write on positions
    with _position_lock(signature):
        try:
            # Step 1: 获取当前持仓
            current_position, current_action_id = get_latest_position(today_date, signature)
            
            # Step 2: 获取股票价格
            this_symbol_price = get_open_prices(today_date, [symbol], market=market)[f"{symbol}_price"]
            
            # Step 3: 计算现金
            current_cash = money(current_position.get("CASH", 0))
            gross_value = money(this_symbol_price * amount)
            commission = calculate_commission(gross_value, "open") if market == "us" else money(0)
            required_cash = money(gross_value + commission)
            cash_left = current_cash - required_cash
            
            # Step 4: 验证购买条件
            if cash_left < 0:
                return {
                    "error": "Insufficient cash!",
                    "required_cash": required_cash,
                    "cash_available": current_cash,
                    "symbol": symbol,
                    "date": today_date,
                }
            
            # Step 5: 更新持仓
            new_position = current_position.copy()
            new_position["CASH"] = float(money(cash_left))
            new_position[symbol] = new_position.get(symbol, 0) + amount
            
            # Step 6: 记录交易
            log_path = get_config_value("LOG_PATH", "./data/agent_data")
            if log_path.startswith("./data/"):
                log_path = log_path[7:]
            position_file_path = os.path.join(project_root, "data", log_path, signature, "position", "position.jsonl")
            
            transaction_record = {
                "date": today_date,
                "id": current_action_id + 1,
                "this_action": {"action": "buy", "symbol": symbol, "amount": amount},
                "positions": new_position,
            }
            
            transaction_record["costs"] = {
                "gross_value_usd": float(gross_value),
                "commission_usd": float(commission),
                "cash_used_usd": float(required_cash),
            }
            with open(position_file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(transaction_record, ensure_ascii=False) + "\n")
            
            # Step 7: 设置交易标志
            write_config_value("IF_TRADE", True)
            return new_position
            
        except KeyError:
            return {"error": f"Symbol {symbol} not found!", "symbol": symbol, "date": today_date}
        except Exception as e:
            return {"error": f"Transaction failed: {str(e)}", "symbol": symbol, "date": today_date}


def _get_today_buy_amount(symbol: str, today_date: str, signature: str) -> int:
    """
    Helper function to get the total amount bought today for T+1 restriction check

    Args:
        symbol: Stock symbol
        today_date: Trading date
        signature: Model signature

    Returns:
        Total shares bought today
    """
    log_path = get_config_value("LOG_PATH", "./data/agent_data")
    if log_path.startswith("./data/"):
        log_path = log_path[7:]  # Remove "./data/" prefix
    position_file_path = os.path.join(project_root, "data", log_path, signature, "position", "position.jsonl")

    if not os.path.exists(position_file_path):
        return 0

    total_bought_today = 0
    with open(position_file_path, "r") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if record.get("date") == today_date:
                    this_action = record.get("this_action", {})
                    if this_action.get("action") == "buy" and this_action.get("symbol") == symbol:
                        total_bought_today += this_action.get("amount", 0)
            except Exception:
                continue

    return total_bought_today


@mcp.tool()
def sell(symbol: str, amount: int) -> Dict[str, Any]:
    """
    Sell stock function

    This function simulates stock selling operations, including the following steps:
    1. Get current position and operation ID
    2. Get stock opening price for the day
    3. Validate sell conditions (position exists, sufficient quantity, lot size, T+1 for CN market)
    4. Update position (decrease stock quantity, increase cash)
    5. Record transaction to position.jsonl file

    Args:
        symbol: Stock symbol, such as "AAPL", "MSFT", etc.
        amount: Sell quantity, must be a positive integer, indicating how many shares to sell
                For Chinese A-shares (symbols ending with .SH or .SZ), must be multiples of 100
                and cannot sell shares bought on the same day (T+1 rule)

    Returns:
        Dict[str, Any]:
          - Success: Returns new position dictionary (containing stock quantity and cash balance)
          - Failure: Returns {"error": error message, ...} dictionary

    Raises:
        ValueError: Raised when SIGNATURE environment variable is not set

    Example:
        >>> result = sell("AAPL", 10)
        >>> print(result)  # {"AAPL": 90, "MSFT": 5, "CASH": 15000.0, ...}
        >>> result = sell("600519.SH", 100)  # Chinese A-shares must be multiples of 100
        >>> print(result)  # {"600519.SH": 0, "CASH": 115000.0, ...}
    """
    # Step 1: Get environment variables and basic information
    # Get signature (model name) from environment variable, used to determine data storage path
    signature = get_config_value("SIGNATURE")
    if signature is None:
        raise ValueError("SIGNATURE environment variable is not set")

    # Get current trading date from environment variable
    today_date = get_config_value("TODAY_DATE")

    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        return {"error": "amount must be a positive integer number of shares", "symbol": symbol, "amount": amount}

    # Auto-detect market type based on symbol format
    market = "cn" if symbol.endswith((".SH", ".SZ")) else "us"

    # 🇨🇳 Chinese A-shares trading rule: Must trade in lots of 100 shares (一手 = 100股)
    if market == "cn" and amount % 100 != 0:
        return {
            "error": f"Chinese A-shares must be traded in multiples of 100 shares (1 lot = 100 shares). You tried to sell {amount} shares.",
            "symbol": symbol,
            "amount": amount,
            "date": today_date,
            "suggestion": f"Please use {(amount // 100) * 100} or {((amount // 100) + 1) * 100} shares instead.",
        }

    # Step 2: Get current latest position and operation ID
    # get_latest_position returns two values: position dictionary and current maximum operation ID
    # This ID is used to ensure each operation has a unique identifier
    with _position_lock(signature):
        current_position, current_action_id = get_latest_position(today_date, signature)

        # Step 3: Get stock opening price for the day
        # Use get_open_prices function to get the opening price of specified stock for the day
        # If stock symbol does not exist or price data is missing, KeyError exception will be raised
        try:
            this_symbol_price = get_open_prices(today_date, [symbol], market=market)[f"{symbol}_price"]
        except KeyError:
            # Stock symbol does not exist or price data is missing, return error message
            return {
                "error": f"Symbol {symbol} not found! This action will not be allowed.",
                "symbol": symbol,
                "date": today_date,
            }

        # Step 4: Validate sell conditions
        # Check if holding this stock
        if symbol not in current_position:
            return {
                "error": f"No position for {symbol}! This action will not be allowed.",
                "symbol": symbol,
                "date": today_date,
            }

        # Check if position quantity is sufficient for selling
        if current_position[symbol] < amount:
            return {
                "error": "Insufficient shares! This action will not be allowed.",
                "have": current_position.get(symbol, 0),
                "want_to_sell": amount,
                "symbol": symbol,
                "date": today_date,
            }

        # 🇨🇳 Chinese A-shares T+1 trading rule: Cannot sell shares bought on the same day
        if market == "cn":
            bought_today = _get_today_buy_amount(symbol, today_date, signature)
            if bought_today > 0:
                # Calculate sellable quantity (total position - bought today)
                sellable_amount = current_position[symbol] - bought_today
                if amount > sellable_amount:
                    return {
                        "error": f"T+1 restriction violated! You bought {bought_today} shares of {symbol} today and cannot sell them until tomorrow.",
                        "symbol": symbol,
                        "total_position": current_position[symbol],
                        "bought_today": bought_today,
                        "sellable_today": max(0, sellable_amount),
                        "want_to_sell": amount,
                        "date": today_date,
                    }

        # Step 5: Execute sell operation, update position
        # Create a copy of current position to avoid directly modifying original data
        new_position = current_position.copy()

        # Decrease stock position quantity
        new_position[symbol] -= amount

        # Increase cash balance: sell price × sell quantity
        # Use get method to ensure CASH field exists, default to 0 if not present
        gross_value = money(this_symbol_price * amount)
        commission = calculate_commission(gross_value, "close") if market == "us" else money(0)
        net_proceeds = money(gross_value - commission)
        if net_proceeds < 0:
            return {"error": "Commission exceeds sale proceeds", "symbol": symbol, "date": today_date}
        new_position["CASH"] = float(money(money(new_position.get("CASH", 0)) + net_proceeds))

        # Step 6: Record transaction to position.jsonl file
        # Build file path: {project_root}/data/{log_path}/{signature}/position/position.jsonl
        # Use append mode ("a") to write new transaction record
        # Each operation ID increments by 1, ensuring uniqueness of operation sequence
        log_path = get_config_value("LOG_PATH", "./data/agent_data")
        if log_path.startswith("./data/"):
            log_path = log_path[7:]  # Remove "./data/" prefix
        position_file_path = os.path.join(project_root, "data", log_path, signature, "position", "position.jsonl")
        with open(position_file_path, "a") as f:
            # Write JSON format transaction record, containing date, operation ID and updated position
            print(
                f"Writing to position.jsonl: {json.dumps({'date': today_date, 'id': current_action_id + 1, 'this_action':{'action':'sell','symbol':symbol,'amount':amount},'positions': new_position})}"
            )
            f.write(
                json.dumps(
                    {
                        "date": today_date,
                        "id": current_action_id + 1,
                        "this_action": {"action": "sell", "symbol": symbol, "amount": amount},
                        "positions": new_position,
                        "costs": {
                            "gross_value_usd": float(gross_value),
                            "commission_usd": float(commission),
                            "net_proceeds_usd": float(net_proceeds),
                        },
                    }
                )
                + "\n"
            )

        # Step 7: Return updated position
        write_config_value("IF_TRADE", True)
        return new_position


@mcp.tool()
def buy_by_amount(
    symbol: str,
    amount_usd: float,
    signature: str,
    today_date: str,
    product_type: str = "real_stock",
    log_path: str = "./data/agent_data",
) -> Dict[str, Any]:
    """Paper-buy a fractional US position using a USD notional.

    ``amount_usd`` is the asset exposure. Commission is charged in addition to
    that amount. Context is explicit so an MCP service cannot write to another
    model's portfolio through stale process environment variables.
    """
    symbol = symbol.strip().upper()
    if not symbol or symbol.endswith((".SH", ".SZ")):
        return {"error": "Only US symbols are supported", "symbol": symbol}
    if not signature or not today_date:
        return {"error": "signature and today_date are required"}

    try:
        amount_value = money(amount_usd)
        estimate = validate_trade_value(amount_value, product_type)
    except (ValueError, TypeError) as exc:
        return {"error": str(exc), "symbol": symbol, "amount_usd": amount_usd}

    with _position_lock(signature):
        current_position, current_action_id = get_latest_position(today_date, signature)
        price_result = get_open_prices(today_date, [symbol], market="us")
        price = price_result.get(f"{symbol}_price")
        if price is None or price <= 0:
            return {"error": "No valid reference price", "symbol": symbol, "date": today_date}

        commission = calculate_commission(amount_value, "open", product_type)
        total_cash = money(amount_value + commission)
        current_cash = money(current_position.get("CASH", 0))
        if current_cash < total_cash:
            return {
                "error": "Insufficient cash",
                "required_cash": float(total_cash),
                "cash_available": float(current_cash),
                "symbol": symbol,
                "date": today_date,
            }

        purchased_quantity = quantity(amount_value / money(price))
        new_position = current_position.copy()
        new_position["CASH"] = float(money(current_cash - total_cash))
        new_position[symbol] = float(quantity(quantity(new_position.get(symbol, 0)) + purchased_quantity))
        action = {
            "action": "buy",
            "symbol": symbol,
            "amount": float(purchased_quantity),
            "amount_usd": float(amount_value),
            "product_type": product_type,
        }
        costs = {
            "reference_price_usd": float(money(price)),
            "gross_value_usd": float(amount_value),
            "commission_usd": float(commission),
            "cash_used_usd": float(total_cash),
            "estimated_round_trip_cost_usd": float(estimate["total_cost"]),
            "estimated_round_trip_cost_pct": float(estimate["cost_pct"]),
        }
        _append_transaction(
            _position_file_path(signature, log_path),
            today_date,
            current_action_id + 1,
            action,
            new_position,
            costs,
        )
        return {"positions": new_position, "action": action, "costs": costs}


@mcp.tool()
def sell_by_amount(
    symbol: str,
    amount_usd: float,
    signature: str,
    today_date: str,
    product_type: str = "real_stock",
    log_path: str = "./data/agent_data",
) -> Dict[str, Any]:
    """Paper-sell a fractional US position using a target USD notional."""
    symbol = symbol.strip().upper()
    if not symbol or symbol.endswith((".SH", ".SZ")):
        return {"error": "Only US symbols are supported", "symbol": symbol}
    if not signature or not today_date:
        return {"error": "signature and today_date are required"}

    try:
        amount_value = money(amount_usd)
        if amount_value <= 0:
            raise ValueError("amount_usd must be greater than zero")
        # Cost thresholds are entry gates, not exit gates. A risk-reducing sale
        # must not be blocked merely because a now-small position is expensive
        # to close.
        calculate_commission(amount_value, "close", product_type)
    except (ValueError, TypeError) as exc:
        return {"error": str(exc), "symbol": symbol, "amount_usd": amount_usd}

    with _position_lock(signature):
        current_position, current_action_id = get_latest_position(today_date, signature)
        price_result = get_open_prices(today_date, [symbol], market="us")
        price = price_result.get(f"{symbol}_price")
        if price is None or price <= 0:
            return {"error": "No valid reference price", "symbol": symbol, "date": today_date}

        sale_quantity = quantity(amount_value / money(price))
        held_quantity = quantity(current_position.get(symbol, 0))
        if held_quantity < sale_quantity:
            return {
                "error": "Insufficient shares",
                "held_quantity": float(held_quantity),
                "requested_quantity": float(sale_quantity),
                "symbol": symbol,
                "date": today_date,
            }

        commission = calculate_commission(amount_value, "close", product_type)
        net_proceeds = money(amount_value - commission)
        if net_proceeds <= 0:
            return {"error": "Commission consumes sale proceeds", "symbol": symbol, "date": today_date}

        new_position = current_position.copy()
        new_position[symbol] = float(quantity(held_quantity - sale_quantity))
        new_position["CASH"] = float(money(money(current_position.get("CASH", 0)) + net_proceeds))
        action = {
            "action": "sell",
            "symbol": symbol,
            "amount": float(sale_quantity),
            "amount_usd": float(amount_value),
            "product_type": product_type,
        }
        costs = {
            "reference_price_usd": float(money(price)),
            "gross_value_usd": float(amount_value),
            "commission_usd": float(commission),
            "net_proceeds_usd": float(net_proceeds),
        }
        _append_transaction(
            _position_file_path(signature, log_path),
            today_date,
            current_action_id + 1,
            action,
            new_position,
            costs,
        )
        return {"positions": new_position, "action": action, "costs": costs}


if __name__ == "__main__":
    # new_result = buy("AAPL", 1)
    # print(new_result)
    # new_result = sell("AAPL", 1)
    # print(new_result)
    port = int(os.getenv("TRADE_HTTP_PORT", "8002"))
    mcp.run(transport="streamable-http", port=port)
