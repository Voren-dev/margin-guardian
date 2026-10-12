# Margin Guardian

AI margin analyst built for the AMD Developer Hackathon: ACT III (lablab.ai), Evolus Business Agents track.
Work in progress.

## Setup

1. Copy `.env.example` to `.env` and fill in the values.
2. Check the AMD Token Factory connection: `python3 scripts/check_amd.py`

## Environment variables

| Name | What it is |
|---|---|
| `AMD_TOKENFACTORY_API_KEY` | Team API key from AMD Token Factory |
| `AMD_TOKENFACTORY_BASE_URL` | OpenAI-compatible base URL of the shared model endpoints: `https://developer.amd.com.cn/radeon/api/v1` |
| `AMD_MODEL` | Model served on AMD GPUs used by the main agent, for example `Gemma-4-31B-IT` |
