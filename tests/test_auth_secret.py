import sys
import os
import unittest
import logging
from unittest.mock import patch, MagicMock

# Add backend to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

class TestAuthSecret(unittest.TestCase):
    def setUp(self):
        # Clean up env var before each test
        if "JWT_SECRET_KEY" in os.environ:
            del os.environ["JWT_SECRET_KEY"]

    def test_secret_key_behavior(self):
        import auth
        import importlib
        importlib.reload(auth)

        # 1. Test Default Behavior (Warning + Default Key)
        # We expect a warning on first call
        with self.assertLogs(auth.logger, level='WARNING') as cm:
            key = auth.get_secret_key()
            self.assertEqual(key, "your-secret-key-change-in-production")
            self.assertTrue(any("JWT_SECRET_KEY is not set" in o for o in cm.output))

        # 2. Test Custom Key Behavior (No Warning + Custom Key)
        # We need to reload to clear the internal cache of auth module
        importlib.reload(auth)
        os.environ["JWT_SECRET_KEY"] = "my-super-secret-key"

        # We assume logging is not triggered if key is present.
        # But assertLogs requires at least one log or it fails.
        # So we can't use assertLogs here easily if we expect NO logs.
        # Instead, we can verify the key returned.
        key = auth.get_secret_key()
        self.assertEqual(key, "my-super-secret-key")

    def test_secret_key_caching(self):
        """Verify that the warning is logged only once."""
        import auth
        import importlib
        importlib.reload(auth)

        if "JWT_SECRET_KEY" in os.environ:
            del os.environ["JWT_SECRET_KEY"]

        with self.assertLogs(auth.logger, level='WARNING') as cm:
            key1 = auth.get_secret_key()
            key2 = auth.get_secret_key()

            self.assertEqual(key1, "your-secret-key-change-in-production")
            self.assertEqual(key1, key2)

            # Should only log once
            self.assertEqual(len(cm.output), 1, f"Expected 1 warning log, got {len(cm.output)}")

    def test_token_creation_uses_getter(self):
        import auth
        import importlib
        importlib.reload(auth)

        # We need to ensure get_secret_key is called.
        # Since we might have caching, we should patch it.
        # Or, we can rely on the fact that we can decode it.

        test_key = "test-key-for-token"
        os.environ["JWT_SECRET_KEY"] = test_key

        token = auth.create_access_token({"sub": "test"})

        # Decode manually using jwt library to verify the key was used
        import jwt
        payload = jwt.decode(token, test_key, algorithms=["HS256"])
        self.assertEqual(payload['sub'], 'test')

if __name__ == '__main__':
    unittest.main()
