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

# ========== 关键修复：应用 py_clob_client 补丁 ==========
# 必须在任何 Polymarket 相关导入之前执行
try:
    from patches import py_clob_client_patch  # noqa: F401
except ImportError:
    print("[WARN] 补丁模块未找到，余额查询可能无法正常工作")

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
            print(f"[DEBUG] Signer address (from private key): {address}")
        except Exception as e:
            print(f"[WARN] Unable to derive address from private key: {e}")

    # ========== 关键修复：检查是否配置了 Proxy 地址 ==========
    proxy_address = os.getenv("POLYMARKET_PROXY_ADDRESS")
    if proxy_address:
        print(f"[OK] Using Proxy/Deposit address: {proxy_address}")
        print(f"[INFO] This is the address where your funds are located!")
        # 如果配置了 Proxy 地址，覆盖 funder
        os.environ['POLYMARKET_FUNDER'] = proxy_address
    else:
        print(f"[WARN] POLYMARKET_PROXY_ADDRESS not configured!")
        print(f"[WARN] Bot will look for funds at Signer address (might be empty)")
        print(f"[INFO] If you see 'insufficient balance', add this to .env:")
        print(f"[INFO]   POLYMARKET_PROXY_ADDRESS=0x18DdcbD977e5b7Ff751A3BAd6F274b67A311CD2d")

    return private_key


def ensure_api_credentials(private_key: str, force_regenerate: bool = False):
    """
    确保 API 凭证存在

    Args:
        private_key: 私钥
        force_regenerate: 是否强制重新生成（忽略环境变量）
    """
    # 检查是否需要强制重新生成
    if force_regenerate:
        print("[INFO] 强制重新生成 API 凭证...")
    else:
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

    # 自动生成（或强制重新生成）
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


def get_next_15m_timestamp():
    """
    计算下一个 15分钟结算点 (00, 15, 30, 45) 的 Unix 时间戳
    """
    from datetime import datetime, timezone, timedelta
    import math

    now = datetime.now(timezone.utc)

    # 将当前分钟向上取整到下一个 15 的倍数
    minutes = now.minute
    next_quarter = math.ceil((minutes + 1) / 15) * 15

    # 如果正好跨小时 (比如现在是 55分，下一个是 60分即下一小时的00分)
    if next_quarter == 60:
        # 加1小时，分钟归0
        target_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    else:
        # 保持当前小时，分钟设为 next_quarter
        target_time = now.replace(minute=next_quarter, second=0, microsecond=0)

    # 返回整数时间戳
    return int(target_time.timestamp())


