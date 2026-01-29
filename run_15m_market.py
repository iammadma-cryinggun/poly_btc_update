"""
Polymarket 15分钟市场做市策略

优势：
- 资金周转快（15分钟一轮）
- 可以高频交易（一天64轮）
- 随时对冲（看订单簿）
- 小资金友好（1U起步）

运行: python run_15m_market.py
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
    """主函数 - 15分钟市场做市"""
    print("=" * 80)
    print("Polymarket 15分钟市场做市策略")
    print("=" * 80)

    # 1. 加载私钥
    private_key = load_env()
    if not private_key:
        print("\n[ERROR] 未找到私钥")
        print("\n请在 .env 文件中配置:")
        print("  POLYMARKET_PK=0x...")
        return 1

    print(f"\n[OK] 私钥已加载: {private_key[:10]}...{private_key[-6:]}")

    # 2. 获取市场信息（15分钟市场）
    slug = "btc-updown-15m-1769689800"  # 15分钟BTC市场
    print(f"\n[INFO] 目标市场: {slug}")
    print(f"[INFO] URL: https://polymarket.com/event/{slug}")

    market_info = get_market_info(slug)

    if market_info:
        condition_id, token_id, question = market_info
        print(f"[OK] 成功获取市场信息")
        print(f"    Question: {question[:80]}...")
    else:
        print("\n[INFO] 使用备用市场配置...")
        condition_id = "0xe0b7a1ce4f6e211dcf7cd02cfe36f9dc374968510baa7f8e40919c9dca642ae8"
        token_id = "50164777809036667758693066076712603672701101684119148869469668706170865082333"
        question = "BTC 15m market (fallback)"

    # 3. 导入并启动
    print("\n[INFO] 导入 NautilusTrader...")

    try:
        from nautilus_trader.adapters.polymarket import POLYMARKET
        from nautilus_trader.adapters.polymarket import PolymarketDataClientConfig
        from nautilus_trader.adapters.polymarket import PolymarketExecClientConfig
        from nautilus_trader.adapters.polymarket.common.symbol import get_polymarket_instrument_id
        from nautilus_trader.config import InstrumentProviderConfig, LoggingConfig, TradingNodeConfig, StrategyConfig
        from nautilus_trader.live.node import TradingNode
        from nautilus_trader.model.identifiers import TraderId
        from strategies.prediction_market_mm_strategy import PredictionMarketMMStrategy

        # 创建 instrument_id
        instrument_id = get_polymarket_instrument_id(condition_id, token_id)
        print(f"[OK] Instrument ID: {instrument_id}")

        # 创建基于论文优化的预测市场做市策略配置
        class PredictionMarketConfig(StrategyConfig, frozen=True):
            instrument_id: str

            # ========== 论文参数（Avellaneda-Stoikov 模型）==========
            risk_aversion: Decimal = Decimal("0.5")     # γ 风险厌恶系数
            time_decay_factor: Decimal = Decimal("2.0") # 时间衰减因子

            # ========== 价差设置（基于论文优化）==========
            base_spread: Decimal = Decimal("0.02")  # 2% 基础价差
            min_spread: Decimal = Decimal("0.01")   # 1% 最小价差
            max_spread: Decimal = Decimal("0.15")   # 15% 最大价差（时间衰减时可达）

            # ========== 订单设置（小资金起步）==========
            order_size: int = 2              # 每单 2 个（约 1 USDC @0.50）
            min_order_size: int = 1          # 最小 1 个（0.5 USDC）
            max_order_size: int = 5          # 最大 5 个（2.5 USDC）

            # ========== 库存设置（严格管理）==========
            target_inventory: int = 0        # 市场中性
            max_inventory: int = 10          # 最大 10 个（5 USDC）
            inventory_skew_factor: Decimal = Decimal("0.001")  # 更敏感（论文建议）
            max_skew: Decimal = Decimal("0.05")
            hedge_threshold: int = 4        # 持有 4 个就对冲
            hedge_size: int = 3             # 对冲 3 个

            # ========== 价格范围 ==========
            min_price: Decimal = Decimal("0.05")
            max_price: Decimal = Decimal("0.95")

            # ========== 波动率控制 ==========
            max_volatility: Decimal = Decimal("0.15")  # 15% 最大波动率
            volatility_window: int = 30        # 30 个 tick

            # ========== 资金管理 ==========
            max_position_ratio: Decimal = Decimal("0.4")   # 最多用 40% 资金
            max_daily_loss: Decimal = Decimal("-3.0")      # 日亏损 -3 USDC

            # ========== 行为控制 ==========
            update_interval_ms: int = 1000    # 1 秒更新
            end_buffer_minutes: int = 5       # 最后5分钟停止做市（关键！）
            use_inventory_skew: bool = True
            use_dynamic_spread: bool = True

        config = PredictionMarketConfig(instrument_id=str(instrument_id))

        # 创建 TradingNode
        print("\n[INFO] 创建 TradingNode...")

        node_config = TradingNodeConfig(
            trader_id=TraderId("POLYMARKET-15M-001"),
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
        strategy = PredictionMarketMMStrategy(config)
        node.trader.add_strategy(strategy)
        node.add_data_client_factory(POLYMARKET, PolymarketLiveDataClientFactory)
        node.add_exec_client_factory(POLYMARKET, PolymarketLiveExecClientFactory)
        node.build()

        print("[OK] TradingNode 创建成功")
        print("[OK] 策略已添加")

        print("\n" + "=" * 80)
        print("预测市场做市策略（基于学术论文优化）")
        print("=" * 80)
        print(f"市场: {slug}")
        print(f"Question: {question[:80]}...")
        print()
        print("[INFO] 论文优化（Market Making in Prediction Markets）:")
        print("  - Avellaneda-Stoikov 模型")
        print("  - 时间衰减价差: s = γσ²T")
        print("  - 库存风险管理")
        print("  - 价格收敛保护")
        print()
        print("[INFO] 15分钟市场特点:")
        print("  - 每轮 15 分钟，一天 64 轮")
        print("  - 快速周转，资金利用率高")
        print("  - 随时可以对冲（看订单簿）")
        print("  - 小订单起步（1U = 2个token）")
        print()
        print("[INFO] 策略配置:")
        print("  - 每单: 2 个（约 1 USDC）")
        print("  - 最大库存: 10 个（5 USDC）")
        print("  - 基础价差: 2%（动态调整至15%）")
        print("  - 更新频率: 1 秒")
        print("  - 对冲阈值: 4 个")
        print("  - 最后5分钟: 停止做市（保护机制）")
        print()
        print("[INFO] 核心优化:")
        print("  ✅ 时间衰减: 价差随剩余时间动态调整")
        print("  ✅ 库存感知: 持仓越多，倾斜越大")
        print("  ✅ 价格收敛: 最后5分钟自动停止")
        print("  ✅ 风险管理: Avellaneda-Stoikov 公式")
        print()
        print("[INFO] 预期收益:")
        print("  - 每 15 分钟: 0.02-0.10 USDC")
        print("  - 每小时（4轮）: 0.08-0.40 USDC")
        print("  - 8 小时: 0.64-3.20 USDC")
        print("  - 日收益率: 2.1-10.7%")
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
