import time

from dotenv import load_dotenv

from text_ocr_processor import TextOCRProcessor
from vision_agents.core import Agent, AgentLauncher, Runner, User
from vision_agents.core.llm.events import RealtimeUserSpeechTranscriptionEvent
from vision_agents.plugins import gemini, getstream

load_dotenv()


def _is_text_query(user_text: str) -> bool:
    text = user_text.lower()
    text_signals = ("text", "read", "see", "screen", "showing", "visible")
    question_signals = ("what", "which", "can you", "tell me")
    return any(word in text for word in text_signals) and any(
        word in text for word in question_signals
    )


async def create_agent(**kwargs) -> Agent:
    ocr_processor = TextOCRProcessor(
        fps=2,
        language="en",
        conf_threshold=0.4,
    )

    rag_store = await gemini.create_file_search_store(
        name="my-agent-gpu-knowledge",
        knowledge_dir="./my-agent/knowledge",
        extensions=[".txt"],
    )

    llm = gemini.Realtime(file_search_store=rag_store)

    @llm.register_function(
        description=(
            "Search GPU knowledge using Gemini File Search over local knowledge docs. "
            "Use this as the primary retrieval source for GPU-related answers."
        )
    )
    async def search_gpu_knowledge(query: str) -> str:
        return await rag_store.search(query, top_k=2)

    agent = Agent(
        edge=getstream.Edge(),
        agent_user=User(name="Assistant", id="agent"),
        instructions=(
            "You are a video agent. You are detecting GPU hardware racks in an AI factory. "
            "Your goal is to read the text being shown to you and output only GPU-related information. "
            "When the user asks about visible text, call search_gpu_knowledge first and base your response only on tool output."
        ),
        llm=llm,
        processors=[ocr_processor],
    )

    @agent.events.subscribe
    async def on_user_speech(event: RealtimeUserSpeechTranscriptionEvent):
        if event.mode != "final":
            return
        if not _is_text_query(event.text):
            return

        detected_text, detected_at = ocr_processor.get_latest_text_snapshot()
        if not detected_text:
            await agent.simple_response(
                "I don't see readable text yet. Please hold the text steady and closer to the camera.",
                interrupt=False,
            )
            return

        age_seconds = time.monotonic() - detected_at
        freshness_note = (
            "This is from the current frame."
            if age_seconds <= 5
            else "This is the most recent text I detected."
        )
        await agent.simple_response(
            (
                f"{freshness_note} OCR text: '{detected_text}'. "
                "Use search_gpu_knowledge with this OCR text and respond with GPU info only based on that tool output."
            ),
            interrupt=False,
        )

    return agent


async def join_call(agent: Agent, call_type: str, call_id: str, **kwargs) -> None:
    call = await agent.create_call(call_type, call_id)
    async with agent.join(call):
        await agent.simple_response(
            "Hi! Show text to the camera and ask me what text I can see."
        )
        await agent.finish()


if __name__ == "__main__":
    Runner(AgentLauncher(create_agent=create_agent, join_call=join_call)).cli()
