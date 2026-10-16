"""Generate public/synthetic demo speech locally; optional development tool.

Install espeakng-loader to regenerate. It is NOT needed to process recordings.
The audio and its source text are shipped so the demo needs no TTS installation.
"""

import ctypes
import subprocess
import wave
from pathlib import Path

SCRIPTS = {
    "business": "Today we reviewed the project schedule. We decided to use the local server for all meeting recordings. Alice will send the revised budget by Friday. The main risk is limited storage on the recording device. Do we need a second backup drive? The next meeting is on Monday.",
    "lecture": "Today's lecture covers reinforcement learning. A policy maps a state to an action. The value function estimates expected future reward. Remember, the discount factor controls how much future rewards matter. The homework is due on Friday. How does exploration affect learning? The exam will cover value iteration and policy iteration.",
    "planning": "This is the recorder planning meeting. We agreed to keep the original recordings on an encrypted drive. The device must record audio before sending it to the laptop. Bob will review the microphone settings tomorrow. The important constraint is battery life. Who will test the transfer cable? We have not decided on a wireless connection.",
}


def main():
    import espeakng_loader
    library = ctypes.CDLL(espeakng_loader.get_library_path())
    library.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    library.espeak_Initialize.restype = ctypes.c_int
    # Parent folder is required; eSpeak appends espeak-ng-data internally.
    sample_rate = library.espeak_Initialize(2, 0, str(Path(espeakng_loader.get_data_path()).parent).encode(), 0)
    if sample_rate <= 0:
        raise RuntimeError("eSpeak initialization failed")
    callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)
    frames = []

    @callback_type
    def receive(samples, count, events):
        if samples and count > 0:
            frames.append(ctypes.string_at(samples, count * 2))
        return 0

    library.espeak_SetSynthCallback.argtypes = [callback_type]
    library.espeak_SetSynthCallback(receive)
    library.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
    library.espeak_SetVoiceByName(b"en-us")
    library.espeak_SetParameter(1, 145, 0)  # speaking rate
    library.espeak_Synth.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint,
                                    ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                                    ctypes.POINTER(ctypes.c_uint), ctypes.c_void_p]
    destination = Path(__file__).resolve().parents[1] / "examples" / "media"
    destination.mkdir(parents=True, exist_ok=True)
    for name, text in SCRIPTS.items():
        frames.clear()
        encoded = text.encode("utf-8")
        result = library.espeak_Synth(encoded, len(encoded) + 1, 0, 1, 0, 1, None, None)
        library.espeak_Synchronize()
        if result or not frames:
            raise RuntimeError("Speech synthesis failed")
        path = destination / (name + ".wav")
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(sample_rate)
            audio.writeframes(b"".join(frames))
        (destination / (name + "_source.txt")).write_text(text, encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(destination / "lecture.wav"),
                    str(destination / "lecture.mp3")], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "color=c=navy:s=320x240:r=5", "-i", str(destination / "planning.wav"),
                    "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(destination / "planning.mp4")], check=True)
    print("Synthetic WAV, MP3 and MP4 demo recordings generated.")


if __name__ == "__main__":
    main()
