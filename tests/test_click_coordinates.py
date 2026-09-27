import unittest
from types import SimpleNamespace
from pipeline.stages.common import click_matching

class FakeMessage:
    def __init__(self):
        self.reply_markup = SimpleNamespace(inline_keyboard=[
            [SimpleNamespace(text="A", callback_data="a")],
            [SimpleNamespace(text="PREV", callback_data="p"), SimpleNamespace(text="NEXT ⏩", callback_data="n")],
        ])
        self.clicked = None
    async def click(self, x, y):
        self.clicked = (x, y)

class ClickCoordinateTests(unittest.IsolatedAsyncioTestCase):
    async def test_pyrogram_column_then_row(self):
        message = FakeMessage()
        self.assertTrue(await click_matching(message, [r"NEXT"]))
        self.assertEqual(message.clicked, (1, 1))

if __name__ == "__main__":
    unittest.main()
