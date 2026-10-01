from tasks.diagnostics import ping


def test_ping():
    assert ping() == "pong"
