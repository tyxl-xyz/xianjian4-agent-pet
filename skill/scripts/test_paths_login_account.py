#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paths.py：wps-collab 当前登录账号解析。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import paths  # noqa: E402


class ResolveAccountIdLoginTests(unittest.TestCase):
    def test_login_id_wins_over_multiple_local_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "accounts" / "111").mkdir(parents=True)
            (root / "accounts" / "222").mkdir(parents=True)
            with mock.patch.object(paths, "get_pet_root", return_value=root):
                with mock.patch.object(
                    paths,
                    "_try_login_account_id_via_wps_collab",
                    return_value="222",
                ):
                    self.assertEqual(paths.resolve_account_id("san-hua"), "222")

    def test_login_id_works_when_no_local_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(paths, "get_pet_root", return_value=root):
                with mock.patch.object(
                    paths,
                    "_try_login_account_id_via_wps_collab",
                    return_value="250006921",
                ):
                    self.assertEqual(paths.resolve_account_id("my-cat"), "250006921")

    def test_ensure_user_creates_account_and_user_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(paths, "get_pet_root", return_value=root):
                with mock.patch.object(
                    paths,
                    "_try_login_account_id_via_wps_collab",
                    return_value="250006921",
                ):
                    info = paths.ensure_user_dir("my-cat")
            account_home = Path(str(info["accountHome"]))
            user_dir = Path(str(info["userDir"]))
            self.assertTrue(account_home.is_dir())
            self.assertTrue(user_dir.is_dir())
            self.assertEqual(info["accountId"], "250006921")
            self.assertTrue(info["accountExists"])

    def test_get_me_helper_reads_success_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "wps-collab" / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "wps_collab.py").write_text(
                "def get_me():\n"
                "    return {'success': True, 'data': {'id': '284967287'}}\n",
                encoding="utf-8",
            )
            with mock.patch.object(
                paths, "_wps_collab_scripts_candidates", return_value=[scripts]
            ):
                self.assertEqual(
                    paths._try_login_account_id_via_wps_collab(), "284967287"
                )


if __name__ == "__main__":
    unittest.main()
