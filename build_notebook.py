"""Generate model.ipynb with proper Jupyter format for local training."""
import json
from pathlib import Path

def code_cell(source, id_num):
    return {
        "cell_type": "code",
        "execution_count": None,
        "id": f"cell{id_num:02d}",
        "metadata": {},
        "outputs": [],
        "source": source if isinstance(source, list) else [source]
    }

def markdown_cell(source, id_num):
    return {
        "cell_type": "markdown",
        "id": f"cell{id_num:02d}",
        "metadata": {},
        "source": source if isinstance(source, list) else [source]
    }

cells = []

# ============================================================================
# OVERVIEW
cells.append(markdown_cell("""# SDXL Poster LoRA — Local Fine-Tuning

Fine-tunes the **background visual** generator behind NexMarket's poster pipeline on the local RTX 3050 (6 GB).

## What this can and cannot change

The poster pipeline is two stages:
1. **SDXL** generates a background *visual* (no text).
2. **`PosterComposer`** overlays the headline, CTA, logo and brand colours with PIL.

A LoRA trained here affects **stage 1 only**. If posters look wrong because of typography, text contrast, or layout, that is stage 2 and no amount of diffusion fine-tuning will fix it.

## Hard constraints on this machine

| Constraint | Value | Consequence |
|---|---|---|
| VRAM | 6.0 GB | LoRA only — a full fine-tune needs ~40 GB |
| `bitsandbytes` | broken | no 8-bit Adam; use plain AdamW |
| torch / diffusers | 2.1.2+cu121 / 0.30.3 | pinned — this project has broken twice on version drift |

The 6 GB fit comes from **pre-computing VAE latents and text embeddings once**, then freeing the VAE and both text encoders so only the UNet occupies VRAM during training.""", 0))

# ============================================================================
# CELL 1: ENVIRONMENT AUDIT
cells.append(markdown_cell("## Cell 1 — Environment audit\n\nVerifies the GPU and pins down what is actually installed. Run this first; every later cell assumes it passed.", 1))
cells.append(code_cell([
    "import sys, subprocess, importlib\n",
    "import torch\n",
    "\n",
    "print(\"python :\", sys.version.split()[0])\n",
    "print(\"torch  :\", torch.__version__, \"| cuda:\", torch.cuda.is_available())\n",
    "\n",
    "if torch.cuda.is_available():\n",
    "    p = torch.cuda.get_device_properties(0)\n",
    "    VRAM_GB = p.total_memory / 1024**3\n",
    "    print(f\"gpu    : {p.name}  {VRAM_GB:.1f} GB\")\n",
    "    torch.cuda.empty_cache()\n",
    "    free, total = torch.cuda.mem_get_info()\n",
    "    print(f\"free   : {free/1024**3:.2f} GB of {total/1024**3:.2f} GB\")\n",
    "else:\n",
    "    VRAM_GB = 0\n",
    "    print(\"!! no CUDA device - training is not viable on CPU\")\n",
    "\n",
    "for m in [\"diffusers\", \"transformers\", \"accelerate\", \"peft\", \"safetensors\"]:\n",
    "    try:\n",
    "        print(f\"{m:13s}:\", importlib.import_module(m).__version__)\n",
    "    except ImportError:\n",
    "        print(f\"{m:13s}: NOT INSTALLED\")\n"
], 2))

