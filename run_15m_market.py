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
    """加载私钥并推导钱包地址"""
    private_key = os.getenv("POLYMARKET_PK")
    if not private_key:
        env_file = project_root / ".env"
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('POLYMARKET_PK='):
                        private_key = line.split('=', 1)[1].strip()
                        break

    # 从私钥推导钱包地址并设置环境变量
    if private_key:
        try:
            from eth_account import Account
            account = Account.from_key(private_key)
            address = account.address
            os.environ['POLYMARKET_FUNDER'] = address
            print(f"[DEBUG] 钱包地址已推导: {address}")
        except Exception as e:
            print(f"[WARN] 无法推导钱包地址: {e}")

    return private_key


def ensure_api_credentials(private_key: str):
    """确保 API 凭证存在（优先使用环境变量，否则自动生成）"""
    # 先检查是否已配置
    api_key = os.getenv('POLYMARKET_API_KEY')
    api_secret = os.getenv('POLYMARKET_API_SECRET')
    passphrase = os.getenv('POLYMARKET_PASSPHRASE')

    if all([api_key, api_secret, passphrase]):
        print(f"[OK] API 凭证已配置")
        print(f"[DEBUG] API Key: {api_key[:10]}...")
        return True

    # 未配置，自动生成
    print("[INFO] API 凭证未配置，正在自动生成...")
    try:
        from py_clob_client.client import ClobClient

        POLYMARKET_API_URL = "https://clob.polymarket.com"
        POLYMARKET_CHAIN_ID = 137  # Polygon chain ID

        print(f"[DEBUG] 创建 ClobClient...")
        client = ClobClient(
            POLYMARKET_API_URL,
            key=str(private_key),
            signature_type=2,  # Magic Wallet
            chain_id=POLYMARKET_CHAIN_ID,
        )

        print(f"[DEBUG] 调用 create_or_derive_api_creds...")
        api_creds = client.create_or_derive_api_creds()

        if api_creds:
            # ApiCreds 字段名是 api_key, api_secret, api_passphrase（下划线）
            os.environ['POLYMARKET_API_KEY'] = api_creds.api_key
            os.environ['POLYMARKET_API_SECRET'] = api_creds.api_secret
            os.environ['POLYMARKET_PASSPHRASE'] = api_creds.api_passphrase

            print(f"[OK] API 凭证已生成")
            print(f"[DEBUG] API Key: {os.environ['POLYMARKET_API_KEY'][:10]}...")
            return True
        else:
            print("[ERROR] 无法生成 API 凭证")
            return False

    except Exception as e:
        import traceback
        print(f"[ERROR] API 凭证生成失败: {e}")
        print(f"[ERROR] 详细错误: {traceback.format_exc()[:500]}")
        return False


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


