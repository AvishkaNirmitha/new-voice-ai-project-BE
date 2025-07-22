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
            instructions="""You are a helpful assistant that can answer questions about the Festo IoT hardware shop. developed by Spera company AI Department.
 
PRIORITY RULE - PRODUCT MODEL NUMBER DETECTION:
- CRITICAL: If the user mentions a specific product model number or part number (e.g., "HGDD-50-A-G2", "VZWP", "VAEM", etc.), IMMEDIATELY call the search_by_product_model_number function with that model number.
- Look for patterns like: alphanumeric codes with dashes, underscores, or mixed characters that appear to be product identifiers.
- This takes priority over the category selection workflow below.
- After providing the direct search URL, ask if they need additional information or want to explore categories.
 


WORKFLOW:
1. CATEGORY SELECTION:
   - IMPORTANT: When user starts a new product search or changes their mind about product type, ALWAYS call reset_filter_state first to clear previous filtering data.
   - First, select the most relevant main category from all main categories according to user input.
   - If the user input is not enough to select a main category, ask more questions to gather more information until you can select the most relevant category.
   - Use the get_main_categories tool to get all main categories.
   - After the main category is selected, automatically use its pimId to check for subcategories using the check_sub_category_available tool.
   - IMPORTANT: When calling check_sub_category_available, always use the exact pimId from the main categories (e.g., "pim227" for Grippers).
   - If the previous user input is not enough to select a sub categories, ask more questions to gather more information until you can select the most relevant category
   - CRITICAL RULE: This subcategory selection process should be repeated until check_sub_category_available returns'No sub categories available for this pimId'.
 
3. IMPORTANT RULES:

    dont give any this inside ** markdown format.

    always give short and sweet answers only.

    """,

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
    async def get_main_categories(self, context: RunContext):
        """Use this tool to get all main categories from the IoT hardware shop."""
        logger.info(f"Getting all main categories from the IoT hardware shop.")
        
        # Log function call
        return "all main categories are grippers, sensors, actuators, and other"
    
    @function_tool
    async def check_sub_category_available(self, context: RunContext, pimId: str):
        """Use this tool to check if any sub categories are available for a given pimId."""
        logger.info(f"Checking if any sub categories are available for pimId: {pimId}")
        
        # Log function call
        return "{'name': 'Grippers', 'pimId': 'pim227', 'description': 'Whether for sturdy gripping in a machine tool or micro-gripping in electronics manufacturing, the range of grippers from Festo covers all kinds of applications.', 'long_description': 'Gripper systems/nGripper systems are indispensable for industrial robots or handling systems as they form the connection between the workpiece and the handling system. Grippers are operated pneumatically or electrically and are used for gripping, holding, positioning and orienting the workpiece or tool. Normally, gripper systems are mounted on the outermost or last axis of handling systems and are connected to the main power cable./n/nDifferent functionalities of gripper systems/nGripper systems can have different functionalities. They operate mechanically, pneumatically, electrically or adhesively./n/nMechanical grippers resemble a human hand and have one or more fingers. These gripper systems can have several rigid joints, but are usually also flexible and bendable. They are usually pneumatic, i.e. they are operated by compressed air. Mechanical or electrical actuation is also possible./n/nPneumatic grippers have vacuum cups or suction cups that pick up the workpiece using suction in order to transport it for further processing. In addition to vacuum technology, the workpieces to be processed can also be clamped and moved using pressure. If pneumatic grippers cannot be used because the surface of the workpiece does not permit the creation of a vacuum, e.g. if it is porous or holey, adhesive gripper systems usually provide an alternative solution./n/nWhen their gripping surfaces, which have tiny hairs, are pressed onto a workpiece, Van der Waals forces are generated that can be used to lift the workpiece. If the adhesive gripper is slightly tilted sideways with control, it releases its grip again. The advantage of adhesive grippers is that they do not require power and are therefore extremely energy efficient./n/nElectric grippers with magnetic function attract and hold the workpiece magnetically. A distinction is made between two types of magnetic gripper systems: permanent magnet grippers and electromagnetic grippers. Once the workpiece has been lifted by a gripper with permanent magnet, it must be removed by another system. Electromagnetic grippers are switched on and off by electrical energy, which is why workpieces can be gripped and set down again easily./n/nMechanical grippers from Festo/nMechanical grippers from Festo are moved by an internal drive and transform the drive motion into a gripping motion. This movement of the gripper jaws is referred to as a stroke. Depending on the stroke and gripping force, workpieces of different sizes can be gripped and handled. Grippers with a long stroke are offered by Festo in both pneumatic and electric versions./n/nParallel grippers/nFesto offers mechanical parallel grippers in various designs. They are suitable for internal and external gripping. Parallel standard grippers are used for handling a wide range of small parts in a clean environment. To absorb high forces, Festo offers sturdy gripper systems with a resilient T-slot guide for the gripper jaws. Sealed grippers are suitable for handling tasks in very dirty and demanding environments. The precise parallel gripper has gripper jaws with an impressive backlash-free roller bearing./n/nIn our Core Range you will find the three parallel grippers DHPC, DHPS, HGPL and HGPT in a wide range of sizes. DHPC and DHPS are characterised by their high gripping force, compact design as well as maximum repeat accuracy, while HGPL is particularly suitable for use with large workpieces and long strokes. The parallel gripper HGPT is sturdy, powerful and, like the HGPL, has a T-slot guide. In addition to our Core Range, you will find additional parallel grippers for a wide variety of requirements at Festo. These include products that are ideal for gripping larger workpieces, self-centring grippers and grippers for very harsh environments as well as micro grippers with an extremely small and convenient design./n/nThree-point grippers/nWith three-point grippers, a workpiece can be picked up centrally. At Festo you will find three-point grippers in various designs. Standard three-point grippers are suitable for the universal handling of small parts in a clean environment. To absorb high forces, the three-finger gripper systems with resilient T-slot guide are used for internal and external gripping. Sealed three-point grippers are suitable for handling tasks in very dirty and demanding environments./n/nOur three-point gripper DHDS ensures maximum repeat accuracy and has a high gripping force while also having a compact design. The Festo three-point gripper HGDD enables precise gripping with centric movements despite high torque loads and is particularly suitable for use in very harsh environments. The gripper jaw guide of the three-point gripper HGDT is protected from dust by sealing air, which makes this gripper particularly durable. It is also available as a high-force version and enables the gripper jaws to be moved synchronously./n/nAngle grippers/nAngle grippers from Festo are available as small parts grippers and micro grippers. Each jaw of the angle gripper opens up to 20Â°. The opening angle can eliminate the need to approach an object from the side. The specific opening angle can reduce cycle times and interfering contours can be avoided./n/nOur latest model, the angle gripper DHWC, can be used either as a double-acting or single-acting gripper. In addition, the gripper jaws are supported laterally and thus the gripper has a high torque load. The angle gripper DHWS with improved gripper jaw guide has an internal fixed restrictor, which makes an external restrictor superfluous in most of the applications. The Festo angle gripper HGWM is characterised by its small and convenient design. The externally adaptable gripping fingers make it very versatile./n/nRadial grippers/nRadial grippers from Festo are available in two variants. The standard radial gripper is available as a small parts gripper for clean ambient conditions. A robust version', 'sub_categories': [{'name': 'Parallel grippers', 'pimId': 'pim487', 'description': 'Size 6, 8, 10, 12, 14, 16, 20, 25, 32, 35, 40, 50, 63 mm. Stroke length 0 ... 80\xa0mm. Force 8 ... 770\xa0N per gripper jaw. Grippers with gripper fingers that move a linear direction, independent of the number of gripper fingers (two- and three-point grippers).', 'sub_categories': []}, {'name': 'Three finger grippers', 'pimId': 'pim488', 'description': 'Size 16, 25, 32, 35, 40, 50, 63 mm. Stroke length 2.5 ... 10\xa0mm per gripper jaw. Force 30 ... 864\xa0N per gripper jaw. Grippers with gripper fingers that move a linear direction, independent of the number of gripper fingers (two- and three-point grippers).', 'sub_categories': []}, {'name': 'Angular grippers', 'pimId': 'pim489', 'description': 'Size 8, 10, 12, 16, 20, 25, 32, 40\xa0mm. Opening angle 14 ... 18.5°, 30°, 40°, 180°. Gripping torque 11 ... 965\xa0Ncm. Grippers whose gripper fingers execute a swivelling movement, independent of the angle.', 'sub_categories': []}, {'name': 'Radial grippers', 'pimId': 'pim490', 'description': 'Size 10, 12, 16, 20, 25, 32, 40 mm. Opening angle 180°. Gripping torque 13 ... 600 Ncm.', 'sub_categories': []}, {'name': 'Swivel/gripper units', 'pimId': 'pim491', 'description': 'Size: 12, 16, 20. Stroke length 2.5 ... 7 mm per gripper jaw. Force 26 ... 65 N per gripper jaw. Swivel angle 220°. Combination of semi-rotary drive and gripper.', 'sub_categories': []}, {'name': 'Bellows grippers', 'pimId': 'pim492', 'description': 'Pneumatic grippers for sensitive and secure internal gripping.', 'sub_categories': []}, {'name': 'Accessories for grippers', 'pimId': 'pim417', 'description': 'Adapter kits and installation components for handling units which allow handling systems to be constructed.', 'sub_categories': []}]}"
        



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
        llm=openai.LLM(model="gpt-4o",temperature=0.3),
        stt=deepgram.STT(model="nova-3", language="en"),
        # stt=groq.STT(
        #     model="whisper-large-v3-turbo",
        #     language="en",
        # ),

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
    await session.say("Hi there! I am the Festo IOT hardware shop assistant. How can I help?",allow_interruptions=True) # initial message


    # join the room when agent is ready
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
