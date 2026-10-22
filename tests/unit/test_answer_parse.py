from reposage.agent.answer_parse import parse_answer_payload

PAYLOAD = '{"answer": "It is in compute_backoff.", "citations": [], "found": false}'


def test_plain_json():
    assert parse_answer_payload(PAYLOAD)["found"] is False


def test_fenced_json_like_the_live_failure():
    assert parse_answer_payload(f"```json\n{PAYLOAD}\n```")["answer"] == "It is in compute_backoff."


def test_json_surrounded_by_prose():
    assert parse_answer_payload(f"Sure! Here you go:\n{PAYLOAD}\nHope that helps.")["citations"] == []


def test_non_json_and_non_object_return_none():
    assert parse_answer_payload("Unable to locate answer.") is None
    assert parse_answer_payload("[1, 2, 3]") is None
    assert parse_answer_payload("") is None
