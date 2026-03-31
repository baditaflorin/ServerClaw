from __future__ import annotations

import io
import os
import threading
import wave
from pathlib import Path

from flask import Flask, Response, jsonify, request
from piper import PiperVoice, SynthesisConfig
from piper.download_voices import download_voice


MODEL_DIR = Path(os.environ.get("PIPER_MODEL_DIR", "/data"))
DEFAULT_VOICE = os.environ.get("PIPER_DEFAULT_VOICE", "en_US-ryan-medium")
DECLARED_VOICES = [
    voice.strip()
    for voice in os.environ.get("PIPER_VOICES", DEFAULT_VOICE).split(",")
    if voice.strip()
]
SENTENCE_SILENCE = float(os.environ.get("PIPER_SENTENCE_SILENCE", "0.0"))

app = Flask(__name__)
_voice_lock = threading.Lock()
_loaded_voices: dict[str, PiperVoice] = {}


def ensure_voice_downloaded(voice_id: str) -> Path:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / f"{voice_id}.onnx"
    config_path = MODEL_DIR / f"{voice_id}.onnx.json"
    if model_path.exists() and config_path.exists():
        return model_path
    download_voice(voice_id, MODEL_DIR, force_redownload=False)
    return model_path


def get_voice(voice_id: str) -> PiperVoice:
    with _voice_lock:
        voice = _loaded_voices.get(voice_id)
        if voice is not None:
            return voice
        model_path = ensure_voice_downloaded(voice_id)
        voice = PiperVoice.load(model_path)
        _loaded_voices[voice_id] = voice
        return voice


def build_synthesis_config(voice: PiperVoice) -> SynthesisConfig:
    speaker_id = request.args.get("speaker_id", type=int)
    if speaker_id is None and voice.config.num_speakers > 1:
        speaker_name = request.args.get("speaker")
        if speaker_name:
            speaker_id = voice.config.speaker_id_map.get(speaker_name)
        if speaker_id is None:
            speaker_id = 0

    return SynthesisConfig(
        speaker_id=speaker_id,
        length_scale=request.args.get("length_scale", type=float) or voice.config.length_scale,
        noise_scale=request.args.get("noise_scale", type=float) or voice.config.noise_scale,
        noise_w_scale=request.args.get("noise_w_scale", type=float) or voice.config.noise_w_scale,
    )


def synthesize_wav_bytes(voice: PiperVoice, text: str, synthesis_config: SynthesisConfig) -> bytes:
    with io.BytesIO() as wav_io:
        wav_file = wave.open(wav_io, "wb")
        with wav_file:
            wav_params_set = False
            for index, audio_chunk in enumerate(voice.synthesize(text, synthesis_config)):
                if not wav_params_set:
                    wav_file.setframerate(audio_chunk.sample_rate)
                    wav_file.setsampwidth(audio_chunk.sample_width)
                    wav_file.setnchannels(audio_chunk.sample_channels)
                    wav_params_set = True
                if index > 0 and SENTENCE_SILENCE > 0:
                    wav_file.writeframes(bytes(int(voice.config.sample_rate * SENTENCE_SILENCE * 2)))
                wav_file.writeframes(audio_chunk.audio_int16_bytes)
        return wav_io.getvalue()


@app.get("/healthz")
def healthz() -> Response:
    voice = get_voice(DEFAULT_VOICE)
    return jsonify(
        {
            "status": "ok",
            "default_voice": DEFAULT_VOICE,
            "voices": DECLARED_VOICES,
            "sample_rate": voice.config.sample_rate,
        }
    )


@app.get("/api/voices")
def voices() -> Response:
    for voice_id in DECLARED_VOICES:
        ensure_voice_downloaded(voice_id)
    return jsonify({"default_voice": DEFAULT_VOICE, "voices": DECLARED_VOICES})


@app.post("/api/tts")
def tts() -> Response:
    text = request.get_data(as_text=True).strip()
    if not text:
        return jsonify({"error": "text body is required"}), 400

    voice_id = request.args.get("voice") or request.args.get("model") or DEFAULT_VOICE
    if voice_id not in DECLARED_VOICES:
        return jsonify({"error": f"unknown voice '{voice_id}'"}), 404

    voice = get_voice(voice_id)
    synthesis_config = build_synthesis_config(voice)
    wav_bytes = synthesize_wav_bytes(voice, text, synthesis_config)
    return Response(wav_bytes, mimetype="audio/wav")


if __name__ == "__main__":
    for declared_voice in DECLARED_VOICES:
        ensure_voice_downloaded(declared_voice)
    get_voice(DEFAULT_VOICE)
    app.run(host="0.0.0.0", port=5000, debug=False)
