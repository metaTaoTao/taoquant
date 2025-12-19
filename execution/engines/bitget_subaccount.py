"""
Bitget Subaccount Manager.

This module provides subaccount management functionality for Bitget.
"""

from __future__ import annotations

from typing import List, Dict, Optional, Any


class BitgetSubaccountManager:
    """Bitget subaccount manager."""

    def __init__(
        self,
        main_api_key: str,
        main_api_secret: str,
        main_passphrase: str,
        debug: bool = False,
    ):
        """
        Initialize subaccount manager with main account credentials.

        Parameters
        ----------
        main_api_key : str
            Main account API key
        main_api_secret : str
            Main account API secret
        main_passphrase : str
            Main account passphrase
        debug : bool
            Enable debug logging
        """
        try:
            from bitget import Client  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "bitget-python package is required. Install via pip install bitget-python."
            ) from exc

        self.main_api_key = main_api_key
        self.main_api_secret = main_api_secret
        self.main_passphrase = main_passphrase
        self.debug = debug

        # Initialize client with main account credentials
        self.client = Client(main_api_key, main_api_secret, passphrase=main_passphrase)

    def list_subaccounts(self) -> List[Dict[str, Any]]:
        """
        List all subaccounts.

        Returns
        -------
        list
            List of subaccount information
        """
        try:
            response = self.client.get_subaccount_list()

            subaccounts = []
            if isinstance(response, dict):
                code = response.get("code", "")
                if code == "00000":
                    data = response.get("data", [])
                    for item in data:
                        subaccounts.append({
                            "uid": item.get("uid", ""),
                            "sub_account_name": item.get("subAccountName", ""),
                            "label": item.get("label", ""),
                            "status": item.get("status", ""),
                        })

            if self.debug:
                print(f"[Subaccount Manager] Found {len(subaccounts)} subaccounts")

            return subaccounts

        except Exception as e:
            if self.debug:
                print(f"[Subaccount Manager] Error listing subaccounts: {e}")
                import traceback
                traceback.print_exc()
            return []

    def create_subaccount(
        self,
        subaccount_name: str,
        passphrase: str,
        permissions: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new subaccount.

        Parameters
        ----------
        subaccount_name : str
            Subaccount name
        passphrase : str
            Subaccount passphrase
        permissions : list, optional
            List of permissions (e.g., ["spot_trade", "contract_trade"])

        Returns
        -------
        dict or None
            Created subaccount information
        """
        try:
            if permissions is None:
                permissions = ["spot_trade"]

            subaccount_data = [
                {
                    "subAccountName": subaccount_name,
                    "passphrase": passphrase,
                    "permList": permissions,
                    "label": subaccount_name,
                }
            ]

            response = self.client.batch_create_subaccount_and_apikey(subaccount_data)

            if isinstance(response, dict):
                code = response.get("code", "")
                if code == "00000":
                    data = response.get("data", [])
                    if data:
                        return data[0]

            return None

        except Exception as e:
            if self.debug:
                print(f"[Subaccount Manager] Error creating subaccount: {e}")
                import traceback
                traceback.print_exc()
            return None

    def get_subaccount_api_keys(self, subaccount_uid: str) -> List[Dict[str, Any]]:
        """
        Get API keys for a subaccount.

        Parameters
        ----------
        subaccount_uid : str
            Subaccount UID

        Returns
        -------
        list
            List of API keys
        """
        try:
            response = self.client.get_virtual_subaccount_apikey_list(
                subAccountUid=subaccount_uid
            )

            api_keys = []
            if isinstance(response, dict):
                code = response.get("code", "")
                if code == "00000":
                    data = response.get("data", [])
                    for item in data:
                        api_keys.append({
                            "api_key": item.get("apiKey", ""),
                            "label": item.get("label", ""),
                            "permissions": item.get("perm", []),
                            "ip": item.get("ip", ""),
                            "status": item.get("status", ""),
                        })

            return api_keys

        except Exception as e:
            if self.debug:
                print(f"[Subaccount Manager] Error getting API keys: {e}")
            return []

    def create_subaccount_apikey(
        self,
        subaccount_uid: str,
        label: str,
        permissions: Optional[List[str]] = None,
        ip: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create API key for a subaccount.

        Parameters
        ----------
        subaccount_uid : str
            Subaccount UID
        label : str
            API key label
        permissions : list, optional
            List of permissions
        ip : str, optional
            IP whitelist

        Returns
        -------
        dict or None
            Created API key information (contains api_key, api_secret, passphrase)
        """
        try:
            if permissions is None:
                permissions = ["read", "spot_trade"]

            params = {
                "subUid": subaccount_uid,
                "label": label,
                "perm": ",".join(permissions),
            }

            if ip:
                params["ip"] = ip

            response = self.client.create_subaccount_apikey(**params)

            if isinstance(response, dict):
                code = response.get("code", "")
                if code == "00000":
                    data = response.get("data", {})
                    return {
                        "api_key": data.get("apiKey", ""),
                        "api_secret": data.get("secretKey", ""),
                        "passphrase": data.get("passphrase", ""),
                        "label": label,
                    }

            return None

        except Exception as e:
            if self.debug:
                print(f"[Subaccount Manager] Error creating API key: {e}")
                import traceback
                traceback.print_exc()
            return None
