"""Tests for credential extraction from webRequestLog."""

from __future__ import annotations

import unittest

from ic_gamedata.credentials import extract_credentials_from_log


SAMPLE_LOG = (
    "*" * 50
    + "\nhttps://pslt3.idlechampions.com/~idledragons/post.php?call=initializemobilesession&user_id=4602118&hash=abc123&instance_key=999&network_id=21&mobile_client_version=650\n"
    + '{"success":true,"play_server":"https://pslt3.idlechampions.com/~idledragons/","hash":"abc123","instance_key":999}\n'
)


class CredentialsTests(unittest.TestCase):
    def test_extract_credentials(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "webRequestLog.txt"
            path.write_text(SAMPLE_LOG, encoding="utf-8")
            creds = extract_credentials_from_log(path)
        self.assertIsNotNone(creds)
        assert creds is not None
        self.assertEqual(creds.user_id, "4602118")
        self.assertEqual(creds.hash, "abc123")
        self.assertEqual(creds.instance_key, 999)


if __name__ == "__main__":
    unittest.main()
