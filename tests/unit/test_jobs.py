from unittest.mock import MagicMock

import pytest

import app.core.jobs as jobs_module


class TestEnqueuePhotoProcessing:
    def test_enqueue_success_delegates_to_rq_queue(self, monkeypatch):
        monkeypatch.setattr("app.core.jobs.record_enqueue", MagicMock())
        seen = {}
        fake_connection = MagicMock()
        redis_mock = MagicMock()
        redis_mock.from_url.return_value = fake_connection
        monkeypatch.setattr("redis.Redis", redis_mock)

        class FakeQueue:
            def __init__(self, name, connection=None):
                seen["name"] = name
                seen["connection"] = connection

            def enqueue(self, fn, photo_id, job_timeout=300):
                seen["fn"] = fn
                seen["photo_id"] = photo_id
                seen["job_timeout"] = job_timeout
                return MagicMock(id="job-123")

        monkeypatch.setattr("rq.Queue", FakeQueue)

        jobs_module.enqueue_photo_processing("photo-1")

        assert seen["name"] == "photos"
        assert seen["connection"] is fake_connection
        assert seen["fn"] == "app.workers.photo_worker.process_photo"
        assert seen["photo_id"] == "photo-1"
        assert seen["job_timeout"] == 300
        jobs_module.record_enqueue.assert_called_once_with("photos")

    def test_enqueue_reraises_when_redis_unavailable(self, monkeypatch):
        monkeypatch.setattr("app.core.jobs.record_enqueue", MagicMock())
        redis_mock = MagicMock()
        redis_mock.from_url.side_effect = RuntimeError("connection refused")
        monkeypatch.setattr("redis.Redis", redis_mock)

        with pytest.raises(RuntimeError, match="connection refused"):
            jobs_module.enqueue_photo_processing("photo-1")

        jobs_module.record_enqueue.assert_not_called()