"""
精准定位脚本：查找特定 UTC 时间结束的 BTC 市场

用途：发现 API 中真实的 "Bitcoin > XXXXX" 行权价格市场
"""
import requests
from datetime import datetime, timezone
import dateutil.parser
import json

def find_specific_et_market():
    # 设置目标：10:30 AM ET -> 转换为 UTC 是 15:30
    TARGET_HOUR_UTC = 15
    TARGET_MINUTE_UTC = 30

    print(f"[INFO] 正在寻找结束时间严格为 {TARGET_HOUR_UTC}:{TARGET_MINUTE_UTC} UTC (即 10:30 AM ET) 的 BTC 市场...")
    print(f"=" * 80)

    url = "https://gamma-api.polymarket.com/events"
    params = {
        "closed": "false",
        "tags": "Bitcoin",
        "limit": 50,
        "order": "endDate:asc"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        events = response.json()

        print(f"[INFO] API 返回了 {len(events)} 个活跃 BTC 市场")
        print(f"=" * 80)

        found_count = 0
        all_btc_markets = []

        # 先收集所有带 "Bitcoin >" 的市场
        for event in events:
            title = event.get('title', '')
            end_date_str = event.get('endDate')

            if not end_date_str:
                continue

            end_date = dateutil.parser.isoparse(end_date_str)

            # 收集所有 "Bitcoin >" 开头且未过期的市场
            if "Bitcoin >" in title and end_date > datetime.now(timezone.utc):
                all_btc_markets.append({
                    'title': title,
                    'end_date': end_date,
                    'event': event
                })

        print(f"[INFO] 找到 {len(all_btc_markets)} 个 'Bitcoin >' 开头的未过期市场")
        print(f"=" * 80)

        # 按 15 分钟分组显示
        time_slots = {}
        for market in all_btc_markets:
            end_date = market['end_date']
            time_key = f"{end_date.hour:02d}:{end_date.minute:02d}"

            if time_key not in time_slots:
                time_slots[time_key] = []
            time_slots[time_key].append(market)

        # 按时间排序
        sorted_slots = sorted(time_slots.keys())

        print(f"\n[INFO] 按结束时间分组 (UTC):")
        print(f"=" * 80)

        for time_slot in sorted_slots[:5]:  # 只显示前 5 个时间段
            markets = time_slots[time_slot]
            print(f"\n[TIME] {time_slot} UTC 结束的市场 (共 {len(markets)} 个):")

            for i, m in enumerate(markets[:3]):  # 每个时间段最多显示 3 个
                print(f"  {i+1}. {m['title']}")
                markets_data = m['event'].get('markets', [])
                if markets_data:
                    market = markets_data[0]
                    condition_id = market.get('conditionId')
                    clob_token_ids_str = market.get('clobTokenIds', '[]')
                    token_ids = json.loads(clob_token_ids_str)

                    print(f"     Condition ID: {condition_id}")
                    print(f"     Token IDs: {token_ids[:2]}...")  # 只显示前2个

        # 专门查找 15:30 UTC 的市场
        print(f"\n" + "=" * 80)
        print(f"[TARGET] 精准查找：15:30 UTC (10:30 AM ET) 结束的市场")
        print(f"=" * 80)

        for market in all_btc_markets:
            end_date = market['end_date']

            if end_date.hour == TARGET_HOUR_UTC and end_date.minute == TARGET_MINUTE_UTC:
                found_count += 1
                print(f"\n[FOUND] 找到匹配市场 #{found_count}")
                print(f"   标题 (API Title): {market['title']}")
                print(f"   结束时间 (UTC): {end_date}")
                print(f"   剩余秒数: {(end_date - datetime.now(timezone.utc)).total_seconds():.0f}s")

                markets_data = market['event'].get('markets', [])
                for m in markets_data:
                    print(f"   [MARKET] Condition ID: {m.get('conditionId')}")

                    outcomes = m.get('outcomes', [])
                    clob_ids = m.get('clobTokenIds', '[]')
                    token_ids = json.loads(clob_ids)

                    for i, out in enumerate(outcomes):
                        print(f"      选项 {out}: {token_ids[i] if i < len(token_ids) else 'N/A'}")

        if found_count == 0:
            print(f"\n[ERROR] 未找到 15:30 UTC 结束的市场")
            print(f"\n可能原因：")
            print(f"1. 市场已经结束")
            print(f"2. API 数据还没刷新出来")
            print(f"3. 时区转换错误（冬令时/夏令时）")
            print(f"\n建议：查看上面列出的所有时间段，找到最近的一个")

        print(f"\n" + "=" * 80)
        print(f"总结: 找到 {found_count} 个 15:30 UTC 结束的市场")
        print(f"=" * 80)

    except Exception as e:
        print(f"[ERROR] 请求失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    find_specific_et_market()