def get_latest_15m_btc_market():
    """使用时间戳直接定位 15分钟 BTC 市场（作弊码方法）"""
    from datetime import datetime, timezone, timedelta

    print("=" * 80)
    print("Market Discovery via Timestamp (Direct Method)")
    print("=" * 80)

    # 1. 计算目标时间戳
    target_ts = get_next_15m_timestamp()
    target_time = datetime.fromtimestamp(target_ts, tz=timezone.utc)

    print(f"[INFO] Current Time (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[INFO] Target Time (UTC): {target_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[INFO] Target Timestamp: {target_ts}")

    # 2. 构造 Slug
    slug = f"btc-updown-15m-{target_ts}"
    print(f"[INFO] Constructed Slug: {slug}")
    print(f"[INFO] Market URL: https://polymarket.com/event/{slug}")
    print(f"=" * 80)

    # 3. 直接查询 API (使用 slug 参数)
    print(f"\n[INFO] Querying Gamma API...")

    try:
        # 使用 /markets/slug/{slug} 端点
        url = f"https://gamma-api.polymarket.com/markets/slug/{slug}"

        response = requests.get(url, timeout=10)

        if response.status_code == 404:
            print(f"[WARN] Market not found (404)")
            print(f"[INFO] Possible reasons:")
            print(f"  1. Market not yet created (usually created 1-2 hours in advance)")
            print(f"  2. Current time is in a gap period")

            # 尝试下一个时间点
            print(f"\n[INFO] Trying next 15-minute slot (+15min)...")
            next_ts = target_ts + 900  # 加 15 分钟 (900 秒)
            next_slug = f"btc-updown-15m-{next_ts}"
            print(f"[INFO] Next Slug: {next_slug}")
            print(f"[INFO] Next Time: {datetime.fromtimestamp(next_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")

            url = f"https://gamma-api.polymarket.com/markets/slug/{next_slug}"
            response = requests.get(url, timeout=10)

            if response.status_code == 404:
                print(f"[ERROR] Next market also not found")
                return None

        response.raise_for_status()
        market = response.json()

        print(f"\n[OK] Successfully found market!")
        print(f"[INFO] Question: {market.get('question')}")
        print(f"[INFO] End Date: {market.get('endDate')}")

        # 提取核心交易数据
        condition_id = market.get('conditionId')
        clob_token_ids_str = market.get('clobTokenIds', '[]')
        token_ids = json.loads(clob_token_ids_str)
        question = market.get('question', 'Market')

        if not all([condition_id, token_ids]):
            print("[ERROR] Market data incomplete")
            return None

        print(f"[INFO] Condition ID: {condition_id}")
        print(f"[INFO] Token IDs: {token_ids}")
        print(f"[INFO] First Token ID: {token_ids[0]}")

        # 计算剩余时间
        end_date_str = market.get('endDate')
        if end_date_str:
            import dateutil.parser
            end_date = dateutil.parser.isoparse(end_date_str)
            now = datetime.now(timezone.utc)
            minutes_left = (end_date - now).total_seconds() / 60

            print(f"[INFO] Time remaining: {minutes_left:.2f} minutes")

            # ========== 关键优化：自动跳过时间不足的市场 ==========
            MIN_REQUIRED_MINUTES = 10  # 至少需要10分钟才能做市

            if minutes_left < MIN_REQUIRED_MINUTES:
                print(f"\n[SKIP] ⚠️  市场剩余时间不足 ({minutes_left:.1f}分钟 < {MIN_REQUIRED_MINUTES}分钟)")
                print(f"[SKIP] 市场可能已经'僵尸化'（结果已定，流动性枯竭）")
                print(f"[INFO] 自动尝试下一个市场...")

                # 尝试下一个时间点
                next_ts = target_ts + 900  # 加 15 分钟
                next_slug = f"btc-updown-15m-{next_ts}"
                print(f"[INFO] Next Slug: {next_slug}")
                print(f"[INFO] Next End Time: {datetime.fromtimestamp(next_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")

                # 递归调用下一个市场
                url = f"https://gamma-api.polymarket.com/markets/slug/{next_slug}"
                response = requests.get(url, timeout=10)

                if response.status_code == 404:
                    print(f"[ERROR] 下一个市场也不存在，停止尝试")
                    return None

                response.raise_for_status()
                market = response.json()

                print(f"\n[OK] 找到下一个市场!")
                print(f"[INFO] Question: {market.get('question')}")
                print(f"[INFO] End Date: {market.get('endDate')}")

                # 重新提取数据
                condition_id = market.get('conditionId')
                clob_token_ids_str = market.get('clobTokenIds', '[]')
                token_ids = json.loads(clob_token_ids_str)
                question = market.get('question', 'Market')
                slug = next_slug

                # 重新计算剩余时间
                end_date = dateutil.parser.isoparse(market.get('endDate'))
                minutes_left = (end_date - now).total_seconds() / 60
                print(f"[INFO] New market time remaining: {minutes_left:.2f} minutes")

                if not all([condition_id, token_ids]):
                    print("[ERROR] Next market data incomplete")
                    return None

            elif minutes_left < 5:
                print("[WARN] This market will end in less than 5 minutes!")
            elif minutes_left > 30:
                print("[WARN] This is a long-period market (>30min)")
            else:
                print("[INFO] Standard short-period market (5-30min)")
        else:
            print("[WARN] No end date found")

        print(f"=" * 80)

        return condition_id, token_ids[0], question, slug

    except Exception as e:
        print(f"[ERROR] Failed to fetch market: {e}")
        import traceback
        print(f"[DEBUG] Error details: {traceback.format_exc()[:800]}")
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

    # 2. 确保 API 凭证存在（在 Zeabur 上强制重新生成，避免环境变量格式问题）
    print("\n[INFO] 检查 API 凭证...")
    # Zeabur 上强制重新生成，避免环境变量格式问题（比如多余的空格、引号等）
    if not ensure_api_credentials(private_key, force_regenerate=True):
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

            # ========== 订单设置（Polymarket 最小要求）==========
            order_size: int = 5              # 每单 5 个（约 2.5 USDC @0.50）- 最小交易要求
            min_order_size: int = 5          # 最小 5 个（2.5 USDC）
            max_order_size: int = 10         # 最大 10 个（5 USDC）

            # ========== 库存设置（严格管理）==========
            target_inventory: int = 0        # 市场中性
            max_inventory: int = 20          # 最大 20 个（10 USDC）
            inventory_skew_factor: Decimal = Decimal("0.001")  # 更敏感（论文建议）
            max_skew: Decimal = Decimal("0.05")
            hedge_threshold: int = 10        # 持有 10 个就对冲
            hedge_size: int = 5              # 对冲 5 个

            # ========== 价格范围 ==========
            min_price: Decimal = Decimal("0.05")
            max_price: Decimal = Decimal("0.95")

            # ========== 波动率控制 ==========
            max_volatility: Decimal = Decimal("0.50")  # 50% 最大波动率 (Polymarket 二元期权波动大)
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
                    funder=os.getenv('POLYMARKET_FUNDER'),  # 关键：指定 Proxy 地址
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
                    funder=os.getenv('POLYMARKET_FUNDER'),  # 关键：指定 Proxy 地址
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
        print("  - Polymarket 最小订单: 5个token（约2.5 USDC）")
        print()
        print("[INFO] 策略配置:")
        print("  - 每单: 5 个（约 2.5 USDC）- 满足最小交易要求")
        print("  - 最大库存: 20 个（10 USDC）")
        print("  - 基础价差: 2%（动态调整至15%）")
        print("  - 更新频率: 1 秒")
        print("  - 对冲阈值: 10 个")
        print("  - 最后5分钟: 停止做市（保护机制）")
        print()
        print("[INFO] 核心优化:")
        print("  ✅ 时间衰减: 价差随剩余时间动态调整")
        print("  ✅ 库存感知: 持仓越多，倾斜越大")
        print("  ✅ 价格收敛: 最后5分钟自动停止")
        print("  ✅ 风险管理: Avellaneda-Stoikov 公式")
        print()
        print("[INFO] 预期收益:")
        print("  - 每 15 分钟: 0.05-0.25 USDC（每单5个）")
        print("  - 每小时（4轮）: 0.20-1.00 USDC")
        print("  - 8 小时: 1.60-8.00 USDC")
        print("  - 日收益率: 3.2-16%（基于50 USDC资金）")
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
