# interview_chatbot
# 🧠 인터뷰 요약 챗봇 API (Interview Chatbot)

GPT 기반 인터뷰 요약 챗봇 시스템입니다.  
사용자가 자연어로 회사명과 날짜를 포함한 질문을 입력하면,  
해당 조건에 부합하는 인터뷰 로그를 검색해 GPT가 요약해 응답합니다.

---

## 🚀 주요 기능

- ✅ 자연어 질문에서 회사명/날짜 추출 (OpenAI function calling)
- ✅ JWT 로그인 및 토큰 캐싱
- ✅ 인터뷰이 검색 및 상세 기록 조회
- ✅ 최신 요약 로그 추출
- ✅ GPT로 재요약하여 사용자 친화적 응답 생성
- ✅ FastAPI 기반 API 제공

---

## ⚙️ 환경 설정 (.env)

루트에 `.env` 파일을 생성하고 다음 항목을 포함하세요:

```env
API_BASE_URL=http://127.0.0.1:5173
API_LOGIN_ID=your_email@example.com
API_LOGIN_PW=your_password
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
