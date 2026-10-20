import pytest


class OpenRobots:
    """robots.txt 가 전부 허용하는 사이트로 친다. robots.txt 요청은 보내지 않는다."""

    def allowed(self, url: str) -> bool:
        return True


@pytest.fixture
def open_robots():
    return OpenRobots()
