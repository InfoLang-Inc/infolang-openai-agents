from __future__ import annotations

from infolang_openai_agents import _envelope


def test_alloc_seqs_zero_returns_empty_list() -> None:
    assert _envelope.alloc_seqs(0) == []
    assert _envelope.alloc_seqs(-1) == []


def test_alloc_seqs_strictly_increasing_and_sortable() -> None:
    seqs = _envelope.alloc_seqs(5)
    assert len(seqs) == 5
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 5


def test_encode_decode_round_trip() -> None:
    item = {"role": "user", "content": "hi"}
    text = _envelope.encode(item, "00000000000000000001")
    assert _envelope.decode(text) == ("00000000000000000001", item)


def test_decode_rejects_non_json() -> None:
    assert _envelope.decode("not json") is None


def test_decode_rejects_json_that_is_not_an_object() -> None:
    assert _envelope.decode("[1, 2, 3]") is None
    assert _envelope.decode('"just a string"') is None


def test_decode_rejects_missing_or_malformed_seq_or_item() -> None:
    assert _envelope.decode("{}") is None
    assert _envelope.decode('{"seq": "1"}') is None  # no item
    assert _envelope.decode('{"item": {}}') is None  # no seq
    assert _envelope.decode('{"seq": 1, "item": {}}') is None  # seq not a string
    assert _envelope.decode('{"seq": "1", "item": "not-a-dict"}') is None


def test_record_id_prefers_id_then_memory_id_then_i() -> None:
    assert _envelope.record_id({"id": "a"}) == "a"
    assert _envelope.record_id({"memory_id": "b"}) == "b"
    assert _envelope.record_id({"i": "c"}) == "c"
    assert _envelope.record_id({"id": "", "memory_id": "b"}) == "b"


def test_record_id_rejects_non_dict_or_missing_key() -> None:
    assert _envelope.record_id("not-a-dict") is None
    assert _envelope.record_id(None) is None
    assert _envelope.record_id({"other": "x"}) is None


def test_record_text_prefers_text_then_t_then_content() -> None:
    assert _envelope.record_text({"text": "a"}) == "a"
    assert _envelope.record_text({"t": "b"}) == "b"
    assert _envelope.record_text({"content": "c"}) == "c"


def test_record_text_rejects_non_dict_or_missing_key() -> None:
    assert _envelope.record_text("not-a-dict") is None
    assert _envelope.record_text(None) is None
    assert _envelope.record_text({"other": "x"}) is None
