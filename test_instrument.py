from nautilus_trader.adapters.polymarket.common.symbol import get_polymarket_instrument_id

# 测试 instrument_id 生成
condition_id = "0xe0b7a1ce4f6e211dcf7cd02cfe36f9dc374968510baa7f8e40919c9dca642ae8"
token_id = "50164777809036667758693066076712603672701101684119148869469668706170865082333"

instrument_id = get_polymarket_instrument_id(condition_id, token_id)
print(f"Instrument ID: {instrument_id}")
print(f"Type: {type(instrument_id)}")
print(f"Str: {str(instrument_id)}")
print(f"Repr: {repr(instrument_id)}")

# 测试 load_ids
load_ids = frozenset([str(instrument_id)])
print(f"\nload_ids: {load_ids}")
print(f"load_ids type: {type(load_ids)}")
print(f"load_ids length: {len(load_ids)}")
