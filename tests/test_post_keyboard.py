import unittest
from utils.notifications import _download_keyboard

class DownloadKeyboardTests(unittest.TestCase):
    def test_requested_download_label(self):
        markup = _download_keyboard("https://example.com/download", "")
        self.assertEqual(
            markup["inline_keyboard"][0][0]["text"],
            "❐ 𝗪𝗮𝘁𝗰𝗵/𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 ❐",
        )

if __name__ == "__main__":
    unittest.main()
