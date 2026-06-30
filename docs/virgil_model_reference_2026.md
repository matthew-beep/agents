# Virgil — Model Selection Reference (2026)

> Last updated: June 2026  
> Supersedes model recommendations in `athena_bottleneck_architecture.md`

This document maps current open-weight models to Virgil's inference architecture. Hardware is fixed: RTX 5060 Ti 16GB VRAM, 96GB DDR5 RAM. Model selection is a hardware question first, use-case question second.

**Key realization (June 2026):** the original two-instance, two-tier model plan (small GPU model + separate large CPU model) undersells what this specific hardware can do. The VRAM/RAM ratio here — modest 16GB VRAM paired with generous 96GB RAM — is close to ideal for **MoE expert offloading**, where dense/attention layers live on GPU and the bulk of expert weights live in RAM. This makes a single large, capable MoE model a realistic *generalist* option, rather than juggling a small interactive model and a separate large background model.

Two viable approaches are documented below: the simple two-tier Ollama setup (lower effort, proven, good enough for current build phase), and the single-generalist-MoE approach via llama.cpp (more capable, more setup, the likely end state).

---

## Architecture Recap

Virgil runs two Ollama instances:

| Instance | Hardware | Role | Latency tolerance |
|---|---|---|---|
| **GPU Ollama** | RTX 5060 Ti 16GB VRAM | Interactive chat, per-item summarization, routing | Low — real-time |
| **CPU Ollama** (`OLLAMA_NUM_GPU=0`) | 96GB DDR5 RAM | Background Celery synthesis, deep research passes | High — async |

The calling code doesn't care which instance handles inference — all requests go through the same `chat(messages, model, tools)` abstraction. Model swapping is a config change.

Cloud API endpoints (Claude, OpenAI, DeepSeek, GLM, MiniMax) plug into the same abstraction for tasks where quality or parallelism justifies cost.

**Hardware constraint to keep in mind:** only one model is hot per Ollama instance at a time. Sub-agents and orchestration steps that call the LLM serialize on a single GPU — there is no local parallelism for concurrent LLM calls. This is why Virgil's agent loops should push decisions into deterministic code wherever possible and reserve LLM calls for summarization/synthesis specifically (see `orchestration` doc). Cloud APIs are the only way to get genuine concurrent inference if a future phase needs it.

**Multi-GPU is not a realistic upgrade path on this board.** The ASUS B650-A has one true PCIe 4.0 x16 slot (current GPU) and one chipset slot that only runs at x4 bandwidth — too slow for tensor-parallel inter-GPU communication. A single larger-VRAM card is a better upgrade path than a second 16GB card.

---

## Approach A: Single Generalist via MoE Expert Offloading (Recommended End State)

### The core insight

MoE models only activate a small fraction of total parameters per token (the rest sit idle). This means the dormant expert weights don't need fast VRAM — they can live in RAM and get fetched on demand when the router selects them. Dense/attention layers (always active) stay on GPU; experts (mostly idle) live in RAM.

```
GPU VRAM (16GB):  attention layers, dense layers, KV cache, active experts
CPU RAM (96GB):   the bulk of expert weight blocks, fetched on demand
```

This is the opposite of the usual local-LLM constraint. Most homelab builds have decent VRAM and limited RAM — Virgil's hardware has modest VRAM (16GB) and generous RAM (96GB), which is exactly the profile MoE expert offloading is designed to exploit. A dense model can't use the spare RAM at all; an MoE model turns it into a real asset.

### Recommended model — Qwen3.6 35B-A3B

```
Total parameters:  35B
Active per token:  ~3B (8 routed + 1 shared expert of 256)
Context:           262K native, extensible to 1M via YaRN
License:           Apache 2.0
Modalities:        text, vision, video
Thinking mode:     yes, with "thinking preservation" across turns
```

Beats its predecessor (Qwen3.5 35B-A3B) on every official benchmark at the same active-parameter cost — Terminal-Bench 2.0 jumps 40.5→51.5, SWE-bench Verified 70.0→73.4, MCPMark 27.0→37.0. The gains come from better training, not a heavier architecture, so there's no reason to run 3.5 once 3.6 is available.

