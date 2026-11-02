import json

from livekit.agents.metrics import LLMMetrics, RealtimeModelMetrics

import usage_log


def realtime_metrics() -> RealtimeModelMetrics:
    details = RealtimeModelMetrics.InputTokenDetails(
        audio_tokens=100,
        text_tokens=50,
        image_tokens=7,
        cached_tokens=30,
        cached_tokens_details=RealtimeModelMetrics.CachedTokenDetails(
            audio_tokens=20, text_tokens=10, image_tokens=0
        ),
    )
    return RealtimeModelMetrics(
        label="openai",
        request_id="r1",
        timestamp=0.0,
        duration=1.0,
        ttft=0.1,
        cancelled=False,
        input_tokens=157,
        output_tokens=60,
        total_tokens=217,
        tokens_per_second=1.0,
        input_token_details=details,
        output_token_details=RealtimeModelMetrics.OutputTokenDetails(
            text_tokens=15, audio_tokens=45, image_tokens=0
        ),
    )


def test_counts_are_written_for_the_monitor_and_nothing_else(tmp_path, monkeypatch):
    monkeypatch.setenv("HIREACE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_REALTIME_MODEL", "gpt-test")

    usage_log.record(realtime_metrics())
    usage_log.record(realtime_metrics())

    lines = (tmp_path / "usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    row = json.loads(lines[0])
    assert row.pop("day")
    assert row == {
        "model": "gpt-test",
        "inText": 50,
        "inAudio": 100,
        "inImage": 7,
        "cachedText": 10,
        "cachedAudio": 20,
        "outText": 15,
        "outAudio": 45,
    }


def test_other_metrics_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("HIREACE_DATA_DIR", str(tmp_path))
    usage_log.record(
        LLMMetrics(
            label="x",
            request_id="r",
            timestamp=0.0,
            duration=1.0,
            ttft=0.1,
            cancelled=False,
            completion_tokens=1,
            prompt_tokens=1,
            prompt_cached_tokens=0,
            total_tokens=2,
            tokens_per_second=1.0,
        )
    )
    assert not (tmp_path / "usage.jsonl").exists()


def test_a_problem_writing_never_disturbs_the_call(tmp_path, monkeypatch):
    blocked = tmp_path / "a-file"
    blocked.write_text("not a folder")
    monkeypatch.setenv("HIREACE_DATA_DIR", str(blocked))
    usage_log.record(realtime_metrics())


def test_the_limit_is_a_file_the_monitor_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("HIREACE_DATA_DIR", str(tmp_path))
    assert not usage_log.limit_reached()
    (tmp_path / "usage-limit").write_text("reached")
    assert usage_log.limit_reached()


class FakeCall:
    def __init__(self) -> None:
        self.said: list[str] = []
        self.ended: list[str] = []

    async def _reply(self) -> None:
        pass

    def generate_reply(self, instructions: str):
        self.said.append(instructions)
        return self._reply()

    def shutdown(self, reason: str) -> None:
        self.ended.append(reason)


async def test_over_the_limit_a_call_only_says_so_and_ends(tmp_path, monkeypatch):
    from agent import refuse_over_limit

    monkeypatch.setenv("HIREACE_DATA_DIR", str(tmp_path))
    call = FakeCall()
    assert await refuse_over_limit(call, call) is False
    assert call.said == [] and call.ended == []

    (tmp_path / "usage-limit").write_text("reached")
    assert await refuse_over_limit(call, call) is True
    assert call.said == [usage_log.LIMIT_MESSAGE]
    assert call.ended == ["usage limit reached"]
