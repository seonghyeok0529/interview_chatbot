
# interview_chatbot.py

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()
from fastapi.responses import JSONResponse
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI
import os

print("[디버그] .env 로딩 결과:")
print("API_LOGIN_ID =", os.getenv("API_LOGIN_ID"))
print("API_LOGIN_PW =", os.getenv("API_LOGIN_PW"))
print("API_BASE_URL =", os.getenv("API_BASE_URL"))
print("OPENAI_API_KEY =", os.getenv("OPENAI_API_KEY"))
# ────────────────────────────────────────────────────────────────
# ❶ Environment & constants
# ----------------------------------------------------------------
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:5173")  # ← backend root
LOGIN_ENDPOINT = "/auth/signin"  # POST with {id, password} → {accessToken, expiresIn}
OPENAI_MODEL = "gpt-4o-mini"  # light & fast; swap to gpt-4o for prod

LOGIN_ID = os.getenv("API_LOGIN_ID")
LOGIN_PW = os.getenv("API_LOGIN_PW")

if not (LOGIN_ID and LOGIN_PW):
    raise RuntimeError("Set API_LOGIN_ID & API_LOGIN_PW env‑vars before starting.")

OpenAI.api_key = os.getenv("OPENAI_API_KEY")
if not OpenAI.api_key:
    raise RuntimeError("Set OPENAI_API_KEY env‑var (sk‑...) before starting.")

# ────────────────────────────────────────────────────────────────
# ❷ Pydantic I/O models
# ----------------------------------------------------------------
class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    answer: str

# ────────────────────────────────────────────────────────────────
# ❸ Token management – memoise until near expiry
# ----------------------------------------------------------------
_token_cache: Dict[str, Optional[str]] = {"token": None, "exp": None}

def _refresh_token() -> str:
    """Login & cache JWT until (expiresIn − 60)s."""
    url = f"{API_BASE_URL}{LOGIN_ENDPOINT}"
    resp = requests.post(url, json={"email": LOGIN_ID, "password": LOGIN_PW}, timeout=10)
    if resp.status_code != 200:
        raise HTTPException(500, detail=f"Login failed: {resp.text}")
    data = resp.json()
    _token_cache["token"] = data["accessToken"]
    _token_cache["exp"] = datetime.utcnow() + timedelta(seconds=data.get("expiresIn", 900) - 60)
    return _token_cache["token"]

def get_token() -> str:
    if _token_cache["token"] and datetime.utcnow() < _token_cache["exp"]:
        return _token_cache["token"]
    return _refresh_token()

# ────────────────────────────────────────────────────────────────
# ❹ GPT helpers
# ----------------------------------------------------------------
SYSTEM_PARSER = (
    "사용자가 질문에서 인터뷰 업체명(회사명)과 날짜(가능하면 YYYY-MM-DD)를 추출해 JSON으로만 답하십시오. "
    "형식: {\"company\":\"\", \"date\":\"\"}. 날짜가 없으면 null 또는 공란." )

SYSTEM_ANSWERER = (
    "당신은 부동산 바이어 미팅 요약 전문 비서입니다. 다음 원본 요약을 읽고 사용자의 질문에 친절하고 간결하게 답하세요. "
    "불필요한 영어 표현을 지양하고, 요약을 bullet 3‑5개로 정리한 뒤 마지막에 필요한 next‑step을 제안하십시오." )

def gpt_extract_company_date(question: str) -> Dict[str, Optional[str]]:
    functions = [{
        "name": "extract_parameters",
        "description": "Extract company and date from message",
        "parameters": {
            "type": "object",
            "properties": {
                "company": {"type": "string", "description": "회사명"},
                "date": {"type": "string", "description": "YYYY-MM-DD 날짜"}
            },
            "required": ["company"]
        }
    }]
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "다음 질문에서 회사명과 날짜를 추출해 JSON 함수로 반환하세요."},
            {"role": "user", "content": question}
        ],
        functions=functions,
        function_call={"name": "extract_parameters"},
        temperature=0
    )

    print("📤 GPT 응답 전체:", response)

    try:
        args = json.loads(response.choices[0].message.function_call.arguments)
        return args
    except Exception as e:
        raise HTTPException(400, detail=f"회사/날짜 파싱 실패: {e}")

