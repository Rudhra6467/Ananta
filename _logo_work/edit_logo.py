import asyncio
import base64
import os

from dotenv import load_dotenv
from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage

load_dotenv("/app/backend/.env")

PROMPT = (
    "Edit this emblem. KEEP ONLY these four elements: (1) the outer metallic "
    "circular ring, (2) the central 3D trident, (3) the silver upward zig-zag "
    "stock-market trending arrow line, and (4) the small constellation/network "
    "dots. Keep the dark graphite + matte-silver metallic color theme. "
    "COMPLETELY DELETE AND ERASE the following so they do NOT appear AT ALL, not "
    "even faintly: the damaru (hand drum), the OM symbol, and the lotus flower. "
    "These three must be 100% gone. "
    "REMOVE the four-point sparkle/star. REMOVE all text ('ANANTA' and "
    "'ALGORITHMIC AI TRADING') — zero text. "
    "Output a PNG with a FULLY TRANSPARENT alpha background: no dark panel, no "
    "background fill, no brushed-metal backdrop — ONLY the emblem floating on "
    "transparency. Center it with about 20-25 percent empty padding around it. "
    "High resolution, crisp clean edges, premium metallic finish. "
    "Render the emblem in BRIGHT polished matte-SILVER / chrome metal so it stands "
    "out clearly. Place it on a SOLID PURE BLACK (#000000) background — uniform "
    "pure black, no texture, no gradient, no panel. Center it with about 20-25 "
    "percent empty black padding around the emblem."
)


async def main():
    with open("/app/_logo_work/src.png", "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    api_key = os.getenv("EMERGENT_LLM_KEY")
    chat = LlmChat(api_key=api_key, session_id="ananta-logo-edit", system_message="You are an expert logo editor.")
    chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])

    msg = UserMessage(text=PROMPT, file_contents=[ImageContent(b64)])
    text, images = await chat.send_message_multimodal_response(msg)
    print("text:", (text or "")[:120])
    if not images:
        print("NO IMAGES RETURNED")
        return
    for i, img in enumerate(images):
        out = f"/app/_logo_work/edited_{i}.png"
        with open(out, "wb") as f:
            f.write(base64.b64decode(img["data"]))
        print("saved", out, img["mime_type"])


asyncio.run(main())
