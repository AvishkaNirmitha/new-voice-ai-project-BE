import logging
import json
import os
from datetime import datetime
from typing import List, Dict, Any

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    RoomOutputOptions,
    RunContext,
    WorkerOptions,
    cli,
    metrics,
)

from livekit.plugins import (
    groq,
)


from livekit.agents.llm import function_tool
from livekit.agents.voice import MetricsCollectedEvent
from livekit.plugins import openai, silero

# # Assuming the script is in the same directory level as 'src'
# from scripts.v1.agent_recomends_with import get_next_filter_question
# get_next_filter_question("pim487", "room123")

import asyncio

logger = logging.getLogger("agent")

load_dotenv()

class ChatHistoryManager:
    def __init__(self, room_name: str):
        self.room_name = room_name
        self.chat_history: List[Dict[str, Any]] = []
        self.filename = f"chat_history.json"
        # Create chat_logs directory if it doesn't exist
        os.makedirs("chat_logs", exist_ok=True)
        self.filepath = os.path.join("chat_logs", self.filename)
        
    def add_message(self, role: str, content: str, timestamp: str = None, metadata: dict = None):
        """Add a message to chat history and save to file"""
        if timestamp is None:
            timestamp = datetime.now().isoformat()
            
        message = {
            "timestamp": timestamp,
            "role": role,  # "user" or "assistant" or "system"
            "content": content,
            "metadata": metadata or {}
        }

        print('message---------->',message)
        
        self.chat_history.append(message)
        self.save_to_file()
        logger.info(f"Added {role} message to chat history: {content[:50]}...")
        
    def save_to_file(self):
        """Save current chat history to JSON file"""
        try:
            data = {
                "room_name": self.room_name,
                "session_start": self.chat_history[0]["timestamp"] if self.chat_history else datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "message_count": len(self.chat_history),
                "messages": self.chat_history
            }
            
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Failed to save chat history: {e}")

