"""
做市策略 - 小资金安全测试版

资金：5-10 USDC
风险：日亏损 1 USDC 即停止
目标：验证策略可行性

运行方法：
    python run_market_making_safe.py
"""

import os
import sys
import json
import asyncio
import requests
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone, timedelta

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def load_env():
    """加载环境变量 - 优先使用环境变量（Zeabur）"""
    env_vars = {
        'private_key': None,
        'api_key': None,
        'api_secret': None,
        'passphrase': None,
    }

    # 1. 优先从环境变量读取（Zeabur）
    env_vars['private_key'] = os.getenv("POLYMARKET_PK")
    env_vars['api_key'] = os.getenv("POLYMARKET_API_KEY")
    env_vars['api_secret'] = os.getenv("POLYMARKET_API_SECRET")
    env_vars['passphrase'] = os.getenv("POLYMARKET_PASSPHRASE")

    if env_vars['private_key']:
        return env_vars

    # 2. 尝试从 .env 文件读取（本地开发）
    env_file = project_root / ".env"
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    if key == "POLYMARKET_PK":
                        env_vars['private_key'] = value
                    elif key == "POLYMARKET_API_KEY":
                        env_vars['api_key'] = value
                    elif key == "POLYMARKET_API_SECRET":
                        env_vars['api_secret'] = value
                    elif key == "POLYMARKET_PASSPHRASE":
                        env_vars['passphrase'] = value

    return env_vars


def get_market_info(slug: str):
    """从 Polymarket Gamma API 获取市场信息"""
    url = f"https://gamma-api.polymarket.com/markets/slug/{slug}"

    print(f"[INFO] 正在获取市场信息...")
    print(f"[INFO] URL: {url}")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        market = response.json()

        condition_id = market.get('conditionId')
        question = market.get('question')
        token_ids_str = market.get('clobTokenIds', '[]')
        token_ids = json.loads(token_ids_str) if token_ids_str else []

        if not token_ids:
            raise ValueError("市场没有 token IDs")

        token_id = token_ids[0]  # YES token

        print(f"[OK] 成功获取市场信息")
        print(f"   Question: {question}")
        print(f"   Condition ID: {condition_id}")
        print(f"   Token ID: {token_id}")

        return condition_id, token_id, question

    except Exception as e:
        print(f"[ERROR] 获取市场信息失败: {e}")
        raise


