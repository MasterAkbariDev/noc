import httpx

from noc.detection.alerts import describe_failure


def test_an_empty_error_message_still_names_the_failure() -> None:
    assert describe_failure(httpx.ReadTimeout("")) == "ReadTimeout"
    assert describe_failure(ValueError("bad json")) == "ValueError: bad json"