Also beats Qwen3-Coder-Next (80B-A3B) on reasoning (+10.6 points) and throughput (~1.9x faster) despite Coder-Next's larger total parameter count — same active compute, better-trained routing wins. Coder-Next is not recommended as the primary local model; Qwen3.6 is the better generalist *and* the better coder.

### Recommended setup

```bash
./llama-server \
  --model qwen3.6-35b-a3b-Q5_K_M.gguf \
  --n-gpu-layers 40 \      # all dense/attention layers to GPU
  --n-cpu-moe 35 \         # bulk of expert blocks to RAM
  --no-mmap \              # load fully upfront, avoid page faults
  --flash-attn \           # efficient KV handling
  --ctx-size 131072 \      # 128K context
  --cache-type-k q8_0 \    # quantized KV cache
  --port 8080
```

**Quantization: Q5_K_M, not the aggressive Q3/i1-Q4 quants seen in community posts.** Those posts came from builds with only 32GB RAM, which forced aggressive compression to fit expert weights. With 96GB RAM there's no such pressure — Q5_K_M (~25GB total, ~17GB of which lands in RAM as offloaded experts) is comfortable and meaningfully higher quality than Q4.

**Expected performance on this hardware:** ~25-40 tokens/sec. Community reports on weaker hardware (7700 XT 20GB, 32GB RAM) get 30+ t/s with aggressive quantization; more RAM and faster DDR5 here should land in a similar or better range even at higher quantization.

**Engine note:** this requires llama.cpp directly, not Ollama — Ollama doesn't yet expose `--n-cpu-moe` or support the model's vision projector. llama.cpp's server mode still exposes an OpenAI-compatible `/v1/chat/completions` endpoint, so the `chat()` abstraction doesn't change — only the base URL does. Docker Compose just needs one more service definition pointing at the llama.cpp server image with the flags above.

### What this replaces

A single Qwen3.6 35B-A3B instance run this way can plausibly cover both the "fast interactive" and "smart background" roles that previously required two separate models on two separate Ollama instances — fast enough for chat, capable enough for long-horizon agentic tasks (community reports of 25-45 minute autonomous coding/tool-use sessions with zero failed tool calls). Thinking mode toggles per-request the same way Qwen3 32B's did.

This doesn't eliminate the GPU/CPU split entirely — concurrent interactive + background load still benefits from separation — but it does mean the *same model* can serve both roles instead of maintaining two different ones.

---

## Approach B: Two-Tier Ollama Setup (Simpler, Proven, Good for Current Build Phase)

This is the original split-tier plan. Lower setup complexity, works today in Ollama without touching llama.cpp, and is sufficient for proving the GitHub Trend Watcher agent loop and earlier roadmap phases. Revisit Approach A once local model quality becomes the actual bottleneck rather than the agent loop architecture itself.

### Tier 1 — GPU (Interactive, 16GB VRAM)

For interactive chat and the per-item summarization pass in agent map-reduce. Speed matters. Must fit in 16GB at Q4.

### Primary — Qwen3 14B
```bash
ollama pull qwen3:14b
```
- **VRAM**: ~9GB at Q4 — leaves headroom for other processes
- **Why**: Strong tool calling, instruction following, structured JSON output. The current default for interactive Virgil chat. Well-tested in your existing setup.
- **Use for**: Chat, per-item GitHub trend summarization, document Q&A, routing decisions

### Alternative — Qwen3.5 27B (MoE)
```bash
ollama pull qwen3.5:27b
```
- **VRAM**: ~18GB at Q4 — tight but fits on 16GB with aggressive quantization; safer on CPU tier
- **Why**: 27B total but MoE architecture means active parameter count is lower. SWE-bench Verified 72.4%, vision+audio native, 262K context. The best local model for agentic coding tasks.
- **Use for**: When you need more reasoning depth interactively; better fit as a CPU tier model

### Wildcard — gpt-oss 20B (MoE)
```bash
ollama pull gpt-oss:20b
```
- **VRAM**: ~16GB at MXFP4 — fits exactly
- **Why**: OpenAI's first open-weight model, Apache 2.0, native function calling, configurable reasoning effort (low/medium/high). Worth benchmarking against Qwen3 14B specifically for tool call reliability in your agent loop.
- **Use for**: Testing as an alternative agent-tier model; may outperform Qwen on structured tool calling

