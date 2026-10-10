from pipeline.source_mirror import _season_post


def test_season_post_matches_compact_layout():
    text = _season_post("Spy x family", 3, 12)
    assert "▷ Season : 3" in text
    assert "▷ Episode : 1-12" in text
    assert "◉ Total Episodes: 12" in text
    assert "@YOAnime" in text
    assert "@India_crunchyroll" in text
