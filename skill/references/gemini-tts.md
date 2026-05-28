# Gemini 3.1 Flash TTS — Voice & Emotion Tag Reference

## Model Versions

| Model ID | Status | Notes |
|----------|--------|-------|
| `gemini-2.5-flash-preview-tts` | Old default | Limited voice control |
| `gemini-3.1-flash-tts-preview` | ✅ Current best | 30 voices, 70+ languages, emotion tags, multi-speaker |

## All 30 Prebuilt Voices

### Cute / Youthful (for "น่ารัก เด็กๆ")

| Voice | Style | เหมาะ? |
|-------|-------|--------|
| **Leda** | **Youthful** 👧 | ✅ **ดีสุด — youthful** |
| **Puck** | **Upbeat** 🎵 | ✅ สดใส |
| Zephyr | Bright ✨ | ⭐ ดี |
| Aoede | Breezy 🌬️ | ✅ โล่ง โปร่ง |
| Laomedeia | Upbeat 🎶 | ✅ สดใส |
| Achird | Friendly 😊 | ✅ เป็นกันเอง |

### Full Voice Table

| Voice | Style | Voice | Style |
|-------|-------|-------|-------|
| Zephyr | Bright | Enceladus | Breathy |
| **Puck** | **Upbeat** | Iapetus | Clear |
| Charon | Informative | Umbriel | Easy-going |
| Kore | Firm | Algieba | Smooth |
| Fenrir | Excitable | Despina | Smooth |
| **Leda** | **Youthful** | Erinome | Clear |
| Orus | Firm | Algenib | Gravelly |
| Aoede | Breezy | Rasalgethi | Informative |
| Callirrhoe | Easy-going | Achernar | Soft |
| Autonoe | Bright | Alnilam | Firm |
| Schedar | Even | Gacrux | Mature |
| Pulcherrima | Forward | Achird | Friendly |
| Zubenelgenubi | Casual | Vindemiatrix | Gentle |
| Sadachbia | Lively | Sadaltager | Knowledgeable |
| Sulafat | Warm | | |

## Supported Languages

**Thai (th) is supported** ✅ — auto-detected, no separate config needed.

## Emotion Tags (Audio Tags)

Embed these directly in the text passed to `text_to_speech`:

### Most Useful

| Tag | Effect |
|-----|--------|
| `[whispers]` | เสียงกระซิบ |
| `[laughs]` | หัวเราะ |
| `[giggles]` | หัวเราะคิกคัก |
| `[excited]` | ตื่นเต้น |
| `[sighs]` | ถอนหายใจ |
| `[gasp]` | ตกใจ/หอบ |
| `[whisper]` | กระซิบ (alternative) |
| `[shouting]` | ตะโกน |
| `[crying]` | ร้องไห้ |

### Pacing

| Tag | Effect |
|-----|--------|
| `[slow]` | พูดช้า |
| `[fast]` | พูดเร็ว |
| `[short pause]` | หยุดสั้น |
| `[long pause]` | หยุดยาว |

### Emotion

| Tag | Effect | Tag | Effect |
|-----|--------|-----|--------|
| `[happy]` | มีความสุข | `[sad]` | เศร้า |
| `[angry]` | โกรธ | `[nervous]` | ประหม่า |
| `[excitedly]` | อย่างตื่นเต้น | `[bored]` | เบื่อ |
| `[serious]` | จริงจัง | `[sarcastic]` | ประชด |
| `[amazed]` | ตะลึง | `[curious]` |  curious |
| `[mischievously]` | ซุกซน | `[panicked]` | ตื่นตระหนก |
| `[tired]` | เหนื่อย | `[trembling]` | สั่น |
| `[laughter]` | หัวเราะ | `[amused]` | ขำ |
| `[determination]` | มุ่งมั่น | `[enthusiasm]` | กระตือรือร้น |
| `[relief]` | โล่งอก | `[alarm]` | ตกใจ |
| `[cautious]` | ระวัง | `[positive]` | บวก |
| `[neutral]` | ปกติ | `[anxiety]` | กังวล |

### Usage Pattern

```
text = "[happy] สวัสดีค่า! [giggles] วันนี้นู๋มีเรื่องน่าสนใจมาเล่าให้ฟังนะคะ"
call text_to_speech(text=text)
```

Tags ใช้ภาษาอังกฤษเท่านั้น แต่ใช้กับข้อความภาษาอื่นได้ (รวมไทย)

## Config Pattern

```yaml
tts:
  provider: gemini
  gemini:
    model: gemini-3.1-flash-tts-preview
    voice: Leda
```

เปลี่ยน provider/voice/model ได้ใน `~/.hermes/config.yaml`

## Hermes Agent Instruction

The agent must be told to use emotion tags. Add to persona or system prompt:

```
- Gemini 3.1 Flash TTS รองรับ emotion tags: [whispers], [laughs], [excited], etc.
- ใส่ emotion tag ใน text ก่อนส่ง text_to_speech ทุกครั้ง
```
