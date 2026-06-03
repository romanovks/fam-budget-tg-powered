import subprocess
from pathlib import Path


def convert_telegram_voice_to_mp3(source: Path) -> Path:
    target = source.with_suffix(".mp3")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-b:a",
            "96k",
            str(target),
        ],
        check=True,
        capture_output=True,
    )
    return target
