"""Single assistant with six logical role profiles, no autonomous external writes."""
from typing import TypedDict
try:
    from langgraph.graph import StateGraph, START, END
except ImportError:  # deterministic offline assistant remains available
    StateGraph = None
    START = END = None

class ChatState(TypedDict):
    message: str
    role: str
    intent: str
    result: str

KEYWORDS = {
    "lead_research": ("find leads", "prospects", "find companies", "lead discovery"),
    "proposal": ("proposal", "quote", "pricing"),
    "website": ("website", "landing page"),
    "marketing": ("ads", "campaign", "marketing plan", "social post"),
    "followups": ("follow-up", "follow up", "today's tasks", "today’s tasks"),
    "analytics": ("revenue", "conversion", "pipeline", "report"),
}

RESPONSES = {
    "lead_research": "Start in Leads. Import verified prospects or connect an authorized lead-data provider. External search and outreach require configured connectors and approval.",
    "proposal": "Open Proposals to create a draft and export PDF or DOCX. Proposed pricing must come from business-provided figures.",
    "website": "Open Websites to generate editable, deployable Next.js source. Review content and approve any deployment separately.",
    "marketing": "Open Campaigns to plan your content. Publishing requires a human approval and configured channel integration.",
    "followups": "Open Tasks and Approvals for due follow-ups and messages awaiting review. No messages are sent automatically.",
    "analytics": "Open Reports for recorded pipeline totals, clients, user-entered revenue, and conversion metrics; missing information is not estimated.",
    "general": "I can coordinate leads, proposals, websites, tasks, campaigns, approvals and reporting. Select a module or request an AI draft.",
}


def classify(state: ChatState) -> dict:
    msg = state["message"].lower()
    intent = next((key for key, words in KEYWORDS.items() if any(word in msg for word in words)), "general")
    return {"intent": intent}


def advise(state: ChatState) -> dict:
    return {"result": RESPONSES[state["intent"]]}


def compile_graph():
    if StateGraph is None:
        raise RuntimeError("LangGraph is not installed")
    graph = StateGraph(ChatState)
    graph.add_node("classify", classify)
    graph.add_node("advise", advise)
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "advise")
    graph.add_edge("advise", END)
    return graph.compile()


def respond(message: str, role: str) -> ChatState:
    state: ChatState = {"message": message, "role": role, "intent": "", "result": ""}
    if StateGraph is None:
        return {**state, **classify(state), **advise({**state, **classify(state)})}
    return compile_graph().invoke(state)