### Compact — Phi-4-reasoning 14B
```bash
ollama pull phi4-reasoning
```
- **VRAM**: ~9GB — same footprint as Qwen3 14B
- **Why**: MIT licensed, exceptional reasoning for its size. AIME 2024 75.3% — beats DeepSeek-R1 70B on math. Interesting for Virgil's thinking-mode background tasks.
- **Use for**: Tasks requiring deliberate chain-of-thought at interactive speed; not a general replacement for Qwen

### Vision-capable — Gemma 4 12B
```bash
ollama pull gemma4:12b
```
- **VRAM**: fits in 16GB, runs at ~85 t/s
- **Why**: Native audio + vision, encoder-free multimodal architecture. Most relevant if Virgil ever needs to process screenshots, images in documents, or audio.
- **Use for**: Future multimodal document ingestion; not needed for current roadmap

---

### Tier 2 — CPU/Background (Async Celery Tasks, 96GB RAM)

For the Celery research pipeline synthesis pass. Latency-tolerant — these tasks run in the background and results are surfaced asynchronously. Quality over speed.

### Primary — Qwen3 32B
```bash
ollama pull qwen3:32b
```
- **RAM**: ~20GB at Q4 — comfortable headroom in 96GB
- **Why**: Hybrid thinking mode is the key feature for Virgil's use case. Toggle `/think` for deep research synthesis, `/no_think` for fast summarization. Same model, two modes — no weight swap needed.
- **Use for**: GitHub Trend Watcher synthesis pass, cross-document research synthesis, project kickoff goal refinement

### High-quality alternative — Qwen3.5 27B
```bash
ollama pull qwen3.5:27b
```
- **RAM**: ~18GB at Q4
- **Why**: SWE-bench 72.4%, vision+audio, 262K context window. Best overall capability for background research tasks that involve code analysis or long documents.
- **Use for**: Research sweeps over large document sets, codebase analysis tasks

### Reasoning specialist — DeepSeek-R1 32B (Distill)
```bash
ollama pull deepseek-r1:32b
```
- **RAM**: ~20GB at Q4
- **Why**: MIT licensed, explicit chain-of-thought before answering. Useful when you want the reasoning trace visible — could feed into Virgil's re-entry briefs or research summaries where showing the thinking adds value.
- **Use for**: Tasks where reasoning transparency matters; math and algorithm-heavy synthesis

### Long-context — Llama 4 Scout
```bash
ollama pull llama4:scout
```
- **RAM**: ~55GB at Q4 — fits in 96GB but leaves less headroom
- **Why**: 10M token context window. Can ingest an entire mid-sized codebase or large document collection in one prompt — eliminates chunking entirely for certain tasks.
- **Use for**: Whole-repository analysis, very long research synthesis where context compaction is a bottleneck

---

## Cloud API Tier

Same `chat()` abstraction, external endpoint. Use when local quality isn't sufficient or for one-off high-value tasks.

| Model | Best for | Cost profile |
|---|---|---|
| **Claude Opus 4.x** | Highest quality synthesis, nuanced writing | High |
| **Claude Sonnet 4.x** | Balanced quality/cost for research tasks | Medium |
| **DeepSeek V4 Flash** | High-volume routine summarization | Very low |
| **DeepSeek V4 Pro** | Frontier-level coding and agentic tasks via API | Low-medium |
| **GLM-5.2** (via API) | Best open-weight agentic coding, 1M context, MIT | Low |

DeepSeek V4 Flash is the best default for high-volume Celery passes where you want cloud quality without Claude-level cost. GLM-5.2 via API is the strongest option for long-horizon agentic coding tasks specifically.

---

## Decision Guide — Which Model for Which Task