def main():
    """主函数"""
    print("=" * 80)
    print("Polymarket 做市策略 - 小资金安全测试")
    print("=" * 80)

    # 加载环境变量
    env_vars = load_env()
    if not env_vars['private_key']:
        print("[ERROR] 未找到私钥！请在 .env 文件中配置 POLYMARKET_PK")
        return 1

    private_key = env_vars['private_key']
    api_key = env_vars['api_key']
    api_secret = env_vars['api_secret']
    passphrase = env_vars['passphrase']

    print(f"\n[OK] 私钥已加载: {private_key[:10]}...{private_key[-6:]}")
    if api_key:
        print(f"[OK] API Key: {api_key}")
    else:
        print("[WARN] 未找到 API Key - 将使用 L1 认证（交易功能受限）")

    # 目标市场
    target_slug = "bitcoin-up-or-down-on-january-28"
    print(f"\n[INFO] 目标市场: {target_slug}")
    print(f"[INFO] URL: https://polymarket.com/event/{target_slug}")

    # 获取市场信息
    try:
        condition_id, token_id, question = get_market_info(target_slug)
    except Exception as e:
        print(f"\n[ERROR] 无法获取市场信息: {e}")
        print("\n[INFO] 尝试使用备用市场 ID 进行测试...")

        # 使用已知的市场 ID（来自旧项目的测试数据）
        condition_id = "0xe0b7a1ce4f6e211dcf7cd02cfe36f9dc374968510baa7f8e40919c9dca642ae8"
        token_id = "50164777809036667758693066076712603672701101684119148869469668706170865082333"
        question = "BTC market (fallback for testing)"

        print(f"[OK] 使用备用市场配置:")
        print(f"   Condition ID: {condition_id}")
        print(f"   Token ID: {token_id}")
        print(f"\n[WARN] 这不是目标市场，仅用于测试集成")

    # 导入 NautilusTrader 模块
    try:
        from nautilus_trader.adapters.polymarket import POLYMARKET
        from nautilus_trader.adapters.polymarket import PolymarketDataClientConfig
        from nautilus_trader.adapters.polymarket import PolymarketExecClientConfig
        from nautilus_trader.adapters.polymarket import PolymarketLiveDataClientFactory
        from nautilus_trader.adapters.polymarket import PolymarketLiveExecClientFactory
        from nautilus_trader.adapters.polymarket.common.symbol import get_polymarket_instrument_id
        from nautilus_trader.config import InstrumentProviderConfig
        from nautilus_trader.config import LoggingConfig, TradingNodeConfig, StrategyConfig
        from nautilus_trader.live.node import TradingNode
        from nautilus_trader.model.identifiers import TraderId, Venue, InstrumentId
        from nautilus_trader.portfolio.config import PortfolioConfig
        from strategies.market_making_strategy import MarketMakingStrategy
    except ImportError as e:
        print(f"\n[ERROR] 导入失败: {e}")
        return 1

    # 创建 instrument_id
    print(f"\n[INFO] 正在创建 Instrument ID...")
    instrument_id = get_polymarket_instrument_id(condition_id, token_id)
    print(f"[OK] Instrument ID: {instrument_id}")

    # 创建策略配置
    class MarketMakingSafeConfig(StrategyConfig, frozen=True):
        instrument_id: InstrumentId
        base_spread: Decimal
        min_spread: Decimal
        max_spread: Decimal
        order_size: int
        min_order_size: int
        max_order_size: int
        target_inventory: int
        max_inventory: int
        inventory_skew_factor: Decimal
        max_skew: Decimal
        hedge_threshold: int
        hedge_size: int
        min_price: Decimal
        max_price: Decimal
        max_volatility: Decimal
        volatility_window: int
        max_position_ratio: Decimal
        max_daily_loss: Decimal
        update_interval_ms: int
        use_inventory_skew: bool
        use_dynamic_spread: bool

    # 小资金安全配置（5-10 USDC）
    config = MarketMakingSafeConfig(
        instrument_id=instrument_id,
        base_spread=Decimal("0.05"),      # 5% 价差（提高利润率）
        min_spread=Decimal("0.03"),      # 3% 最小价差
        max_spread=Decimal("0.20"),      # 20% 最大价差
        order_size=1,                    # 每单 1 个（极小）
        min_order_size=1,                # 最小 1 个
        max_order_size=2,                # 最大 2 个
        target_inventory=0,              # 目标库存（中性）
        max_inventory=5,                 # 最大库存 5 个（极小）
        inventory_skew_factor=Decimal("0.0003"),  # 更强的倾斜
        max_skew=Decimal("0.05"),        # 5% 最大倾斜
        hedge_threshold=3,               # 3 个就开始对冲
        hedge_size=2,                    # 对冲 2 个
        min_price=Decimal("0.05"),       # 5%
        max_price=Decimal("0.95"),       # 95%
        max_volatility=Decimal("0.08"),  # 8% 波动率限制（更严格）
        volatility_window=50,
        max_position_ratio=Decimal("0.5"),   # 50% 资金利用率
        max_daily_loss=Decimal("-1.0"),      # -1 USDC 日亏损限制（极小）
        update_interval_ms=5000,         # 5 秒更新（降低网络要求）
        use_inventory_skew=True,
        use_dynamic_spread=True,
    )

    print("\n" + "=" * 80)
    print("策略配置（小资金安全测试 - 5-10 USDC）")
    print("=" * 80)
    print(f"  市场: {target_slug}")
    print(f"  Question: {question}")
    print(f"  订单大小: {config.order_size} 个")
    print(f"  最大库存: {config.max_inventory} 个")
    print(f"  基础价差: {config.base_spread*100:.1f}%")
    print(f"  日亏损限制: {config.max_daily_loss} USDC")
    print(f"  更新频率: {config.update_interval_ms/1000:.1f} 秒")
    print("=" * 80)
    print("\n[安全提示]")
    print("  - 资金需求: ~5 USDC")
    print("  - 预期日收益: 0.5-1 USDC（理论值）")
    print("  - 风险: 最大亏损 1 USDC")
    print("  - 运行时间: 建议先跑 1-2 小时观察")
    print("=" * 80)

    # 创建数据客户端配置
    data_client_config = PolymarketDataClientConfig(
        private_key=private_key,
        signature_type=2,  # 邮箱/Magic 用户使用 type 2
        instrument_provider=InstrumentProviderConfig(
            load_ids=frozenset([str(instrument_id)])
        ),
    )

    # 创建执行客户端配置
    exec_client_config = PolymarketExecClientConfig(
        private_key=private_key,
        signature_type=2,  # 邮箱/Magic 用户使用 type 2
        api_key=api_key or "",
        api_secret=api_secret or "",
        passphrase=passphrase or "",
    )

    # 创建日志配置
    logging_config = LoggingConfig(
        log_level="INFO",
        log_colors=True,
    )

    # 创建 TradingNode 配置
    node_config = TradingNodeConfig(
        trader_id=TraderId("POLYMARKET-001"),
        data_clients={
            POLYMARKET: data_client_config,
        },
        exec_clients={
            POLYMARKET: exec_client_config,
        },
        logging=logging_config,
    )

    print("\n[INFO] 正在创建 TradingNode...")

    try:
        # 创建 TradingNode
        node = TradingNode(config=node_config)

        # 创建策略
        strategy = MarketMakingStrategy(config)

        # 添加策略到 trader
        node.trader.add_strategy(strategy)

        # 注册 client factories
        node.add_data_client_factory(POLYMARKET, PolymarketLiveDataClientFactory)
        node.add_exec_client_factory(POLYMARKET, PolymarketLiveExecClientFactory)

        # 构建节点
        node.build()

        print("[OK] TradingNode 创建成功")
        print(f"[OK] 策略已添加")

        print("\n" + "=" * 80)
        print("准备启动")
        print("=" * 80)
        print(f"Instrument ID: {instrument_id}")
        print(f"Condition ID: {condition_id}")
        print(f"Token ID: {token_id}")
        print(f"市场: {target_slug}")
        print()
        print("[WARN] 这是真实交易模式！")
        print("[WARN] 建议先运行 1-2 小时观察策略表现")
        print("[WARN] 按 Ctrl+C 停止")
        print("=" * 80)

        # 启动节点
        node.run()

    except KeyboardInterrupt:
        print("\n\n[INFO] 正在停止策略...")
        node.dispose()
        print("[OK] 策略已停止")

        # 打印统计
        print("\n" + "=" * 80)
        print("最终统计")
        print("=" * 80)

        # 获取账户信息
        account = node.portfolio.account_for_venue(Venue("POLYMARKET"))
        if account:
            print(f"总盈亏: {account.realized_pnl() + account.unrealized_pnl()}")
            print(f"已实现盈亏: {account.realized_pnl()}")
            print(f"未实现盈亏: {account.unrealized_pnl()}")

        print("=" * 80)

        return 0

    except Exception as e:
        print(f"\n[ERROR] 启动失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n已停止")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
