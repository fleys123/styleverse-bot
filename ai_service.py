import asyncio
import base64
import os
import tempfile
import time
import zipfile

import fal_client
from openai import OpenAI

def _get_openrouter() -> OpenAI:
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )


def _upload(path: str) -> str:
    for attempt in range(3):
        try:
            return fal_client.upload_file(path)
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def _get_outfit(photo_path: str, scene_prompt: str) -> str:
    with open(photo_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    msg = _get_openrouter().chat.completions.create(
        model="google/gemini-2.0-flash-001",
        max_tokens=60,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                },
                {
                    "type": "text",
                    "text": (
                        f"This person will be placed in this scene: {scene_prompt}. "
                        "Suggest a specific outfit that fits both their personal style and the scene. "
                        "Reply with ONLY 3-6 words starting with 'wearing', e.g. 'wearing a casual linen shirt'. "
                        "No explanation, no punctuation at the end."
                    ),
                },
            ],
        }],
    )
    return msg.choices[0].message.content.strip()


def _subscribe(model: str, arguments: dict, timeout: int = 120) -> dict:
    for attempt in range(3):
        try:
            return fal_client.subscribe(model, arguments, client_timeout=timeout)
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


async def virtual_tryon(person_path: str, garment_path: str, category: str = "auto") -> str:
    """
    Try garment on person using FASHN v1.6 (best quality try-on on fal.ai).
    category: "auto" | "tops" | "bottoms" | "one-pieces"
    Returns CDN URL of the result image.
    """
    def _run():
        human_url = _upload(person_path)
        garment_url = _upload(garment_path)
        result = _subscribe("fal-ai/fashn/tryon/v1.6", {
            "model_image": human_url,
            "garment_image": garment_url,
            "category": category,
            "mode": "quality",
            "garment_photo_type": "auto",
            "num_samples": 1,
            "output_format": "jpeg",
        })
        return result["images"][0]["url"]

    return await asyncio.to_thread(_run)


async def tryon_in_scene(
    person_path: str, garment_path: str, category: str, scene_prompt: str
) -> str:
    """
    Combined with reversed pipeline for natural results:
    Step 1 → face-to-full-portrait places person in scene with natural pose and lighting.
    Step 2 → FASHN applies garment to person already in the scene.
    Step 3 → face-swap restores exact face from original photo.
    Returns CDN URL of the final image.
    """
    def _run():
        human_url = _upload(person_path)
        garment_url = _upload(garment_path)

        # Step 1: generate person in scene with natural pose and lighting
        scene_result = _subscribe("fal-ai/flux-2-lora-gallery/face-to-full-portrait", {
            "image_urls": [human_url],
            "prompt": (
                f"{scene_prompt}, natural relaxed pose, casual stance, "
                "same slim body build as the reference, "
                "photorealistic, high quality, cinematic lighting, sharp focus"
            ),
            "image_size": "portrait_4_3",
            "guidance_scale": 6.0,
            "num_inference_steps": 50,
            "num_images": 1,
            "lora_scale": 1.0,
            "output_format": "jpeg",
        })
        person_in_scene_url = scene_result["images"][0]["url"]

        # Step 2: FASHN — apply garment to person already in the scene
        tryon = _subscribe("fal-ai/fashn/tryon/v1.6", {
            "model_image": person_in_scene_url,
            "garment_image": garment_url,
            "category": category,
            "mode": "quality",
            "garment_photo_type": "auto",
            "num_samples": 1,
            "output_format": "jpeg",
        })
        tryon_url = tryon["images"][0]["url"]

        # Step 3: face-swap — paste exact face from original photo
        final = _subscribe("fal-ai/face-swap", {
            "base_image_url": tryon_url,
            "swap_image_url": human_url,
        })
        return final["image"]["url"]

    return await asyncio.to_thread(_run)


STYLE_PROMPTS = {
    "gta": (
        "GTA V loading screen art style, Rockstar Games character portrait, "
        "urban street background, gritty digital illustration, "
        "dramatic cinematic lighting, detailed game art"
    ),
}


async def apply_style(person_path: str, style: str) -> str:
    """Apply art style: manga uses FLUX Kontext directly; GTA uses face-to-full-portrait + face-swap."""
    def _run():
        person_url = _upload(person_path)

        if style == "manga":
            # Step 1: generate dynamic pose in interesting location
            scene = _subscribe("fal-ai/flux-2-lora-gallery/face-to-full-portrait", {
                "image_urls": [person_url],
                "prompt": (
                    "dynamic confident pose, upper body shot, "
                    "urban street or interesting location, "
                    "cinematic lighting, photorealistic, sharp focus"
                ),
                "image_size": "portrait_4_3",
                "guidance_scale": 6.0,
                "num_inference_steps": 50,
                "num_images": 1,
                "lora_scale": 1.0,
                "output_format": "jpeg",
            })
            scene_url = scene["images"][0]["url"]

            # Step 2: transform to manga style
            result = _subscribe("fal-ai/flux-kontext", {
                "image_url": scene_url,
                "prompt": (
                    "Transform into black and white manga illustration, "
                    "bold ink linework, heavy cross-hatching for shadows, "
                    "manga speed lines in background, screen tone halftone dots, "
                    "high contrast, sharp ink lines, no color, "
                    "Slam Dunk and Vagabond manga style, "
                    "keep the same face and pose"
                ),
            })
            return result["images"][0]["url"]

        else:
            # GTA: face-to-full-portrait + face-swap
            style_prompt = STYLE_PROMPTS[style]
            result = _subscribe("fal-ai/flux-2-lora-gallery/face-to-full-portrait", {
                "image_urls": [person_url],
                "prompt": style_prompt,
                "image_size": "portrait_4_3",
                "guidance_scale": 7.0,
                "num_inference_steps": 50,
                "num_images": 1,
                "lora_scale": 0.9,
                "output_format": "jpeg",
            })
            style_url = result["images"][0]["url"]
            final = _subscribe("fal-ai/face-swap", {
                "base_image_url": style_url,
                "swap_image_url": person_url,
            })
            return final["image"]["url"]

    return await asyncio.to_thread(_run)