# ============================================================================
# CELL 2: INSTALL PEFT
cells.append(markdown_cell("""## Cell 2 — Install `peft`

`peft` provides the LoRA layers. Pinned to a release known to work with diffusers 0.30.3 / torch 2.1.2.

**This project has twice been broken by dependency drift.** Install exactly this pin, and do not let pip resolve `torch`, `numpy`, or `diffusers` to something newer.""", 3))
cells.append(code_cell([
    "import sys\n",
    "!{sys.executable} -m pip install --no-deps \"peft==0.13.2\"\n",
    "\n",
    "import importlib, peft\n",
    "importlib.reload(peft)\n",
    "print(\"peft:\", peft.__version__)\n",
    "\n",
    "# Confirm nothing else moved.\n",
    "import torch, numpy, diffusers\n",
    "print(\"torch:\", torch.__version__, \"| numpy:\", numpy.__version__, \"| diffusers:\", diffusers.__version__)\n",
    "assert torch.__version__.startswith(\"2.1.2\"),  \"torch drifted - reinstall torch==2.1.2+cu121\"\n",
    "assert numpy.__version__.startswith(\"1.\"),     \"numpy drifted to 2.x - reinstall numpy<2.0.0\"\n",
    "assert diffusers.__version__ == \"0.30.3\",      \"diffusers drifted - reinstall diffusers==0.30.3\"\n",
    "print(\"\\nenvironment intact\")\n"
], 4))

# ============================================================================
# CELL 3: DATASET AUDIT
cells.append(markdown_cell("""## Cell 3 — Dataset audit  ⚠️ **decision gate**

Before writing a training loop, establish what we would be training *on*.

The thing to look for is **provenance**. If all candidate images were produced by the same SDXL pipeline we are about to fine-tune, then training on them is **self-distillation**: the model is fed its own output, learns nothing it did not already encode, and amplifies its own artifacts. This is the path to model collapse — worth several hours to avoid.""", 5))
cells.append(code_cell([
    "import sqlite3\n",
    "from pathlib import Path\n",
    "from collections import Counter\n",
    "\n",
    "BACKEND = Path(\"backend\")\n",
    "DB      = BACKEND / \"nexmarket.db\"\n",
    "\n",
    "con = sqlite3.connect(str(DB), timeout=15)\n",
    "con.execute(\"PRAGMA busy_timeout=15000\")\n",
    "\n",
    "posters = con.execute(\"SELECT id, provider, image_url, prompt_used FROM posters\").fetchall()\n",
    "by_provider = Counter(p[1] for p in posters)\n",
    "\n",
    "products = con.execute(\"\"\"\n",
    "    SELECT c.product_name, COUNT(*) FROM posters p\n",
    "    JOIN campaigns c ON c.id = p.campaign_id\n",
    "    GROUP BY c.product_name ORDER BY 2 DESC\n",
    "\"\"\").fetchall()\n",
    "\n",
    "n_evals = con.execute(\"SELECT COUNT(*) FROM poster_evaluations\").fetchone()[0]\n",
    "scores  = [r[0] for r in con.execute(\"SELECT overall_score FROM poster_evaluations\")]\n",
    "con.close()\n",
    "\n",
    "print(f\"poster rows      : {len(posters)}\")\n",
    "print(f\"by provider      : {dict(by_provider)}\")\n",
    "print(f\"distinct products: {len(products)}  ->  {products[:3]}\")\n",
    "print(f\"evaluations      : {n_evals}  scores={scores}\")\n",
    "\n",
    "# Provenance: anything our own pipeline made is unusable as ground truth.\n",
    "SELF_GENERATED = {\"local-sdxl\", \"local-sdxl-composed\", \"openai-dalle3\", \"mock\"}\n",
    "self_made = sum(v for k, v in by_provider.items() if k in SELF_GENERATED)\n",
    "\n",
    "print(\"\\n\" + \"=\" * 62)\n",
    "print(f\"self-generated : {self_made}/{len(posters)}\")\n",
    "\n",
    "DATA_IS_USABLE = (\n",
    "    len(posters) - self_made >= 100 and len(products) >= 10\n",
    ")\n",
    "\n",
    "if not DATA_IS_USABLE:\n",
    "    print(\"VERDICT: NOT USABLE as SDXL training data (use external dataset).\")\n",
    "else:\n",
    "    print(\"VERDICT: usable - proceed.\")\n",
    "print(\"=\" * 62)\n"
], 6))

