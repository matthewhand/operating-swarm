# REQ-2

Intent: the operator default LLM is the LAN LiteLLM, not a hardcoded public OpenAI model.

Success:
1. Default API base `http://198.51.100.30:8000` (OpenAI-compatible `/v1`), model `auxiliary`, provider **litellm**.
2. Reachable from LAN clients; `ALLOWED_HOSTS` / CSRF / CORS allow the LAN.
3. Global default LLM profile plus per-agent override.
4. Assist paths (quickstarts, blueprint class draft) use that default (`llm_assist.default_chat`), not a baked-in cloud model.

Constraints: Do not clone a LiteLLM catalog UI. Do not change OMB (:8802).

Owner: open-swarm engineer.
