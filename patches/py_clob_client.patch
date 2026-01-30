"""
在项目启动时自动应用 py_clob_client 余额查询修复

这个模块会在导入时自动修补 py_clob_client 库
"""

def patch_py_clob_client():
    """修补 py_clob_client 以支持 funder 地址余额查询"""

    try:
        from py_clob_client.headers import headers as headers_module
        from py_clob_client import client as client_module

        # ========== 修复 1: 替换 create_level_2_headers 函数 ==========
        original_create_level_2_headers = headers_module.create_level_2_headers

        def create_level_2_headers_patched(
            signer,
            creds,
            request_args,
            address=None,  # ← 新增参数
        ):
            """修补后的版本：支持使用 funder 地址查询余额"""
            from py_clob_client.headers.headers import (
                POLY_ADDRESS,
                POLY_SIGNATURE,
                POLY_TIMESTAMP,
                POLY_API_KEY,
                POLY_PASSPHRASE,
            )
            from datetime import datetime
            from py_clob_client.signing.hmac import build_hmac_signature

            timestamp = int(datetime.now().timestamp())

            # Prefer the pre-serialized body string for deterministic signing if available
            body_for_sig = (
                request_args.serialized_body
                if request_args.serialized_body is not None
                else request_args.body
            )

            hmac_sig = build_hmac_signature(
                creds.api_secret,
                timestamp,
                request_args.method,
                request_args.request_path,
                body_for_sig,
            )

            # 修复：优先使用传入的 address 参数（funder），否则使用 signer.address()
            address_to_use = address if address is not None else signer.address()

            return {
                POLY_ADDRESS: address_to_use,  # ← 使用 funder 地址
                POLY_SIGNATURE: hmac_sig,
                POLY_TIMESTAMP: str(timestamp),
                POLY_API_KEY: creds.api_key,
                POLY_PASSPHRASE: creds.api_passphrase,
            }

        # 替换原函数
        headers_module.create_level_2_headers = create_level_2_headers_patched

        # ========== 修复 2: 替换 get_balance_allowance 方法 ==========
        original_get_balance_allowance = client_module.ClobClient.get_balance_allowance

        def get_balance_allowance_patched(self, params=None):
            """修补后的版本：使用 funder 地址查询余额"""
            self.assert_level_2_auth()
            request_args = client_module.RequestArgs(
                method="GET",
                request_path=client_module.GET_BALANCE_ALLOWANCE
            )

            # 修复：如果设置了 funder（proxy 地址），使用它来查询余额
            funder_address = self.builder.funder if hasattr(self, 'builder') and self.builder else None
            headers = create_level_2_headers_patched(
                self.signer,
                self.creds,
                request_args,
                address=funder_address  # ← 传入 funder 地址
            )

            if params.signature_type == -1:
                params.signature_type = self.builder.sig_type

            from py_clob_client.http_helpers.helpers import add_balance_allowance_params_to_url
            url = add_balance_allowance_params_to_url(
                "{}{}".format(self.host, client_module.GET_BALANCE_ALLOWANCE), params
            )
            return self.get(url, headers=headers)

        # 替换原方法
        client_module.ClobClient.get_balance_allowance = get_balance_allowance_patched

        print("[PATCH] py_clob_client 已成功修补 - 余额查询现在使用 funder 地址")

    except Exception as e:
        print(f"[ERROR] py_clob_client 修补失败: {e}")
        import traceback
        traceback.print_exc()


# 在模块导入时自动执行修补
patch_py_clob_client()
