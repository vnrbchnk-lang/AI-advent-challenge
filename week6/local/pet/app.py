import asyncio
import uuid

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse

from local import localllm
from local.pet import limits, persona, state
from local.pet.page import PAGE

PET_MODEL = "qwen2.5:1.5b-instruct"

app = FastAPI(title="Pet")

rate = limits.RateLimiter(per_ip_rate=0.4, per_ip_burst=3, global_rate=1.0, global_burst=6)
inference = asyncio.Semaphore(1)
histories = {}


def client_ip(request):
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def session_id(request):
    return request.cookies.get("pet_sid") or uuid.uuid4().hex


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    sid = session_id(request)
    response = HTMLResponse(PAGE)
    response.set_cookie("pet_sid", sid, max_age=86400, samesite="lax")
    return response


@app.get("/pet")
def pet_status():
    return state.snapshot()


@app.post("/chat")
async def chat(request: Request):
    ip = client_ip(request)
    allowed, wait, scope = rate.check(ip)
    if not allowed:
        reason = "меня перекормили, всем нужно подождать" if scope == "global" else "не так быстро, я не успеваю жевать"
        return JSONResponse(
            status_code=429,
            content={"reply": f"*пыхтит* {reason}. Загляни через {wait} c.", "retry_after": wait, "pet": state.snapshot()},
        )

    body = await request.json()
    text, clipped = limits.clip_input(body.get("message", ""))
    if not text:
        return JSONResponse(status_code=400, content={"reply": "Ты ничего не сказал!", "pet": state.snapshot()})

    pet = state.feed_and_talk()
    if pet["stuffed"]:
        return {"reply": persona.stuffed_reply(pet), "pet": pet, "clipped": clipped}

    sid = session_id(request)
    history = limits.trim_history(histories.get(sid, []))
    messages = [{"role": "system", "content": persona.system_prompt(pet)}]
    messages.extend(history)
    messages.append({"role": "user", "content": text})

    async with inference:
        reply, stats = await run_in_threadpool(
            localllm.chat, messages, PET_MODEL, 0.7, limits.NUM_CTX, limits.NUM_PREDICT,
        )

    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply})
    histories[sid] = limits.trim_history(history)

    result = JSONResponse({"reply": reply, "pet": pet, "clipped": clipped, "stats": stats})
    result.set_cookie("pet_sid", sid, max_age=86400, samesite="lax")
    return result


def run():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
