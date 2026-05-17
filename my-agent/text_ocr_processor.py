import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import aiortc
import av
import cv2
import easyocr
import numpy as np
from vision_agents.core.processors.base_processor import VideoProcessorPublisher
from vision_agents.core.utils.video_forwarder import VideoForwarder
from vision_agents.core.utils.video_track import QueuedVideoTrack

logger = logging.getLogger(__name__)


class TextOCRProcessor(VideoProcessorPublisher):
    name = "text_ocr"

    def __init__(
        self,
        fps: int = 2,
        language: str = "en",
        conf_threshold: float = 0.4,
        max_workers: int = 2,
    ):
        super().__init__()
        self.fps = fps
        self.conf_threshold = conf_threshold
        self._shutdown = False
        self._video_forwarder: Optional[VideoForwarder] = None
        self._video_track = QueuedVideoTrack()
        self._reader = easyocr.Reader([language], gpu=False)
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="text_ocr_processor"
        )

        self._latest_text_lock = threading.Lock()
        self._latest_text = ""
        self._latest_text_updated_at = 0.0

    async def process_video(
        self,
        track: aiortc.VideoStreamTrack,
        participant_id: Optional[str],
        shared_forwarder: Optional[VideoForwarder] = None,
    ) -> None:
        if self._video_forwarder is not None:
            await self._video_forwarder.remove_frame_handler(self._process_and_publish_frame)

        self._video_forwarder = (
            shared_forwarder
            if shared_forwarder
            else VideoForwarder(
                track,
                max_buffer=self.fps,
                fps=self.fps,
                name="text_ocr_forwarder",
            )
        )
        self._video_forwarder.add_frame_handler(
            self._process_and_publish_frame,
            fps=float(self.fps),
            name="text_ocr",
        )

    async def _process_and_publish_frame(self, frame: av.VideoFrame) -> None:
        if self._shutdown:
            return

        frame_array = frame.to_ndarray(format="rgb24")
        loop = asyncio.get_running_loop()
        annotated = await loop.run_in_executor(
            self.executor,
            self._detect_text_and_annotate_sync,
            frame_array,
        )
        await self._video_track.add_frame(av.VideoFrame.from_ndarray(annotated, format="rgb24"))

    def _detect_text_and_annotate_sync(self, frame_array: np.ndarray) -> np.ndarray:
        try:
            annotated = frame_array.copy()
            results = self._reader.readtext(frame_array, detail=1, paragraph=False)

            detected_text_parts: list[str] = []

            for result in results:
                if len(result) != 3:
                    continue

                bbox, text, confidence = result
                if confidence < self.conf_threshold:
                    continue

                cleaned_text = text.strip()
                if cleaned_text:
                    detected_text_parts.append(cleaned_text)

                points = np.array(bbox, dtype=np.int32)
                if points.shape[0] < 4:
                    continue

                x_min = int(np.min(points[:, 0]))
                y_min = int(np.min(points[:, 1]))
                x_max = int(np.max(points[:, 0]))
                y_max = int(np.max(points[:, 1]))

                cv2.rectangle(annotated, (x_min, y_min), (x_max, y_max), (0, 255, 0), 2)

                label = f"{cleaned_text[:32]} ({confidence:.2f})"
                cv2.putText(
                    annotated,
                    label,
                    (x_min, max(16, y_min - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    2,
                )

            self._update_latest_text(detected_text_parts)
            return annotated
        except Exception:
            logger.exception("Text OCR processing failed")
            return frame_array

    def _update_latest_text(self, detected_text_parts: list[str]) -> None:
        if not detected_text_parts:
            return
        normalized = " ".join(" ".join(detected_text_parts).split()).strip()
        if not normalized:
            return
        if len(normalized) > 220:
            normalized = f"{normalized[:220]}..."
        with self._latest_text_lock:
            self._latest_text = normalized
            self._latest_text_updated_at = time.monotonic()

    def get_latest_text_snapshot(self) -> tuple[str, float]:
        with self._latest_text_lock:
            return self._latest_text, self._latest_text_updated_at

    def publish_video_track(self):
        return self._video_track

    async def stop_processing(self) -> None:
        if self._video_forwarder is not None:
            await self._video_forwarder.remove_frame_handler(self._process_and_publish_frame)
            self._video_forwarder = None

    async def close(self) -> None:
        self._shutdown = True
        await self.stop_processing()
        self.executor.shutdown(wait=False)
        self._video_track.stop()
