"""
生成 Zeabur 部署所需的环境变量

运行此脚本，然后将输出的环境变量配置到 Zeabur
"""

import os
from pathlib import Path

project_root = Path(__file__).parent


def load_private_key():
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


def main():
    print("=" * 80)
    print("生成 Zeabur 部署环境变量")
    print("=" * 80)

    # 1. 加载私钥
    private_key = load_private_key()
    if not private_key:
        print("\n[ERROR] 未找到私钥")
        print("\n请在 .env 文件中配置:")
        print("  POLYMARKET_PK=0x...")
        return 1

    print(f"\n[OK] 私钥已加载: {private_key[:10]}...{private_key[-6:]}")

    # 2. 生成 API 凭证
    print("\n[INFO] 生成 API 凭证...")

    try:
        from py_clob_client.client import ClobClient

        POLYMARKET_API_URL = "https://clob.polymarket.com"
        POLYMARKET_CHAIN_ID = 137  # Polygon chain ID

        client = ClobClient(
            POLYMARKET_API_URL,
            key=str(private_key),
            signature_type=2,  # Magic Wallet
            chain_id=POLYMARKET_CHAIN_ID,
        )

        api_creds = client.create_or_derive_api_creds()

        if api_creds:
            # ApiCreds 是对象，不是字典
            api_key = getattr(api_creds, 'apiKey', '')
            api_secret = getattr(api_creds, 'apiSecret', '')
            passphrase = getattr(api_creds, 'passphrase', '')

            print("\n" + "=" * 80)
            print("✅ API 凭证生成成功！")
            print("=" * 80)
            print("\n📋 请在 Zeabur 配置以下环境变量：\n")

            print(f"POLYMARKET_PK={private_key}")
            print(f"POLYMARKET_API_KEY={api_key}")
            print(f"POLYMARKET_API_SECRET={api_secret}")
            print(f"POLYMARKET_PASSPHRASE={passphrase}")

            print("\n" + "=" * 80)
            print("配置步骤：")
            print("=" * 80)
            print("1. 复制上面的环境变量")
            print("2. 打开 Zeabur 项目设置")
            print("3. 进入 Environment Variables")
            print("4. 逐个添加上述 4 个环境变量")
            print("5. 保存并重新部署\n")

            return 0
        else:
            print("\n[ERROR] 无法生成 API 凭证")
            return 1

    except Exception as e:
        import traceback
        print(f"\n[ERROR] API 凭证生成失败: {e}")
        print(f"\n详细错误:\n{traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    import sys
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n已取消")
        sys.exit(0)
