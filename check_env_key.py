"""
直接验证 .env 文件中的私钥
"""
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
import os
from pathlib import Path

def main():
    print("=" * 80)
    print("验证 .env 文件中的私钥")
    print("=" * 80)

    # 读取 .env 文件
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        print("[ERROR] .env 文件不存在")
        return 1

    private_key = None
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith("POLYMARKET_PK="):
                private_key = line.split("=", 1)[1].strip()
                break

    if not private_key:
        print("[ERROR] .env 文件中未找到 POLYMARKET_PK")
        return 1

    print(f"\n[INFO] 私钥: {private_key[:10]}...{private_key[-6:]}")

    # 验证私钥对应的地址
    print("\n[INFO] 正在验证私钥对应的地址...")

    for sig_type in [0, 1, 2]:
        try:
            client = ClobClient(
                host='https://clob.polymarket.com',
                chain_id=POLYGON,
                key=private_key,
                signature_type=sig_type,
            )
            address = client.get_address()
            print(f"\n  signature_type={sig_type}: {address}")
        except Exception as e:
            print(f"\n  signature_type={sig_type}: 错误 - {e}")

    print("\n" + "=" * 80)
    print("期望地址（来自截图）: 0x18DdcbD977e5b7Ff751A3BAd6F274b67A311CD2d")
    print("=" * 80)

if __name__ == "__main__":
    main()
