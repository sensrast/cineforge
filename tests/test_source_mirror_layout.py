from pipeline.source_mirror import _channel_title, _season_post


def test_season_post_matches_exact_compact_layout():
    text = _season_post("Spy x family Hindi Dubbed", 3, 12)
    assert text == (
        "✦ Spy x family ✦\n"
        "╔━━━━━━━━━━━━━━━━━━━━━╗\n"
        "⌲ 𝗦𝗲𝗮𝘀𝗼𝗻 : 3\n"
        "❍ 𝗘𝗽𝗶𝘀𝗼𝗱𝗲: 1-12\n"
        "〄 𝗔𝘂𝗱𝗶𝗼: Hindi\n"
        "◎ 𝗧𝗼𝘁𝗮𝗹 𝗘𝗽𝗶𝘀𝗼𝗱𝗲𝘀: 12\n"
        "♡ 𝗣𝗼𝘄𝗲𝗿𝗲𝗱 𝗯𝘆: @YCAnime , @India_crunchyroll\n"
        "╚━━━━━━━━━━━━━━━━━━━━━╝"
    )
    assert "\n\n" not in text


def test_hindi_dubbed_channel_suffix_is_replaced():
    assert _channel_title("Spy x family (Hindi Dubbed)") == "Spy x family (In Hindi)"
    assert _channel_title("Spy x family Hindi Dubbed") == "Spy x family (In Hindi)"
    assert _channel_title("Spy x family (In Hindi)") == "Spy x family (In Hindi)"