# ============================================================================
# CELL 4: POINT AT DATASET
cells.append(markdown_cell("""## Cell 4 — Load the external dataset

Point at the folder of **external** marketing images (not pipeline output).

```
data/poster_train/
    pexels_0000.jpg
    pexels_0000.txt      <- caption, same stem
    pexels_0001.jpg
    pexels_0001.txt
    ...
```

Captions describe *the visual*, since that is all SDXL produces — subject, environment, lighting, composition, mood. No headlines or CTAs: those are drawn by `PosterComposer`, never by the model.

> `nxmposter, photo of a matte-black water bottle on wet slate, hard rim light from the left, deep shadows, condensation, centred hero product shot, cool teal palette`

**Licensing is on you** — only train on images you have the right to use.""", 7))
cells.append(code_cell([
    "from pathlib import Path\n",
    "\n",
    "# ── configure ────────────────────────────────────────────────────────────────\n",
    "DATA_DIR     = Path(\"data/poster_train\")   # external images\n",
    "OUTPUT_DIR   = Path(\"backend/ml/lora\")     # where the trained LoRA lands\n",
    "TRIGGER_WORD = \"nxmposter\"                 # rare token; put it in every caption\n",
    "RESOLUTION   = 768                         # 1024 is SDXL-native but will OOM on 6GB\n",
    "# ─────────────────────────────────────────────────────────────────────────────\n",
    "\n",
    "OUTPUT_DIR.mkdir(parents=True, exist_ok=True)\n",
    "EXTS = {\".png\", \".jpg\", \".jpeg\", \".webp\"}\n",
    "\n",
    "if not DATA_DIR.exists():\n",
    "    print(f\"DATA_DIR does not exist: {DATA_DIR.resolve()}\")\n",
    "    images = []\n",
    "else:\n",
    "    images = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() in EXTS)\n",
    "\n",
    "pairs = []\n",
    "missing_caption = 0\n",
    "for img in images:\n",
    "    cap_file = img.with_suffix(\".txt\")\n",
    "    if cap_file.exists():\n",
    "        caption = cap_file.read_text(encoding=\"utf-8\").strip()\n",
    "    else:\n",
    "        caption = TRIGGER_WORD\n",
    "        missing_caption += 1\n",
    "    if TRIGGER_WORD not in caption:\n",
    "        caption = f\"{TRIGGER_WORD}, {caption}\"\n",
    "    pairs.append((img, caption))\n",
    "\n",
    "print(f\"images found     : {len(pairs)}\")\n",
    "print(f\"missing captions : {missing_caption}\")\n",
    "if pairs:\n",
    "    print(\"\\nsample:\")\n",
    "    for img, cap in pairs[:2]:\n",
    "        print(f\"  {img.name}\")\n",
    "        print(f\"    {cap[:100]}...\")\n",
    "\n",
    "if len(pairs) < 20:\n",
    "    print(f\"\\n{len(pairs)} images is not enough (need ~20 minimum).\")\n",
    "\n",
    "READY = len(pairs) >= 20\n",
    "print(f\"\\nREADY = {READY}\")\n"
], 8))

