import unittest

from scripts.import_actual_portfolio import supabase_headers


class SupabaseHeaderTests(unittest.TestCase):
    def test_new_secret_key_is_not_sent_as_bearer_jwt(self):
        self.assertEqual(supabase_headers("sb_secret_example"), {"apikey": "sb_secret_example"})

    def test_legacy_service_role_key_is_sent_as_bearer(self):
        self.assertEqual(
            supabase_headers("legacy.jwt"),
            {"apikey": "legacy.jwt", "Authorization": "Bearer legacy.jwt"},
        )


if __name__ == "__main__":
    unittest.main()
