"""
基于时间戳直接定位 15分钟 BTC 市场

Slug 格式：btc-updown-15m-{unix_timestamp}
其中 timestamp 是市场结束时间的 Unix 时间戳
"""
import requests
from datetime import datetime, timezone, timedelta
import math
import json


def get_next_15m_timestamp():
    """
    计算下一个 15分钟结算点 (00, 15, 30, 45) 的 Unix 时间戳
    """
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


def get_market_by_slug(slug):
    """
    通过 slug 直接查询市场信息
    """
    url = "https://gamma-api.polymarket.com/markets/slug/" + slug

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        market = response.json()

        # 打印市场信息
        print(f"[OK] Successfully found market")
        print(f"[INFO] Question: {market.get('question')}")
        print(f"[INFO] End Date: {market.get('endDate')}")

        # 提取核心交易数据
        condition_id = market.get('conditionId')
        clob_token_ids_str = market.get('clobTokenIds', '[]')
        token_ids = json.loads(clob_token_ids_str)

        print(f"[INFO] Condition ID: {condition_id}")
        print(f"[INFO] Token IDs: {token_ids}")

        return condition_id, token_ids, market.get('question'), slug

    except Exception as e:
        print(f"[ERROR] Failed to fetch market: {e}")
        return None


def get_15m_btc_market_direct():
    """
    直接通过时间戳定位 15分钟 BTC 市场
    """
    print("=" * 80)
    print("Direct Market Discovery via Timestamp")
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

    # 3. 直接查询 API
    print(f"\n[INFO] Querying Gamma API...")

    market_info = get_market_by_slug(slug)

    if market_info:
        print(f"\n[OK] Market found successfully!")
        return market_info
    else:
        print(f"\n[WARN] Market not found")
        print(f"[INFO] Possible reasons:")
        print(f"  1. Market not yet created (usually created 1-2 hours in advance)")
        print(f"  2. URL pattern has changed")
        print(f"  3. Slug format is different")

        # 尝试查找下一个时间点
        print(f"\n[INFO] Trying next 15-minute slot...")
        next_ts = target_ts + 900  # 加 15 分钟 (900 秒)
        next_slug = f"btc-updown-15m-{next_ts}"
        print(f"[INFO] Next Slug: {next_slug}")

        market_info = get_market_by_slug(next_slug)

        if market_info:
            print(f"\n[OK] Found next market!")
            return market_info
        else:
            print(f"\n[ERROR] Unable to find any market")
            return None


if __name__ == "__main__":
    result = get_15m_btc_market_direct()

    if result:
        condition_id, token_ids, question, slug = result
        print(f"\n" + "=" * 80)
        print(f"SUMMARY")
        print(f"=" * 80)
        print(f"Condition ID: {condition_id}")
        print(f"Token IDs: {token_ids}")
        print(f"Slug: {slug}")
        print(f"Question: {question}")
        print(f"=" * 80)
    else:
        print(f"\n[ERROR] Failed to find market")
