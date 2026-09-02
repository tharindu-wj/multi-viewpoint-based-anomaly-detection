"""A pause before every model call, so a run stays under the rate limit.

The free Gemini tier allows 15 requests per minute per model. Two observers
run in PARALLEL, so their calls land together; the retry options in config
rescue a refused call, but a run that never gets refused is faster and pays
nothing. This callback spaces the requests out instead: every model call
waits CALL_PAUSE seconds first. Async, so one observer's pause never blocks
the other's tool work.

Observation only -- returns None, the request goes through unchanged.
"""
import asyncio

#: seconds to wait before each model request. 15 requests/minute shared by
#: two parallel agents means one request per ~8 s is the ceiling; 4 s
#: halves the request rate each agent would otherwise attempt.
CALL_PAUSE = 4.0


async def pace_model_calls(callback_context, llm_request):
    """before_model_callback on every agent in the tree."""
    if CALL_PAUSE > 0:
        await asyncio.sleep(CALL_PAUSE)
    return None
