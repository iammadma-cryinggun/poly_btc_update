"""
更新 Polymarket 私钥

使用方法：
    python update_private_key.py
"""

import os
import shutil
from pathlib import Path

def main():
    print("=" * 80)
    print("Polymarket 私钥更新工具")
    print("=" * 80)

    # 获取新私钥
    print("\n请输入你的新 Polymarket 邮箱钱包私钥：")
    print("提示: 登录 Polymarket → Settings → Wallets → Magic Wallet → Reveal Private Key")
    new_private_key = input("\n私钥: ").strip()

    if not new_private_key:
        print("[错误] 未输入私钥")
        return 1

    if not new_private_key.startswith("0x"):
        new_private_key = "0x" + new_private_key

    print(f"\n[OK] 新私钥: {new_private_key[:10]}...{new_private_key[-6:]}")

    # 更新 .env 文件
    env_file = Path(__file__).parent / '.env'

    # 备份
    if env_file.exists():
        backup_file = Path(__file__).parent / '.env.old_backup'
        shutil.copy(env_file, backup_file)
        print(f"[INFO] 已备份旧配置到: {backup_file}")

    # 读取现有配置
    existing_vars = {}
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    existing_vars[key.strip()] = value.strip()

    # 写入新配置
    with open(env_file, 'w', encoding='utf-8') as f:
        f.write("# Polymarket 配置\n")
        f.write(f"# 私钥更新时间: {__import__('datetime').datetime.now()}\n\n")

        # 写入新私钥
        f.write(f"POLYMARKET_PK={new_private_key}\n")

        # 保留其他配置（如果存在）
        for key, value in existing_vars.items():
            if key != "POLYMARKET_PK":
                f.write(f"{key}={value}\n")

    print(f"\n[OK] 私钥已更新到: {env_file}")

    print("\n" + "=" * 80)
    print("下一步：")
    print("  1. 运行 'python generate_api_credentials.py' 为新账号生成 API 凭证")
    print("  2. 或直接使用新账号的私钥（可能需要先在网页上交易一次激活钱包）")
    print("=" * 80)

    return 0

if __name__ == "__main__":
    try:
        import sys
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n[错误] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