async def insert_into_scene(person_path: str, scene_prompt: str) -> str:
    """
    Insert person into described scene.
    Step 1 → face-to-full-portrait generates natural scene from scratch (proper lighting/shadows).
    Step 2 → face-swap restores exact face from original photo.
    Returns CDN URL of the result image.
    """
    def _run():
        person_url = _upload(person_path)
        outfit = _get_outfit(person_path, scene_prompt)

        # Step 1: face-to-full-portrait — portrait shot in scene with reference photo
        scene_result = _subscribe("fal-ai/flux-2-lora-gallery/face-to-full-portrait", {
            "image_urls": [person_url],
            "prompt": f"{scene_prompt}, {outfit}, f/4 lens, natural rim lighting, well-lit face, slight angle, candid natural pose, professional portrait photography",
            "image_size": "portrait_4_3",
            "guidance_scale": 6.0,
            "num_inference_steps": 50,
            "num_images": 1,
            "lora_scale": 1.0,
            "output_format": "jpeg",
        })
        scene_url = scene_result["images"][0]["url"]

        # Step 2: face-swap — restore exact face from original photo
        final = _subscribe("fal-ai/face-swap", {
            "base_image_url": scene_url,
            "swap_image_url": person_url,
        })
        return final["image"]["url"]

    return await asyncio.to_thread(_run)


async def train_user_lora(photo_paths: list[str], user_id: int) -> tuple[str, str]:
    """
    Train a personal LoRA on the user's photos for better face preservation.
    Returns (lora_url, trigger_word). Takes ~5-15 minutes.
    """
    trigger_word = f"USR{user_id}"

    def _run():
        zip_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                zip_path = tmp.name
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, path in enumerate(photo_paths):
                    zf.write(path, f"photo_{i:03d}.jpg")
            zip_url = _upload(zip_path)
        finally:
            if zip_path and os.path.exists(zip_path):
                os.unlink(zip_path)

        result = _subscribe(
            "fal-ai/flux-lora-portrait-trainer",
            {
                "images_data_url": zip_url,
                "trigger_word": trigger_word,
                "steps": 1000,
                "multiresolution_training": True,
                "data_archive_format": "zip",
            },
            timeout=1800,
        )
        return result["diffusers_lora_file"]["url"], trigger_word

    return await asyncio.to_thread(_run)


async def insert_into_scene_lora(
    person_path: str, scene_prompt: str, lora_url: str, trigger_word: str
) -> str:
    """
    Scene generation using trained personal LoRA + face-swap for exact face.
    Returns CDN URL of the result image.
    """
    def _run():
        person_url = _upload(person_path)

        # Step 1: flux-lora generates portrait shot in scene using personal LoRA
        scene_result = _subscribe("fal-ai/flux-lora", {
            "prompt": (
                f"portrait photo of {trigger_word}, upper body shot, face and shoulders, "
                f"{scene_prompt}, candid photography, muted realistic colors, natural light, "
                "shot on 35mm film, Kodak Portra 400, shallow depth of field, "
                "correct anatomy, photorealistic, high quality"
            ),
            "negative_prompt": "deformed, ugly, cartoon, oversaturated, bad anatomy, extra limbs",
            "loras": [{"path": lora_url, "scale": 1.0}],
            "image_size": "portrait_4_3",
            "num_inference_steps": 50,
            "guidance_scale": 4.0,
            "num_images": 1,
            "output_format": "jpeg",
        })
        return scene_result["images"][0]["url"]

    return await asyncio.to_thread(_run)


async def tryon_in_scene_lora(
    person_path: str,
    garment_path: str,
    category: str,
    scene_prompt: str,
    lora_url: str,
    trigger_word: str,
) -> str:
    """
    Combo with LoRA, reversed pipeline:
    Step 1 → flux-lora generates person in scene with natural pose.
    Step 2 → FASHN applies garment to person already in scene.
    Step 3 → face-swap restores exact face.
    Returns CDN URL of the final image.
    """
    def _run():
        human_url = _upload(person_path)
        garment_url = _upload(garment_path)

        # Step 1: flux-lora generates person in scene with natural pose
        scene_result = _subscribe("fal-ai/flux-lora", {
            "prompt": (
                f"photo of {trigger_word} person, {scene_prompt}, "
                "natural relaxed pose, casual stance, "
                "photorealistic, high quality, cinematic lighting, sharp focus"
            ),
            "loras": [{"path": lora_url, "scale": 0.85}],
            "image_size": "portrait_4_3",
            "num_inference_steps": 35,
            "guidance_scale": 3.5,
            "num_images": 1,
            "output_format": "jpeg",
        })
        person_in_scene_url = scene_result["images"][0]["url"]

        # Step 2: FASHN — apply garment to person already in the scene
        tryon = _subscribe("fal-ai/fashn/tryon/v1.6", {
            "model_image": person_in_scene_url,
            "garment_image": garment_url,
            "category": category,
            "mode": "quality",
            "garment_photo_type": "auto",
            "num_samples": 1,
            "output_format": "jpeg",
        })
        tryon_url = tryon["images"][0]["url"]

        # Step 3: face-swap — paste exact face from original photo
        final = _subscribe("fal-ai/face-swap", {
            "base_image_url": tryon_url,
            "swap_image_url": human_url,
        })
        return final["image"]["url"]

    return await asyncio.to_thread(_run)
