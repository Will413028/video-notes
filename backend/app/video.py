from pydantic import BaseModel, Field

DEMO_URL = "fixture://learning-demo"


class VideoFormat(BaseModel):
    format_id: str
    label: str
    ext: str
    has_audio: bool
    requires_merge: bool = False


class VideoInfo(BaseModel):
    id: str
    title: str
    uploader: str
    duration_seconds: int
    source: str
    formats: list[VideoFormat] = Field(default_factory=list)


class DemoVideoParser:
    def parse(self, url: str) -> VideoInfo:
        if url != DEMO_URL:
            raise ValueError("目前可先體驗範例影片，請點選「帶入範例」。")
        return VideoInfo(
            id="learning-demo",
            title="用 AI 建立你的學習工作流",
            uploader="video-notes",
            duration_seconds=754,
            source="demo",
            formats=[
                VideoFormat(
                    format_id="demo-360",
                    label="360p MP4 · 影片與音訊",
                    ext="mp4",
                    has_audio=True,
                )
            ],
        )
