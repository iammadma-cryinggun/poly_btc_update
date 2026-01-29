"""
Polymarket 做市策略 - 简化版

吸取教训：
1. 不要重复造轮子 - 利用 NautilusTrader 的能力
2. 保持简单 - 像旧项目一样
3. 专注策略 - 做市算法才是核心

运行: python run_simple_v2.py
"""

import os
import sys
import json
import requests
from pathlib import Path
from decimal import Decimal

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def load_env():
    """加载私钥"""
    private_key = os.getenv("POLYMARKET_PK")
    if not private_key:
        env_file = project_root / ".env"
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('POLYMARKET_PK='):
                        private_key = line.split('=', 1)[1].strip()
                        break
    return private_key


def get_market_info(slug: str):
    """从 Gamma API 获取市场信息"""
    url = f"https://gamma-api.polymarket.com/markets/slug/{slug}"

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()

        market = response.json()
        condition_id = market.get('conditionId')
        token_ids = json.loads(market.get('clobTokenIds', '[]'))
        token_id = token_ids[0] if token_ids else None
        question = market.get('question', 'Market')

        if not all([condition_id, token_id]):
            raise ValueError("市场信息不完整")

        return condition_id, token_id, question

    except Exception as e:
        print(f"[WARN] Gamma API 失败: {str(e)[:60]}")
        return None


def main():
    """主函数 - 简单直接"""
    print("=" * 80)
    print("Polymarket 做市策略 - 简化版")
    print("=" * 80)

    # 1. 加载私钥
    private_key = load_env()
    if not private_key:
        print("\n[ERROR] 未找到私钥")
        print("\n请在 .env 文件中配置:")
        print("  POLYMARKET_PK=0x...")
        return 1

    print(f"\n[OK] 私钥已加载: {private_key[:10]}...{private_key[-6:]}")

    # 2. 获取市场信息
    slug = "bitcoin-up-or-down-on-january-29"
    print(f"\n[INFO] 目标市场: {slug}")
    print(f"[INFO] URL: https://polymarket.com/event/{slug}")

    market_info = get_market_info(slug)

    if market_info:
        # 成功获取
        condition_id, token_id, question = market_info
        print(f"[OK] 成功获取市场信息")
        print(f"    Question: {question[:80]}...")
    else:
        # 失败：使用备用
        print("\n[INFO] 使用备用市场配置...")
        condition_id = "0xe0b7a1ce4f6e211dcf7cd02cfe36f9dc374968510baa7f8e40919c9dca642ae8"
        token_id = "50164777809036667758693066076712603672701101684119148869469668706170865082333"
        question = "BTC market (fallback)"
        print("[WARN] 这可能不是最新的市场")

    # 3. 导入并启动
    print("\n[INFO] 导入 NautilusTrader...")

    try:
        from nautilus_trader.adapters.polymarket import (
            POLYMARKET,
            PolymarketDataClientConfig,
            PolymarketExecClientConfig,
            PolymarketLiveDataClientFactory,
            PolymarketLiveExecClientFactory,
        )
        from nautilus_trader.adapters.polymarket.common.symbol import get_polymarket_instrument_id
        from nautilus_trader.config import InstrumentProviderConfig, LoggingConfig, TradingNodeConfig, StrategyConfig
        from nautilus_trader.live.node import TradingNode
        from nautilus_trader.model.identifiers import TraderId
        from strategies.market_making_strategy import MarketMakingStrategy

        # 创建 instrument_id
        instrument_id = get_polymarket_instrument_id(condition_id, token_id)
        print(f"[OK] Instrument ID: {instrument_id}")

        # 创建策略配置（小资金优化：10-50 USDC）
        class MarketMakingConfig(StrategyConfig, frozen=True):
            instrument_id: str

            # 价差设置
            base_spread: Decimal = Decimal("0.02")  # 2% 基础价差
            min_spread: Decimal = Decimal("0.005")  # 0.5% 最小价差
            max_spread: Decimal = Decimal("0.10")   # 10% 最大价差

            # 订单设置（小资金优化）
            order_size: int = 5              # 每单 5 个（约 2.5 USDC）
            min_order_size: int = 3          # 最小 3 个
            max_order_size: int = 15         # 最大 15 个（约 7.5 USDC）

            # 库存设置（小资金优化）
            target_inventory: int = 0        # 市场中性
            max_inventory: int = 25          # 最大 25 个（约 12.5 USDC）
            inventory_skew_factor: Decimal = Decimal("0.0003")
            max_skew: Decimal = Decimal("0.05")
            hedge_threshold: int = 10        # 持有 10 个以上对冲
            hedge_size: int = 5              # 对冲 5 个

            # 价格范围
            min_price: Decimal = Decimal("0.05")
            max_price: Decimal = Decimal("0.95")

            # 波动率控制
            max_volatility: Decimal = Decimal("0.08")  # 8% 最大波动率
            volatility_window: int = 50

            # 资金管理（小资金优化）
            max_position_ratio: Decimal = Decimal("0.5")   # 最多用 50% 资金
            max_daily_loss: Decimal = Decimal("-5.0")      # 日亏损 -5 USDC（10%）

            # 行为控制
            update_interval_ms: int = 2000    # 2 秒更新（更快响应）
            use_inventory_skew: bool = True
            use_dynamic_spread: bool = True

        config = MarketMakingConfig(instrument_id=str(instrument_id))

        # 创建 TradingNode
        print("\n[INFO] 创建 TradingNode...")

        node_config = TradingNodeConfig(
            trader_id=TraderId("POLYMARKET-001"),
            data_clients={
                POLYMARKET: PolymarketDataClientConfig(
                    private_key=private_key,
                    signature_type=2,  # Magic Wallet
                    instrument_provider=InstrumentProviderConfig(
                        load_ids=frozenset([str(instrument_id)])
                    ),
                ),
            },
            exec_clients={
                POLYMARKET: PolymarketExecClientConfig(
                    private_key=private_key,
                    signature_type=2,
                ),
            },
            logging=LoggingConfig(log_level="INFO"),
        )

        node = TradingNode(config=node_config)
        strategy = MarketMakingStrategy(config)
        node.trader.add_strategy(strategy)
        node.add_data_client_factory(POLYMARKET, PolymarketLiveDataClientFactory)
        node.add_exec_client_factory(POLYMARKET, PolymarketLiveExecClientFactory)
        node.build()

        print("[OK] TradingNode 创建成功")
        print("[OK] 策略已添加")

        print("\n" + "=" * 80)
        print("准备启动")
        print("=" * 80)
        print(f"市场: {slug}")
        print(f"Question: {question[:80]}...")
        print()
        print("[INFO] NautilusTrader 会自动处理:")
        print("  - 连接到 Polymarket API")
        print("  - 获取订单簿数据")
        print("  - 提交和管理订单")
        print("  - 计算二元期权盈亏")
        print()
        print("[INFO] 策略专注于:")
        print("  - 做市算法")
        print("  - 价差计算")
        print("  - 库存管理")
        print("  - 风险控制")
        print()
        print("[WARN] 这是真实交易模式！")
        print("[WARN] 按 Ctrl+C 停止")
        print("=" * 80)

        # 启动
        node.run()

    except KeyboardInterrupt:
        print("\n\n[INFO] 正在停止...")
        node.dispose()
        print("[OK] 已停止")
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
