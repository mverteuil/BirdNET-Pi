import subprocess
import os
from models.birdnet_config import BirdNETConfig


class AudioManager:
    def __init__(self, config: BirdNETConfig):
        self.config = config

    def record_from_sound_card(self):
        command = [
            "arecord",
            "-f",
            "S16_LE",
            "-c",
            str(self.config.channels),
            "-r",
            "48000",
            "-t",
            "wav",
            "--max-file-time",
            str(self.config.recording_length),
        ]

        if self.config.rec_card:
            command.extend(["-D", self.config.rec_card])

        command.extend(["--use-strftime", os.path.join(self.config.recordings_dir, "%Y-%m-%d-birdnet-%H-%M-%S.wav")])

        subprocess.run(command)

    def record_from_rtsp_stream(self):
        rtsp_streams = self.config.rtsp_stream.split(",")
        stream_data_dir = os.path.join(self.config.recordings_dir, "StreamData")

        if not os.path.exists(stream_data_dir):
            os.makedirs(stream_data_dir)

        while True:
            for i, stream in enumerate(rtsp_streams):
                command = [
                    "ffmpeg",
                    "-nostdin",
                    "-i",
                    stream,
                    "-t",
                    str(self.config.recording_length),
                    "-vn",
                    "-acodec",
                    "pcm_s16le",
                    "-ac",
                    "2",
                    "-ar",
                    "48000",
                    "file:" + os.path.join(stream_data_dir, f"{i}.wav"),
                ]
                subprocess.run(command)

    def record(self):
        if self.config.rtsp_stream:
            self.record_from_rtsp_stream()
        else:
            self.record_from_sound_card()
