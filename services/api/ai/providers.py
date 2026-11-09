"""Provider contracts for the hidden voice feature. No phonetic score is invented."""
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class Transcript:
    text:str
    duration_seconds:float
    language:str

class SpeechToText(Protocol):
    async def transcribe(self,audio:bytes,content_type:str)->Transcript:...
class TextToSpeech(Protocol):
    async def synthesize(self,text:str,voice:str)->bytes:...
class LanguageModel(Protocol):
    async def complete(self,messages:list[dict],max_tokens:int)->str:...
class PronunciationScorer(Protocol):
    async def score(self,audio:bytes,reference:str)->dict:...
