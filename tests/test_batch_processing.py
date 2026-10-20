from types import SimpleNamespace

from pipeline.stages.common import batch_link_from_message, is_batch_processing


def message(text="", url=None):
    markup = None
    if url:
        markup = SimpleNamespace(inline_keyboard=[[SimpleNamespace(url=url)]])
    return SimpleNamespace(text=text, caption=None, reply_markup=markup)


def test_processing_response_is_an_acknowledgement():
    assert is_batch_processing(message("⏳ Processing your batch, please wait..."))
    assert is_batch_processing(message("Generating link"))
    assert not is_batch_processing(message("Batch created successfully"))


def test_batch_link_can_arrive_in_text_or_button():
    text_link = "https://t.me/ANIMEZONEFILESBOT?start=b_abc-123"
    assert batch_link_from_message(message(text_link)) == text_link
    button_link = "https://t.me/YcAnimefilesbot?start=b_xyz_789"
    assert batch_link_from_message(message("✅ Done", button_link)) == button_link