# ============================================================================
# CELL 5: PRECOMPUTE LATENTS & EMBEDDINGS
cells.append(markdown_cell("""## Cell 5 — Pre-compute latents and text embeddings

**This is the step that makes 6 GB work.**

The VAE (~330 MB) and SDXL's *two* text encoders (CLIP ViT-L + OpenCLIP bigG, ~1.4 GB together) are only needed to convert images→latents and captions→embeddings. Doing that once and caching frees them, so only the UNet occupies VRAM during training.

The VAE runs in **fp32**: SDXL's base VAE produces NaNs in fp16.""", 9))
cells.append(code_cell([
    "import gc, torch\n",
    "from PIL import Image\n",
    "import torchvision.transforms as T\n",
    "from diffusers import AutoencoderKL\n",
    "from transformers import CLIPTextModel, CLIPTextModelWithProjection, AutoTokenizer\n",
    "\n",
    "assert READY, \"Cell 4 reported READY=False - supply images first.\"\n",
    "\n",
    "MODEL_ID = \"stabilityai/stable-diffusion-xl-base-1.0\"\n",
    "device   = \"cuda\"\n",
    "\n",
    "tf = T.Compose([\n",
    "    T.Resize(RESOLUTION, interpolation=T.InterpolationMode.BILINEAR),\n",
    "    T.CenterCrop(RESOLUTION),\n",
    "    T.ToTensor(),\n",
    "    T.Normalize([0.5], [0.5]),          # -> [-1, 1]\n",
    "])\n",
    "\n",
    "# ── 1. images -> latents (fp32 VAE) ────────────────────────────────────────\n",
    "# Only the fp16-variant weights are typically cached locally (no plain\n",
    "# diffusion_pytorch_model.safetensors), so variant=\"fp16\" is required to find\n",
    "# the file at all. torch_dtype=float32 still upcasts on load and runs the\n",
    "# forward pass in fp32, which is what actually avoids the VAE's NaN overflow.\n",
    "vae = AutoencoderKL.from_pretrained(\n",
    "    MODEL_ID, subfolder=\"vae\", variant=\"fp16\", use_safetensors=True,\n",
    "    torch_dtype=torch.float32, local_files_only=True,\n",
    ").to(device).eval()\n",
    "\n",
    "latents = []\n",
    "with torch.no_grad():\n",
    "    for i, (img_path, _) in enumerate(pairs):\n",
    "        if i % 50 == 0: print(f\"  encode {i}/{len(pairs)}\")\n",
    "        img = Image.open(img_path).convert(\"RGB\")\n",
    "        x   = tf(img).unsqueeze(0).to(device, torch.float32)\n",
    "        lat = vae.encode(x).latent_dist.sample() * vae.config.scaling_factor\n",
    "        latents.append(lat.squeeze(0).cpu())\n",
    "\n",
    "print(f\"latents: {len(latents)} x {tuple(latents[0].shape)}\")\n",
    "\n",
    "del vae; gc.collect(); torch.cuda.empty_cache()\n",
    "\n",
    "# ── 2. captions -> embeddings (SDXL needs BOTH encoders) ────────────────────\n",
    "tok1 = AutoTokenizer.from_pretrained(MODEL_ID, subfolder=\"tokenizer\",   local_files_only=True)\n",
    "tok2 = AutoTokenizer.from_pretrained(MODEL_ID, subfolder=\"tokenizer_2\", local_files_only=True)\n",
    "# text_encoder_2 also only has the fp16-variant file cached; text_encoder\n",
    "# happens to have both, but pass variant=\"fp16\" on both for consistency.\n",
    "te1  = CLIPTextModel.from_pretrained(\n",
    "    MODEL_ID, subfolder=\"text_encoder\",   variant=\"fp16\",\n",
    "    torch_dtype=torch.float16, local_files_only=True).to(device).eval()\n",
    "te2  = CLIPTextModelWithProjection.from_pretrained(\n",
    "    MODEL_ID, subfolder=\"text_encoder_2\", variant=\"fp16\",\n",
    "    torch_dtype=torch.float16, local_files_only=True).to(device).eval()\n",
    "\n",
    "prompt_embeds_all, pooled_all = [], []\n",
    "with torch.no_grad():\n",
    "    for i, (_, caption) in enumerate(pairs):\n",
    "        if i % 50 == 0: print(f\"  embed {i}/{len(pairs)}\")\n",
    "        i1 = tok1(caption, padding=\"max_length\", max_length=77, truncation=True, return_tensors=\"pt\").input_ids.to(device)\n",
    "        i2 = tok2(caption, padding=\"max_length\", max_length=77, truncation=True, return_tensors=\"pt\").input_ids.to(device)\n",
    "\n",
    "        o1 = te1(i1, output_hidden_states=True).hidden_states[-2]\n",
    "        o2 = te2(i2, output_hidden_states=True)\n",
    "        pooled = o2.text_embeds\n",
    "        o2h    = o2.hidden_states[-2]\n",
    "\n",
    "        prompt_embeds_all.append(torch.cat([o1, o2h], dim=-1).squeeze(0).cpu())\n",
    "        pooled_all.append(pooled.squeeze(0).cpu())\n",
    "\n",
    "print(f\"prompt_embeds: {tuple(prompt_embeds_all[0].shape)}  pooled: {tuple(pooled_all[0].shape)}\")\n",
    "\n",
    "del te1, te2, tok1, tok2; gc.collect(); torch.cuda.empty_cache()\n",
    "print(f\"\\nfree VRAM: {torch.cuda.mem_get_info()[0]/1024**3:.2f} GB\")\n"
], 10))

