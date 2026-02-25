from __future__ import annotations

import os
import time
import uuid
from typing import Dict, List, Optional, Literal

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

# -----------------------------
# Config
# -----------------------------
API_KEY = os.getenv("QUIZ_API_KEY", "dev-secret-change-me")  # set in env for prod

# Proper Bearer auth scheme (adds Authorize button in /docs)
bearer_scheme = HTTPBearer(auto_error=True)

def require_bearer_auth(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> bool:
    """
    Expects:
      Authorization: Bearer <QUIZ_API_KEY>
    In Swagger "Authorize", you paste only the token value (without 'Bearer ').
    """
    token = credentials.credentials
    if token != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid token")
    return True


app = FastAPI(title="Quiz Action API", version="1.0.0")

# -----------------------------
# Data models
# -----------------------------
class CreateSessionRequest(BaseModel):
    quiz_id: str = Field(..., examples=["us_history_1"])
    mode: Literal["practice", "test"] = Field(default="practice")

class CreateSessionResponse(BaseModel):
    session_id: str
    quiz_id: str
    mode: str
    status: Literal["active", "finished"]

class Progress(BaseModel):
    current: int
    total: int

class QuestionOut(BaseModel):
    question_id: str
    prompt: str
    options: List[str]
    multi_select: bool = False

class NextQuestionResponse(BaseModel):
    session_id: str
    question: Optional[QuestionOut] = None
    progress: Progress
    status: Literal["active", "finished"]

class SubmitAnswerRequest(BaseModel):
    question_id: str
    selected: List[int] = Field(..., description="List of selected option indexes (0-based).")

class SubmitAnswerResponse(BaseModel):
    session_id: str
    question_id: str
    correct: bool
    score: int
    explanation: str
    progress: Progress
    status: Literal["active", "finished"]
    next_available: bool

class SessionStateResponse(BaseModel):
    session_id: str
    quiz_id: str
    mode: str
    status: Literal["active", "finished"]
    current_index: int
    total: int
    score: int
    started_at: float
    updated_at: float

class FinishResponse(BaseModel):
    session_id: str
    status: Literal["finished"]
    score: int
    total: int

class ResultsResponse(BaseModel):
    session_id: str
    quiz_id: str
    score: int
    total: int
    answers: List[dict]

# -----------------------------
# In-memory "DB"
# -----------------------------
QUIZZES: Dict[str, List[dict]] = {
    "us_history_1": [
        {
            "question_id": "q1",
            "prompt": "In what year was the U.S. Declaration of Independence adopted?",
            "options": ["1774", "1776", "1781", "1789"],
            "correct": [1],
            "explanation": "The Declaration of Independence was adopted on July 4, 1776.",
            "multi_select": False,
        },
        {
            "question_id": "q2",
            "prompt": "Which document begins with 'We the People'?",
            "options": ["The U.S. Constitution", "The Bill of Rights", "The Articles of Confederation", "The Federalist Papers"],
            "correct": [0],
            "explanation": "The preamble to the U.S. Constitution begins with 'We the People'.",
            "multi_select": False,
        },
        {
            "question_id": "q3",
            "prompt": "Select all that were among the original 13 colonies.",
            "options": ["Georgia", "Vermont", "Pennsylvania", "Alaska"],
            "correct": [0, 2],
            "explanation": "Georgia and Pennsylvania were original colonies; Vermont and Alaska were not.",
            "multi_select": True,
        },
    ]
}

sessions: Dict[str, dict] = {}

def get_quiz_questions(quiz_id: str) -> List[dict]:
    if quiz_id not in QUIZZES:
        raise HTTPException(status_code=404, detail=f"Unknown quiz_id '{quiz_id}'")
    return QUIZZES[quiz_id]

def now_ts() -> float:
    return time.time()

# -----------------------------
# Endpoints
# -----------------------------
@app.get("/health")
def health():
    return {"ok": True}


@app.post("/quiz/sessions", response_model=CreateSessionResponse)
def create_session(req: CreateSessionRequest, _: bool = Depends(require_bearer_auth)):
    questions = get_quiz_questions(req.quiz_id)
    session_id = str(uuid.uuid4())
    started = now_ts()
    sessions[session_id] = {
        "session_id": session_id,
        "quiz_id": req.quiz_id,
        "mode": req.mode,
        "status": "active",
        "current_index": 0,
        "score": 0,
        "served_order": [q["question_id"] for q in questions],
        "answers": [],
        "started_at": started,
        "updated_at": started,
    }
    return {
        "session_id": session_id,
        "quiz_id": req.quiz_id,
        "mode": req.mode,
        "status": "active",
    }


@app.get("/quiz/sessions/{session_id}", response_model=SessionStateResponse)
def get_session(session_id: str, _: bool = Depends(require_bearer_auth)):
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    total = len(get_quiz_questions(s["quiz_id"]))
    return {
        "session_id": s["session_id"],
        "quiz_id": s["quiz_id"],
        "mode": s["mode"],
        "status": s["status"],
        "current_index": s["current_index"],
        "total": total,
        "score": s["score"],
        "started_at": s["started_at"],
        "updated_at": s["updated_at"],
    }


@app.post("/quiz/sessions/{session_id}/next", response_model=NextQuestionResponse)
def next_question(session_id: str, _: bool = Depends(require_bearer_auth)):
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    questions = get_quiz_questions(s["quiz_id"])
    total = len(questions)

    if s["status"] == "finished" or s["current_index"] >= total:
        s["status"] = "finished"
        s["updated_at"] = now_ts()
        return {
            "session_id": session_id,
            "question": None,
            "progress": {"current": total, "total": total},
            "status": "finished",
        }

    q = questions[s["current_index"]]
    progress = {"current": s["current_index"] + 1, "total": total}

    return {
        "session_id": session_id,
        "question": {
            "question_id": q["question_id"],
            "prompt": q["prompt"],
            "options": q["options"],
            "multi_select": q.get("multi_select", False),
        },
        "progress": progress,
        "status": "active",
    }


@app.post("/quiz/sessions/{session_id}/answer", response_model=SubmitAnswerResponse)
def submit_answer(session_id: str, req: SubmitAnswerRequest, _: bool = Depends(require_bearer_auth)):
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    questions = get_quiz_questions(s["quiz_id"])
    total = len(questions)

    if s["status"] == "finished":
        raise HTTPException(status_code=400, detail="Session already finished")

    if s["current_index"] >= total:
        s["status"] = "finished"
        raise HTTPException(status_code=400, detail="No active question to answer")

    current_q = questions[s["current_index"]]
    if req.question_id != current_q["question_id"]:
        raise HTTPException(
            status_code=409,
            detail=f"Answer question_id mismatch. Expected '{current_q['question_id']}'"
        )

    if any(a["question_id"] == req.question_id for a in s["answers"]):
        raise HTTPException(status_code=409, detail="Question already answered")

    if not req.selected:
        raise HTTPException(status_code=400, detail="selected cannot be empty")
    if any((i < 0 or i >= len(current_q["options"])) for i in req.selected):
        raise HTTPException(status_code=400, detail="selected contains out-of-range index")

    selected_norm = sorted(set(req.selected))
    correct_norm = sorted(current_q["correct"])

    is_correct = selected_norm == correct_norm
    if is_correct:
        s["score"] += 1

    answered_at = now_ts()
    s["answers"].append({
        "question_id": req.question_id,
        "selected": selected_norm,
        "correct": is_correct,
        "answered_at": answered_at,
    })

    s["current_index"] += 1
    if s["current_index"] >= total:
        s["status"] = "finished"

    s["updated_at"] = answered_at

    answered_count = len(s["answers"])
    progress = {"current": answered_count, "total": total}

    return {
        "session_id": session_id,
        "question_id": req.question_id,
        "correct": is_correct,
        "score": s["score"],
        "explanation": current_q["explanation"],
        "progress": progress,
        "status": s["status"],
        "next_available": (s["status"] == "active"),
    }


@app.post("/quiz/sessions/{session_id}/finish", response_model=FinishResponse)
def finish_session(session_id: str, _: bool = Depends(require_bearer_auth)):
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    total = len(get_quiz_questions(s["quiz_id"]))
    s["status"] = "finished"
    s["updated_at"] = now_ts()
    return {
        "session_id": session_id,
        "status": "finished",
        "score": s["score"],
        "total": total,
    }


@app.get("/quiz/sessions/{session_id}/results", response_model=ResultsResponse)
def results(session_id: str, _: bool = Depends(require_bearer_auth)):
    s = sessions.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    total = len(get_quiz_questions(s["quiz_id"]))
    return {
        "session_id": session_id,
        "quiz_id": s["quiz_id"],
        "score": s["score"],
        "total": total,
        "answers": s["answers"],
    }
