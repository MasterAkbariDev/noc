from noc.llm.client import LLMUnavailable, ProviderRequestRejected, describe_error

LEAKY_PROVIDER_TEXT = "Incorrect API key provided: gsk_live_ABCD1234"


class FakeStatusError(Exception):
    status_code = 400


def rejected_by_provider() -> ProviderRequestRejected:
    try:
        try:
            raise FakeStatusError(LEAKY_PROVIDER_TEXT)
        except FakeStatusError as cause:
            raise ProviderRequestRejected(
                f"groq: request rejected (400): {LEAKY_PROVIDER_TEXT}"
            ) from cause
    except ProviderRequestRejected as error:
        return error


def test_an_llm_error_keeps_the_provider_message_without_any_key() -> None:
    described = describe_error(rejected_by_provider())
    expected = "ProviderRequestRejected (HTTP 400): groq: request rejected (400): "
    assert described == expected + "Incorrect API key provided: [key]"
    assert "gsk_" not in described


def test_an_llm_error_without_an_http_cause_is_its_class_name() -> None:
    assert describe_error(LLMUnavailable("all routes failed for tier strong")) == "LLMUnavailable"


def test_other_errors_keep_their_message() -> None:
    assert describe_error(ValueError("bad payload")) == "ValueError: bad payload"