# ============================================================================
# CELL 6: ATTACH LORA
cells.append(markdown_cell("""## Cell 6 — Attach LoRA to the UNet

Only the attention projections (`to_q`, `to_k`, `to_v`, `to_out.0`) get adapters. That is where cross-attention injects the text conditioning, so it is where style adaptation lands — and it keeps the trainable parameter count near ~1 % of the UNet.

Base weights stay frozen in fp16; the LoRA parameters are fp32 for stable gradients.""", 11))
cells.append(code_cell([
    "from diffusers import UNet2DConditionModel, DDPMScheduler\n",
    "from peft import LoraConfig, get_peft_model\n",
    "\n",
    "LORA_RANK  = 16     # rank of the low-rank adaptation\n",
    "LORA_ALPHA = 16     # scaling\n",
    "\n",
    "# Only the fp16-variant unet weights are typically cached locally - same\n",
    "# reason as the VAE fix above.\n",
    "unet = UNet2DConditionModel.from_pretrained(\n",
    "    MODEL_ID, subfolder=\"unet\", variant=\"fp16\",\n",
    "    torch_dtype=torch.float16, local_files_only=True,\n",
    ").to(device)\n",
    "\n",
    "unet.requires_grad_(False)              # freeze the base model\n",
    "unet.enable_gradient_checkpointing()    # trades compute for VRAM\n",
    "\n",
    "lora_cfg = LoraConfig(\n",
    "    r=LORA_RANK,\n",
    "    lora_alpha=LORA_ALPHA,\n",
    "    init_lora_weights=\"gaussian\",\n",
    "    target_modules=[\"to_q\", \"to_k\", \"to_v\", \"to_out.0\"],\n",
    ")\n",
    "unet.add_adapter(lora_cfg)\n",
    "\n",
    "# LoRA params in fp32 - fp16 gradients on rank-16 matrices underflow.\n",
    "lora_params = [p for p in unet.parameters() if p.requires_grad]\n",
    "for p in lora_params:\n",
    "    p.data = p.data.float()\n",
    "\n",
    "n_train = sum(p.numel() for p in lora_params)\n",
    "n_total = sum(p.numel() for p in unet.parameters())\n",
    "print(f\"trainable: {n_train:,} / {n_total:,}  ({100*n_train/n_total:.2f}%)\")\n",
    "\n",
    "noise_scheduler = DDPMScheduler.from_pretrained(MODEL_ID, subfolder=\"scheduler\", local_files_only=True)\n",
    "print(f\"free VRAM: {torch.cuda.mem_get_info()[0]/1024**3:.2f} GB\")\n"
], 12))

