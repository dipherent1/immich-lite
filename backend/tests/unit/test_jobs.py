from unittest.mock import MagicMock

import pytest

import app.core.jobs as jobs_module


class TestEnqueuePhotoProcessing:
    def test_enqueue_success_delegates_to_celery_task(self, monkeypatch):
        monkeypatch.setattr("app.core.jobs.record_enqueue", MagicMock())
        celery_app = MagicMock()
        celery_app.send_task.return_value = MagicMock(id="job-123")
        monkeypatch.setattr(jobs_module, "celery_app", celery_app)

        jobs_module.enqueue_photo_processing("photo-1")

        celery_app.send_task.assert_called_once_with(
            "app.workers.photo_worker.process_photo",
            args=["photo-1"],
            queue="photos",
        )
        jobs_module.record_enqueue.assert_called_once_with("photos")

    def test_enqueue_reraises_when_broker_unavailable(self, monkeypatch):
        monkeypatch.setattr("app.core.jobs.record_enqueue", MagicMock())
        celery_app = MagicMock()
        celery_app.send_task.side_effect = RuntimeError("broker unavailable")
        monkeypatch.setattr(jobs_module, "celery_app", celery_app)

        with pytest.raises(RuntimeError, match="broker unavailable"):
            jobs_module.enqueue_photo_processing("photo-1")

        jobs_module.record_enqueue.assert_not_called()