def gpt_rewrite_answer(question: str, raw_summaries: List[str]) -> str:
    joined = "\n\n".join(raw_summaries)
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    completion = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_ANSWERER},
            {"role": "user", "content": f"질문: {question}"},
            {"role": "assistant", "content": f"원본 요약:\n{joined}"},
        ],
        temperature=0.4,
    )
    return completion.choices[0].message.content.strip()

# ────────────────────────────────────────────────────────────────
# ❺ Backend API helpers
# ----------------------------------------------------------------

def api_get(path: str, token: str, params: dict = None):
    resp = requests.get(f"{API_BASE_URL}{path}", params=params or {}, headers={"Authorization": f"Bearer {token}"}, timeout=10)
    if resp.status_code == 401:
        # stale token – refresh once
        token = _refresh_token()
        resp = requests.get(f"{API_BASE_URL}{path}", params=params or {}, headers={"Authorization": f"Bearer {token}"}, timeout=10)
    resp.raise_for_status()
    return resp.json()

def search_interviewees(token: str, name: str, company: str, date: Optional[str]):
    params = {"limit": 50, "offset": 0, "nameSearch": name, "companySearch": company}
    if date:
        params["dateSearch"] = date
    print("📤 인터뷰이 검색 파라미터:", params)
    data = api_get("/interview/interviewees", token, params)
    return data.get("interviewees", [])

def fetch_interviewee_list(token: str, name: str, company: str) -> list:
    url = f"{API_BASE_URL}/interviewee/list"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"limit": 50, "offset": 0, "nameSearch": name, "companySearch": company}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json().get("data", {}).get("items", [])

def fetch_interview_detail(token: str, interviewee_id: str):
    try:
        url = f"{API_BASE_URL}/interview/interviewees/{interviewee_id}"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ 인터뷰 상세 조회 실패: {e}")
        return None

# ────────────────────────────────────────────────────────────────
# ❻ FastAPI routes
# ----------------------------------------------------------------
app = FastAPI(title="Interview Chatbot", version="1.0.0")

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # Step 1: parse company & date from free‑text question
    parsed = gpt_extract_company_date(req.question)
    company = (parsed.get("company") or "").strip()
    name = (parsed.get("name") or "").strip()
    date = parsed.get("date") or None

    if not company:
        raise HTTPException(400, detail="질문에서 회사명을 찾지 못했습니다. 예: ‘7월 10일에 ABC 대부랑 무슨 얘기했지?’")

    # Step 2/3: auth → search interviewees
    token = get_token()
    candidates = search_interviewees(token, name, company, date)
    if not candidates:
        raise HTTPException(404, detail="해당 조건의 인터뷰 기록을 찾지 못했습니다.")

    # Step 4: fetch summaries (most recent first)
    raw_summaries: List[str] = []

    for iv in candidates:
        interviewee_id = iv["intervieweeId"]  # ✅ 인터뷰이 ID 추출
        print("🧾 인터뷰이 JSON:", json.dumps(iv, indent=2, ensure_ascii=False))

        detail = fetch_interview_detail(token, interviewee_id)
        if detail is None:
            print("❌ 인터뷰 상세 정보를 가져오지 못했습니다.")
            continue

        logs = detail.get("logs", [])
        if not logs:
            print("❌ 인터뷰 로그가 없습니다.")
            continue

        # 최신 로그를 기준으로 summary 추출
        latest_log = logs[0]  # logs가 최신순 정렬되어 있다고 가정
        summary_text = latest_log.get("summary") or "[요약 없음]"

        raw_summaries.append(
            f"● {iv['name']} | {iv.get('companyName') or '회사명 없음'} | {iv['updatedAt']}\n{summary_text.strip()}"
        )

    if not raw_summaries:
        raise HTTPException(404, detail="인터뷰 요약을 찾을 수 없습니다.")

    # Step 5: let GPT rewrite nicely
    answer = gpt_rewrite_answer(req.question, raw_summaries)
    return ChatResponse(answer=answer)

# ────────────────────────────────────────────────────────────────
# End of file

```