# ============================================================================
# CELL 7: TRAIN
cells.append(markdown_cell("""## Cell 7 — Train

Standard diffusion objective: noise the cached latent to a random timestep, ask the UNet to predict the noise, minimise MSE.

SDXL additionally requires `added_cond_kwargs` with the pooled text embedding plus `time_ids`. Measured on this 3050: ~6 min per 100 steps at 768 px (800 steps ≈ 50 min) — VRAM peaks around 5.6/6.0 GB, so close anything else GPU-heavy before running this.""", 13))
cells.append(code_cell([
    "import math, random, time\n",
    "from torch.nn import functional as F\n",
    "\n",
    "# ── hyperparameters ──────────────────────────────────────────────────────────\n",
    "MAX_STEPS      = 800     # ~100 imgs: 500-1500 is the useful band\n",
    "LR             = 1e-4    # LoRA tolerates a far higher LR than a full fine-tune\n",
    "GRAD_ACCUM     = 4       # effective batch 4 with batch_size 1\n",
    "SAVE_EVERY     = 200\n",
    "# ─────────────────────────────────────────────────────────────────────────────\n",
    "\n",
    "optimizer = torch.optim.AdamW(lora_params, lr=LR, weight_decay=1e-2)\n",
    "lr_sched  = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=MAX_STEPS)\n",
    "\n",
    "# SDXL micro-conditioning: (orig_h, orig_w, crop_top, crop_left, target_h, target_w)\n",
    "time_ids = torch.tensor(\n",
    "    [[RESOLUTION, RESOLUTION, 0, 0, RESOLUTION, RESOLUTION]],\n",
    "    dtype=torch.float16, device=device,\n",
    ")\n",
    "\n",
    "unet.train()\n",
    "N = len(latents)\n",
    "losses, t0 = [], time.time()\n",
    "\n",
    "for step in range(1, MAX_STEPS + 1):\n",
    "    accum_loss = 0.0\n",
    "    for _ in range(GRAD_ACCUM):\n",
    "        i = random.randrange(N)\n",
    "\n",
    "        lat = latents[i].unsqueeze(0).to(device, torch.float16)\n",
    "        pe  = prompt_embeds_all[i].unsqueeze(0).to(device, torch.float16)\n",
    "        po  = pooled_all[i].unsqueeze(0).to(device, torch.float16)\n",
    "\n",
    "        noise     = torch.randn_like(lat)\n",
    "        timesteps = torch.randint(0, noise_scheduler.config.num_train_timesteps, (1,), device=device).long()\n",
    "        noisy     = noise_scheduler.add_noise(lat, noise, timesteps)\n",
    "\n",
    "        pred = unet(\n",
    "            noisy, timesteps, encoder_hidden_states=pe,\n",
    "            added_cond_kwargs={\"text_embeds\": po, \"time_ids\": time_ids},\n",
    "        ).sample\n",
    "\n",
    "        loss = F.mse_loss(pred.float(), noise.float()) / GRAD_ACCUM\n",
    "        loss.backward()\n",
    "        accum_loss += loss.item()\n",
    "\n",
    "    torch.nn.utils.clip_grad_norm_(lora_params, 1.0)\n",
    "    optimizer.step(); lr_sched.step(); optimizer.zero_grad(set_to_none=True)\n",
    "    losses.append(accum_loss)\n",
    "\n",
    "    if step % 25 == 0:\n",
    "        recent = sum(losses[-25:]) / 25\n",
    "        el     = time.time() - t0\n",
    "        eta    = el / step * (MAX_STEPS - step)\n",
    "        print(f\"step {step:4d}/{MAX_STEPS}  loss {recent:.4f}  \"\n",
    "              f\"lr {lr_sched.get_last_lr()[0]:.2e}  eta {eta/60:.1f}m  \"\n",
    "              f\"vram {torch.cuda.max_memory_allocated()/1024**3:.2f}GB\")\n",
    "\n",
    "    if step % SAVE_EVERY == 0 or step == MAX_STEPS:\n",
    "        from peft.utils import get_peft_model_state_dict\n",
    "        from safetensors.torch import save_file\n",
    "        sd  = {k: v.to(torch.float16).cpu() for k, v in get_peft_model_state_dict(unet).items()}\n",
    "        out = OUTPUT_DIR / \"sdxl_poster_lora.safetensors\"\n",
    "        save_file(sd, str(out))\n",
    "        print(f\"  saved {out}  ({sum(v.numel() for v in sd.values()):,} params)\")\n",
    "\n",
    "print(f\"\\ndone in {(time.time()-t0)/60:.1f} min\")\n"
], 14))