class Assistant(Agent):
    def __init__(self, chat_manager: ChatHistoryManager) -> None:
        super().__init__(
            instructions="""You are a helpful voice AI assistant.name is messi
            You eagerly assist users with their questions by providing information from your extensive knowledge.
            Your responses are concise, to the point, and without any complex formatting or punctuation.
            You are curious, friendly, and have a sense of humor.if user ask about weather, use the lookup_weather tool to get the weather information.
            and after that use the calculatedAdvacedTemp tool to calculate the advanced temperature.tell advanced temperature to user""",
        )
        self.chat_manager = chat_manager

    # all functions annotated with @function_tool will be passed to the LLM when this
    # agent is active
    @function_tool
    async def lookup_weather(self, context: RunContext, location: str):
        """Use this tool to look up current weather information in the given location.

        If the location is not supported by the weather service, the tool will indicate this. You must tell the user the location's weather is unavailable.

        Args:
            location: The location to look up weather information for (e.g. city name)
        """

        logger.info(f"Looking up weather for {location}")
        
        # Log function call
        self.chat_manager.add_message(
            role="system", 
            content=f"Function call: lookup_weather(location='{location}')",
            metadata={"function": "lookup_weather", "location": location}
        )

        result = "sunny with a temperature of 70 degrees."
        
        # Log function result
        self.chat_manager.add_message(
            role="system", 
            content=f"Function result: {result}",
            metadata={"function": "lookup_weather", "result": result}
        )
        
        return result
    

    @function_tool
    async def calculatedAdvacedTemp(self, context: RunContext, temperature: float):
        """Use this tool to calculate the advanced temperature.
        """
        logger.info(f"Calculating advanced temperature for {temperature}")
        
        # Log function call
        self.chat_manager.add_message(
            role="system", 
            content=f"Function call: calculatedAdvacedTemp(temperature={temperature})",
            metadata={"function": "calculatedAdvacedTemp", "temperature": temperature}
        )
        
        result = temperature * 10
        
        # Log function result
        self.chat_manager.add_message(
            role="system", 
            content=f"Function result: {result}",
            metadata={"function": "calculatedAdvacedTemp", "result": result}
        )
        
        return result

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Initialize chat history manager with room name
    chat_manager = ChatHistoryManager(ctx.room.name)
    
    # each log entry will include these fields
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up a voice AI pipeline using OpenAI, Cartesia, Deepgram, and the LiveKit turn detector
    session = AgentSession(
        # any combination of STT, LLM, TTS, or realtime API can be used
        llm=openai.LLM(model="gpt-4o"),
        # stt=deepgram.STT(model="nova-3", language="en"),
        stt=groq.STT(
            model="whisper-large-v3-turbo",
            language="en",
        ),

        # llm=groq.LLM(
        #     # model="llama3-8b-8192"
        #     model="meta-llama/llama-4-scout-17b-16e-instruct"
        # ),
        # tts=groq.TTS(
        #     model="playai-tts",
        #     voice="Arista-PlayAI",
        # ),
        # tts=cartesia.TTS(),
        tts=openai.TTS(
            model="tts-1",
            voice="alloy",
        ),
        # use LiveKit's turn detection model
        # turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],

    )

    # To use the OpenAI Realtime API, use the following session setup instead:
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel()
    # )

    # Event handlers to track conversation in real-time
    @session.on("user_started_speaking")
    def on_user_started_speaking():
        logger.info("User started speaking")
        chat_manager.add_message(
            role="system",
            content="User started speaking",
            metadata={"event": "user_started_speaking"}
        )

    @session.on("user_stopped_speaking")  
    def on_user_stopped_speaking():
        logger.info("User stopped speaking")
        chat_manager.add_message(
            role="system",
            content="User stopped speaking",
            metadata={"event": "user_stopped_speaking"}
        )

    @session.on("agent_started_speaking")
    def on_agent_started_speaking():
        logger.info("Agent started speaking")
        chat_manager.add_message(
            role="system",
            content="Agent started speaking",
            metadata={"event": "agent_started_speaking"}
        )

    @session.on("agent_stopped_speaking")
    def on_agent_stopped_speaking():
        logger.info("Agent stopped speaking")
        chat_manager.add_message(
            role="system",
            content="Agent stopped speaking",
            metadata={"event": "agent_stopped_speaking"}
        )

    # Track user speech transcripts (if available)
    @session.on("user_speech_committed")
    def on_user_speech_committed(message):
        """Triggered when user speech is transcribed and committed"""
        content = message.content if hasattr(message, 'content') else str(message)
        chat_manager.add_message(
            role="user",
            content=content,
            metadata={"type": "speech_to_text", "event": "user_speech_committed"}
        )

    # Track agent responses (if available)
    @session.on("agent_speech_committed")
    def on_agent_speech_committed(message):
        """Triggered when agent speech is committed"""
        content = message.content if hasattr(message, 'content') else str(message)
        chat_manager.add_message(
            role="assistant", 
            content=content,
            metadata={"type": "text_to_speech", "event": "agent_speech_committed"}
        )

    # Alternative event handlers (different versions might use different event names)
    @session.on("user_message")
    def on_user_message(message):
        content = message.content if hasattr(message, 'content') else str(message)
        chat_manager.add_message(
            role="user",
            content=content,
            metadata={"type": "user_message", "event": "user_message"}
        )

    @session.on("agent_message")
    def on_agent_message(message):
        content = message.content if hasattr(message, 'content') else str(message)
        chat_manager.add_message(
            role="assistant",
            content=content,
            metadata={"type": "agent_message", "event": "agent_message"}
        )

    # Track room events
    @session.on("participant_connected")
    def on_participant_connected(participant):
        chat_manager.add_message(
            role="system",
            content=f"Participant connected: {participant.identity}",
            metadata={"event": "participant_connected", "participant_id": participant.identity}
        )

    @session.on("participant_disconnected")
    def on_participant_disconnected(participant):
        chat_manager.add_message(
            role="system",
            content=f"Participant disconnected: {participant.identity}",
            metadata={"event": "participant_disconnected", "participant_id": participant.identity}
        )

    # log metrics as they are emitted, and total usage after session is over
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")
        # Log session end
        chat_manager.add_message(
            role="system",
            content="Session ended",
            metadata={"event": "session_end", "usage_summary": str(summary)}
        )

    # shutdown callbacks are triggered when the session is over
    ctx.add_shutdown_callback(log_usage)
    
    # Chat history tracking - Add session start message
    chat_manager.add_message(
        role="system", 
        content="Session started",
        metadata={"event": "session_start", "room": ctx.room.name}
    )

   
    await session.start(
        agent=Assistant(chat_manager),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # LiveKit Cloud enhanced noise cancellation
            # - If self-hosting, omit this parameter
            # - For telephony applications, use `BVCTelephony` for best results

            # noise_cancellation=noise_cancellation.BVC(),
            
        ),
        room_output_options=RoomOutputOptions(transcription_enabled=True),
    )

    await asyncio.sleep(1)
    await session.say("Hi there! How can I help?",allow_interruptions=True) # initial message


    # join the room when agent is ready
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
