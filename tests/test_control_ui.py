from control.keyboards import home_keyboard, ingest_keyboard, operations_keyboard, premium_sources_keyboard


def callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_home_uses_task_based_navigation():
    markup = home_keyboard(True)
    values = callbacks(markup)
    assert 'nav:ingest' in values
    assert 'nav:operations' in values
    assert 'nav:settings' in values
    assert 'manual:start' not in values
    assert 'mirror:panel' not in values


def test_ingest_hub_groups_upload_and_source_workflows():
    values = callbacks(ingest_keyboard())
    assert {'manual:start', 'mirror:panel', 'nav:premium_sources'} <= set(values)
    assert values[-1] == 'nav:home'


def test_operations_pause_resume_is_contextual():
    running = operations_keyboard(False)
    paused = operations_keyboard(True)
    assert 'ops:pause' in callbacks(running)
    assert 'ops:resume' in callbacks(paused)
    assert any('Pause Pipeline' in label for label in labels(running))


def test_premium_sources_returns_to_ingest_hub():
    assert callbacks(premium_sources_keyboard())[-1] == 'nav:ingest'