# ============================================================================
# CELL 8: COMPARE BEFORE/AFTER
cells.append(markdown_cell("""## Cell 8 — Compare before / after

The only honest test is the same prompt and the same **seed**, with and without the adapter. Anything else confounds the LoRA's effect with sampling noise.""", 15))
cells.append(code_cell([
    "import gc, torch\n",
    "from diffusers import StableDiffusionXLPipeline\n",
    "\n",
    "del unet; gc.collect(); torch.cuda.empty_cache()\n",
    "\n",
    "TEST_PROMPT = f\"{TRIGGER_WORD}, marketing visual for a premium water bottle, studio lighting, centred hero shot\"\n",
    "TEST_SEED   = 12345\n",
    "\n",
    "pipe = StableDiffusionXLPipeline.from_pretrained(\n",
    "    MODEL_ID, torch_dtype=torch.float16, use_safetensors=True,\n",
    "    variant=\"fp16\", local_files_only=True,\n",
    ")\n",
    "pipe.enable_model_cpu_offload()\n",
    "pipe.enable_vae_slicing()\n",
    "\n",
    "def render(tag):\n",
    "    g = torch.Generator(device=\"cpu\").manual_seed(TEST_SEED)\n",
    "    img = pipe(TEST_PROMPT, num_inference_steps=28, guidance_scale=7.5,\n",
    "               width=RESOLUTION, height=RESOLUTION, generator=g).images[0]\n",
    "    img.save(f\"compare_{tag}.png\")\n",
    "    return img\n",
    "\n",
    "before = render(\"before\")\n",
    "\n",
    "lora_file = OUTPUT_DIR / \"sdxl_poster_lora.safetensors\"\n",
    "if lora_file.exists():\n",
    "    pipe.load_lora_weights(str(lora_file))\n",
    "    after = render(\"after\")\n",
    "    print(\"Comparison saved: compare_before.png vs compare_after.png\")\n",
    "else:\n",
    "    print(f\"No LoRA found at {lora_file}\")\n"
], 16))

# ============================================================================
# CELL 9: INTEGRATION
cells.append(markdown_cell("""## Cell 9 — Integrate into the backend

Once the comparison above is genuinely better, wire it in. The change is small and additive: load the adapter after the pipeline is built, only if the file exists.

**In `backend/ai/vision/sdxl_service.py`** at the end of `_do_load()` — after the memory optimisations, before `self._pipeline = pipe`:

```python
# Optional fine-tuned poster LoRA. Absent by default; the base model is used
# unchanged when the file is not present.
lora_path = Path(settings.SDXL_LORA_PATH)
if lora_path.exists():
    pipe.load_lora_weights(str(lora_path))
    logger.info("sdxl lora loaded path=%s", lora_path)
```

**In `backend/app/core/config.py`**:

```python
SDXL_LORA_PATH: str = "backend/ml/lora/sdxl_poster_lora.safetensors"
```

**In `requirements.txt`** add:

```
peft==0.13.2
```

**In `backend/app/services/ai/poster_generator.py`** — the prompt must include the trigger word:

In `_build_spec_prompt`, prepend `TRIGGER_WORD`:

```python
spec = f"{TRIGGER_WORD}, {spec}"
```

Then verify with the existing test suite:

```bash
pytest tests/test_main.py::test_poster_generation -v
```
""", 17))

# ============================================================================
# Build the notebook
notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "codemirror_mode": {
                "name": "ipython",
                "version": 3
            },
            "file_extension": ".py",
            "mimetype": "text/x-python",
            "name": "python",
            "nbconvert_exporter": "python",
            "pygments_lexer": "ipython3",
            "version": "3.11.0"
        }
    },
    "nbformat": 4,
    "nbformat_minor": 4
}

output = Path("model.ipynb")
output.write_text(json.dumps(notebook, indent=2), encoding="utf-8")
print(f"✓ Generated {output} ({len(cells)} cells)")
print(f"  Ready to run cell-by-cell in Jupyter or VS Code")