def get_latest_15m_btc_market():
    """使用时间差逻辑查找最新的 15分钟 BTC 市场（健壮版）"""
    from datetime import datetime, timezone, timedelta
    import dateutil.parser

    try:
        # 使用 Gamma API 的 events 端点
        url = "https://gamma-api.polymarket.com/events"
        params = {
            "closed": "false",      # 只看活跃市场
            "tags": "Bitcoin",      # 标签过滤
            "limit": 20,            # 获取最近的市场
            "order": "endDate:asc"  # 按结束时间升序排列
        }

        # 打印容器当前时间，检查时间漂移
        now = datetime.now(timezone.utc)
        print(f"[SYSTEM] 容器当前时间 (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"[INFO] 查询 Gamma API events...")

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        events = response.json()

        if not events:
            print("[WARN] API 返回空列表，可能是网络问题或API维护")
            return None

        print(f"[OK] 找到 {len(events)} 个活跃 BTC 市场")

        # 放宽时间窗口：1分钟 到 60分钟（避免市场真空期崩溃）
        MIN_SECONDS = 60     # 1 分钟
        MAX_SECONDS = 3600   # 60 分钟

        print(f"[INFO] 时间窗口: {MIN_SECONDS/60:.0f}-{MAX_SECONDS/60:.0f} 分钟")
        print(f"[DEBUG] 正在分析最近的 5 个市场:")
        print(f"[INFO] 查找目标: 'Bitcoin >' 开头的行权价格市场")

        candidates = []

        # 收集所有 "Bitcoin >" 市场（用于价格排序）
        all_strike_markets = []

        # 遍历所有市场，详细打印前5个
        for i, event in enumerate(events[:5]):
            title = event.get('title', 'No Title')
            end_date_str = event.get('endDate')

            if not end_date_str:
                continue

            end_date = dateutil.parser.isoparse(end_date_str)
            diff_seconds = (end_date - now).total_seconds()
            diff_minutes = diff_seconds / 60

            print(f"  {i+1}. {title[:60]}")
            print(f"     -> 结束时间: {end_date.strftime('%H:%M:%S')} | 剩余: {diff_minutes:.2f} 分钟")

            # 筛选逻辑：必须是 "Bitcoin >" 开头（行权价格市场）且 在时间窗口内
            if "Bitcoin >" in title and MIN_SECONDS < diff_seconds < MAX_SECONDS:
                # 尝试提取价格（例如从 "Bitcoin > $102,500 on Jan 29?" 中提取 102500）
                import re
                price_match = re.search(r'\$([0-9,]+)', title)
                price = int(price_match.group(1).replace(',', '')) if price_match else 0

                candidates.append({
                    "title": title,
                    "diff": diff_seconds,
                    "event": event,
                    "price": price
                })

                all_strike_markets.append({
                    "title": title,
                    "diff": diff_seconds,
                    "event": event,
                    "price": price
                })

        # 如果没有找到符合窗口的市场，打印所有市场信息
        if not candidates:
            print(f"\n[WARN] 未找到符合时间窗口 ({MIN_SECONDS/60:.0f}-{MAX_SECONDS/60:.0f}分钟) 的市场")
            print(f"[DEBUG] 正在打印所有返回的市场信息:")

            all_valid = []
            for event in events:
                title = event.get('title', '')
                end_date_str = event.get('endDate')
                if not end_date_str:
                    continue

                end_date = dateutil.parser.isoparse(end_date_str)
                diff_seconds = (end_date - now).total_seconds()

                # 收集所有未来的 "Bitcoin >" 行权价格市场
                if "Bitcoin >" in title and diff_seconds > 0:
                    # 提取价格
                    import re
                    price_match = re.search(r'\$([0-9,]+)', title)
                    price = int(price_match.group(1).replace(',', '')) if price_match else 0

                    all_valid.append({
                        "title": title,
                        "diff": diff_seconds,
                        "event": event,
                        "price": price
                    })

            if not all_valid:
                print("[ERROR] 没有任何未来的 'Bitcoin >' 行权价格市场")
                print("[INFO] 注意：前端显示的 'Bitcoin Up or Down' 是 UI 聚合名称")
                print("[INFO] API 里实际存储的是 'Bitcoin > $XXX' 这样的行权价格市场")
                return None

            # 找到最近的一个（即使是短于1分钟的）
            best = all_valid[0]
            print(f"\n[INFO] 最近的有效市场:")
            print(f"  标题: {best['title']}")
            print(f"  行权价格: ${best['price']:,}" if best['price'] > 0 else "")
            print(f"  剩余时间: {best['diff']/60:.2f} 分钟")

            # 如果剩余时间太短，给出警告
            if best['diff'] < 60:
                print("[WARN] 该市场将在 1 分钟内结束，属于超短线！")
                print("[WARN] 建议等待下一个市场")
                return None

            candidates.append(best)

        # 选择最佳市场（优先选择价格居中的市场 - At-The-Money）
        if len(candidates) > 1:
            # 按价格排序
            candidates_sorted_by_price = sorted(candidates, key=lambda x: x['price'])
            # 选择价格居中的（平值期权流动性最好）
            middle_index = len(candidates_sorted_by_price) // 2
            best_match = candidates_sorted_by_price[middle_index]

            print(f"[INFO] 找到 {len(candidates)} 个符合时间窗口的市场")
            print(f"[INFO] 按行权价格排序，选择平值期权（价格居中）")
            print(f"[DEBUG] 价格范围: ${candidates_sorted_by_price[0]['price']:,} - ${candidates_sorted_by_price[-1]['price']:,}")
        else:
            best_match = candidates[0]

        minutes_left = best_match['diff'] / 60

        print(f"\n[OK] ✅ 锁定市场!")
        print(f"[INFO] 标题: {best_match['title']}")
        print(f"[INFO] 行权价格: ${best_match['price']:,}" if best_match['price'] > 0 else "")
        print(f"[INFO] 剩余时间: {minutes_left:.2f} 分钟")

        # 智能判断市场类型
        if minutes_left < 5:
            print("[WARN] 注意：该市场将在 5 分钟内结束，属于超短线！")
        elif minutes_left > 30:
            print("[WARN] 注意：这是一个长周期市场 (>30分钟)")
        else:
            print("[INFO] ✅ 这是一个标准的短周期市场 (5-30分钟)")

        # 提取市场信息
        markets = best_match['event'].get('markets', [])
        if not markets:
            print("[ERROR] Event 中没有市场数据")
            return None

        market = markets[0]
        condition_id = market.get('conditionId')
        clob_token_ids_str = market.get('clobTokenIds', '[]')
        token_ids = json.loads(clob_token_ids_str)
        slug = market.get('slug', '')

        if not all([condition_id, token_ids]):
            print("[ERROR] 市场信息不完整")
            return None

        print(f"[INFO] URL: https://polymarket.com/event/{slug}")
        print(f"[DEBUG] Condition ID: {condition_id}")
        print(f"[DEBUG] Token ID: {token_ids[0]}")

        return condition_id, token_ids[0], best_match['title'], slug

    except Exception as e:
        print(f"[FATAL] 查询失败: {str(e)}")
        import traceback
        print(f"[DEBUG] 详细错误: {traceback.format_exc()[:800]}")
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

    # 2. 确保 API 凭证存在（自动生成如果未配置）
    print("\n[INFO] 检查 API 凭证...")
    if not ensure_api_credentials(private_key):
        print("\n[ERROR] API 凭证获取失败，程序退出")
        return 1

    # 3. 获取市场信息（带重试机制）
    print("\n[INFO] 自动查找最新的15分钟BTC市场...")

    import time
    max_retries = 3
    market_info = None

    for attempt in range(max_retries):
        print(f"\n>>> 尝试第 {attempt + 1}/{max_retries} 次市场查找...")

        market_info = get_latest_15m_btc_market()

        if market_info:
            print(f"\n>>> ✅ 成功获取市场信息")
            break
        else:
            if attempt < max_retries - 1:
                wait_time = 10
                print(f">>> ⚠️ 未找到合适市场，等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                print(f"\n[ERROR] 多次尝试后仍无法找到BTC市场")
                print("[INFO] 可能原因：")
                print("  1. 市场真空期（15分钟市场交接间隙）")
                print("  2. API 维护或网络问题")
                print("  3. 当前时间没有活跃的 BTC 市场")
                print(f"\n[INFO] 为了便于调试，程序将休眠 60 秒...")
                time.sleep(60)
                return 1

    condition_id, token_id, question, slug = market_info
    print(f"    Question: {question[:80]}...")
    print(f"[DEBUG] condition_id: {condition_id}")
    print(f"[DEBUG] token_id: {token_id}")
    print(f"[DEBUG] slug: {slug}")

    # 4. 导入并启动
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
        from strategies.prediction_market_mm_strategy import PredictionMarketMMStrategy

        # 创建 instrument_id
        instrument_id = get_polymarket_instrument_id(condition_id, token_id)
        print(f"[OK] Instrument ID: {instrument_id}")
        print(f"[DEBUG] Instrument ID 类型: {type(instrument_id)}")
        print(f"[DEBUG] Instrument ID (字符串): {str(instrument_id)}")

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
                    # 直接内联创建 load_ids，避免变量作用域问题
                    instrument_provider=InstrumentProviderConfig(
                        load_ids=frozenset([str(instrument_id)])
                    ),
                ),
            },
            exec_clients={
                POLYMARKET: PolymarketExecClientConfig(
                    private_key=private_key,
                    signature_type=2,  # Magic Wallet
                ),
            },
            logging=LoggingConfig(log_level="WARNING"),  # 减少日志噪音
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