| Virgil task | Recommended model | Tier |
|---|---|---|
| Interactive chat | Qwen3 14B | GPU |
| Per-item GitHub trend summarization | Qwen3 14B (no_think) | GPU |
| Routing / complexity classification | Qwen3 14B | GPU |
| Tool call agent loop | Qwen3 14B or gpt-oss 20B | GPU |
| Cross-item synthesis (GitHub digest) | Qwen3 32B (think) | CPU |
| Deep research sweep synthesis | Qwen3.5 27B or Qwen3 32B | CPU |
| Re-entry briefs | Qwen3 32B (think) | CPU |
| Project goal refinement conversation | Claude Sonnet (API) or Qwen3 32B | CPU / Cloud |
| Whole-codebase analysis | Llama 4 Scout | CPU |
| High-volume routine passes at scale | DeepSeek V4 Flash | Cloud API |

---

## Thinking Mode Strategy

Qwen3 32B supports hybrid thinking mode — this is the key lever for Virgil's two-speed needs:

```python
# Fast summarization pass (per-item in map-reduce)
chat(messages, model="qwen3:32b", options={"think": False})

# Deep synthesis pass (cross-item, research reports)
chat(messages, model="qwen3:32b", options={"think": True})
```

Same model, same Ollama instance, different reasoning depth. No weight loading overhead between modes.

---

## Quantization Reference

| Model | Q4 size | Q5 size | Recommended |
|---|---|---|---|
| Qwen3 8B | ~5GB | ~6GB | Q5_K_M if VRAM allows |
| Qwen3 14B | ~9GB | ~10GB | Q4_K_M (GPU tier) |
| Qwen3 32B | ~20GB | ~24GB | Q4_K_M (CPU tier) |
| Qwen3.5 27B | ~18GB | ~22GB | Q4_K_M |
| Qwen3.6 35B-A3B | ~21GB | ~25GB | **Q5_K_M** (Approach A — split across VRAM/RAM via expert offload, not loaded fully on one device) |
| DeepSeek-R1 32B | ~20GB | ~24GB | Q4_K_M |
| Llama 4 Scout | ~55GB | — | Q4_K_M (RAM only) |
| Phi-4-reasoning 14B | ~9GB | ~10GB | Q4_K_M |

Use `_K_M` (K-quant Medium) variants for best quality/size balance. Only drop to `_K_S` or imatrix (`i1-`) quants if RAM is genuinely constrained — not the case here at 96GB.

General quantization rule: higher Q number = less compression = better quality = more memory. Q3 is a downgrade from Q4, not an upgrade — don't reach for lower quants without a specific VRAM/RAM constraint forcing it.

---

## What Changed from Previous Recommendations

The original `athena_bottleneck_architecture.md` recommended:
- Tier 1: `qwen2.5:7b-q4_K_M`
- Tier 2: `qwen2.5:30b-q5_K_M`  
- Tier 3: `llama3.1:70b-q4_K_M`

**First update rationale (Approach B):**
- Qwen3 14B replaces Qwen2.5 7B — same VRAM footprint, significantly better reasoning and tool calling
- Qwen3 32B with thinking mode replaces the static Qwen2.5 30B — hybrid think/no_think covers both speed and quality needs in one model
- Llama 4 Scout (10M context) replaces Llama 3.1 70B as the long-context specialist — better suited to Virgil's research use cases
- gpt-oss 20B and Phi-4-reasoning are new additions not available when the original doc was written

**Second update rationale (Approach A added):**
- Realized the two-tier split undersells the hardware. 16GB VRAM + 96GB RAM is a strong ratio specifically for MoE expert offloading, not just dense-model tiering
- Qwen3.6 35B-A3B via llama.cpp with `--n-cpu-moe` is now the recommended end-state model — one capable generalist instead of a small interactive model and separate large background model
- Confirmed Qwen3-Coder-Next is not the better pick despite the larger 80B parameter count — Qwen3.6 35B-A3B beats it on both reasoning and coding benchmarks at the same active-parameter cost
- Confirmed Qwen3.6 strictly beats Qwen3.5 at the same size/footprint — no reason to run 3.5 once 3.6 is available
- This is an additive update — Approach B remains valid and lower-effort for the current GitHub Trend Watcher build phase; Approach A is the planned migration once agent loop architecture is proven and model quality becomes the bottleneck
