import logging
import os
from dataclasses import dataclass, field
from typing import Optional
import sys

from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession, RunContext
from livekit.plugins import cartesia, deepgram, openai, silero
from livekit.plugins import noise_cancellation

from utils import load_prompt
from database import CustomerDatabase

# Add the parent directory to the path to import from scripts
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import Festo-specific functions
try:
    from scripts.v1.find_categories import find_main_categories, find_by_pimid, get_url_of_categoriy, get_brands_of_categories, get_brands_of_categories_with_query
    from scripts.v1.filter_function import get_next_filter, get_formatted_filter, make_filter_question, get_answred_code_for_filter, get_selected_value_query, generate_url
    from scripts.v1.engineering_tool_functions import get_available_engineering_tool, get_next_sizing_tool_question, validate_sizing_tool_answer, get_next_sizing_tool_filter, generate_product_urls
except ImportError as e:
    print(f"Warning: Could not import Festo scripts: {e}")
    print("Please ensure the scripts are available in the correct path")

logger = logging.getLogger("personal-shopper")
logger.setLevel(logging.INFO)

load_dotenv()

# Initialize the customer database
db = CustomerDatabase()

@dataclass
class UserData:
    """Class to store user data and agents during a call."""
    personas: dict[str, Agent] = field(default_factory=dict)
    prev_agent: Optional[Agent] = None
    ctx: Optional[JobContext] = None

    # Customer information
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    customer_id: Optional[str] = None
    current_order: Optional[dict] = None

    # Festo-specific conversation state
    festo_conversation_state: dict = field(default_factory=lambda: {
        "current_answered_query": None,
        "all_answered_query": [],
        "current_filter_data": None,
        "skip_filter_questions": [],
        "current_engineering_tool": {
            "answered_questions": {},
            "skip_filter_questions": {},
            "current_filter_data": {}
        }
    })

    def is_identified(self) -> bool:
        """Check if the customer is identified."""
        return self.first_name is not None and self.last_name is not None

    def reset(self) -> None:
        """Reset customer information."""
        self.first_name = None
        self.last_name = None
        self.customer_id = None
        self.current_order = None

    def reset_festo_state(self) -> None:
        """Reset the Festo filtering state to start a new filtering process."""
        self.festo_conversation_state = {
            "current_answered_query": None,
            "all_answered_query": [],
            "current_filter_data": None,
            "skip_filter_questions": [],
            "current_engineering_tool": {
                "answered_questions": {},
                "skip_filter_questions": {},
                "current_filter_data": {}
            }
        }

    def summarize(self) -> str:
        """Return a summary of the user data."""
        if self.is_identified():
            return f"Customer: {self.first_name} {self.last_name} (ID: {self.customer_id})"
        return "Customer not yet identified."

RunContext_T = RunContext[UserData]

class BaseAgent(Agent):
    async def on_enter(self) -> None:
        agent_name = self.__class__.__name__
        logger.info(f"Entering {agent_name}")

        userdata: UserData = self.session.userdata
        if userdata.ctx and userdata.ctx.room:
            await userdata.ctx.room.local_participant.set_attributes({"agent": agent_name})

        # Create a personalized prompt based on customer identification
        custom_instructions = self.instructions
        if userdata.is_identified():
            custom_instructions += f"\n\nYou are speaking with {userdata.first_name} {userdata.last_name}."

        chat_ctx = self.chat_ctx.copy()

        # Copy context from previous agent if it exists
        if userdata.prev_agent:
            items_copy = self._truncate_chat_ctx(
                userdata.prev_agent.chat_ctx.items, keep_function_call=True
            )
            existing_ids = {item.id for item in chat_ctx.items}
            items_copy = [item for item in items_copy if item.id not in existing_ids]
            chat_ctx.items.extend(items_copy)

        chat_ctx.add_message(
            role="system",
            content=f"You are the {agent_name}. {userdata.summarize()}"
        )
        await self.update_chat_ctx(chat_ctx)
        self.session.generate_reply()

    def _truncate_chat_ctx(
        self,
        items: list,
        keep_last_n_messages: int = 6,
        keep_system_message: bool = False,
        keep_function_call: bool = False,
    ) -> list:
        """Truncate the chat context to keep the last n messages."""
        def _valid_item(item) -> bool:
            if not keep_system_message and item.type == "message" and item.role == "system":
                return False
            if not keep_function_call and item.type in ["function_call", "function_call_output"]:
                return False
            return True

        new_items = []
        for item in reversed(items):
            if _valid_item(item):
                new_items.append(item)
            if len(new_items) >= keep_last_n_messages:
                break
        new_items = new_items[::-1]

        while new_items and new_items[0].type in ["function_call", "function_call_output"]:
            new_items.pop(0)

        return new_items

    async def _transfer_to_agent(self, name: str, context: RunContext_T) -> Agent:
        """Transfer to another agent while preserving context."""
        userdata = context.userdata
        current_agent = context.session.current_agent
        next_agent = userdata.personas[name]
        userdata.prev_agent = current_agent

        return next_agent


class TriageAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            instructions=load_prompt('triage_prompt.yaml'),
            stt=deepgram.STT(),
            llm=openai.LLM(model="gpt-4o-mini"),
            # tts=cartesia.TTS(),
            tts=openai.TTS(),
            vad=silero.VAD.load()
        )

    @function_tool
    async def identify_customer(self, first_name: str, last_name: str):
        """
        Identify a customer by their first and last name.

        Args:
            first_name: The customer's first name
            last_name: The customer's last name
        """
        userdata: UserData = self.session.userdata
        userdata.first_name = first_name
        userdata.last_name = last_name
        userdata.customer_id = db.get_or_create_customer(first_name, last_name)

        return f"Thank you, {first_name}. I've found your account."

    @function_tool
    async def transfer_to_festo(self, context: RunContext_T) -> Agent:
        """Transfer to Festo technical support for product specifications and engineering questions."""
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = f"Thank you, {userdata.first_name}. I'll transfer you to our Festo technical support specialist who can help with product specifications and engineering questions."
        else:
            message = "I'll transfer you to our Festo technical support specialist who can help with product specifications and engineering questions."
        
        await self.session.say(message)
        return await self._transfer_to_agent("festo", context)

    @function_tool
    async def transfer_to_sales(self, context: RunContext_T) -> Agent:
        # Create a personalized message if customer is identified
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = f"Thank you, {userdata.first_name}. I'll transfer you to our Sales team who can help you find the perfect product."
        else:
            message = "I'll transfer you to our Sales team who can help you find the perfect product."

        await self.session.say(message)
        return await self._transfer_to_agent("sales", context)

    @function_tool
    async def transfer_to_returns(self, context: RunContext_T) -> Agent:
        # Create a personalized message if customer is identified
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = f"Thank you, {userdata.first_name}. I'll transfer you to our Returns department who can assist with your return or exchange."
        else:
            message = "I'll transfer you to our Returns department who can assist with your return or exchange."

        await self.session.say(message)
        return await self._transfer_to_agent("returns", context)


class SalesAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            instructions=load_prompt('sales_prompt.yaml'),
            stt=deepgram.STT(),
            llm=openai.LLM(model="gpt-4o-mini"),
            # tts=cartesia.TTS(),
            tts=openai.TTS(),
            vad=silero.VAD.load()
        )

    @function_tool
    async def identify_customer(self, first_name: str, last_name: str):
        """
        Identify a customer by their first and last name.

        Args:
            first_name: The customer's first name
            last_name: The customer's last name
        """
        userdata: UserData = self.session.userdata
        userdata.first_name = first_name
        userdata.last_name = last_name
        userdata.customer_id = db.get_or_create_customer(first_name, last_name)

        return f"Thank you, {first_name}. I've found your account."

    @function_tool
    async def start_order(self):
        """Start a new order for the customer."""
        userdata: UserData = self.session.userdata
        if not userdata.is_identified():
            return "Please identify the customer first using the identify_customer function."

        userdata.current_order = {
            "items": []
        }

        return "I've started a new order for you. What would you like to purchase?"

    @function_tool
    async def add_item_to_order(self, item_name: str, quantity: int, price: float):
        """
        Add an item to the current order.

        Args:
            item_name: The name of the item
            quantity: The quantity to purchase
            price: The price per item
        """
        userdata: UserData = self.session.userdata
        if not userdata.is_identified():
            return "Please identify the customer first using the identify_customer function."

        if not userdata.current_order:
            userdata.current_order = {"items": []}

        item = {
            "name": item_name,
            "quantity": quantity,
            "price": price
        }

        userdata.current_order["items"].append(item)

        return f"Added {quantity}x {item_name} to your order."

    @function_tool
    async def complete_order(self):
        """Complete the current order and save it to the database."""
        userdata: UserData = self.session.userdata
        if not userdata.is_identified():
            return "Please identify the customer first using the identify_customer function."

        if not userdata.current_order or not userdata.current_order.get("items"):
            return "There are no items in the current order."

        # Calculate order total
        total = sum(item["price"] * item["quantity"] for item in userdata.current_order["items"])
        userdata.current_order["total"] = total

        # Save order to database
        order_id = db.add_order(userdata.customer_id, userdata.current_order)

        # Create a summary of the order
        summary = f"Order #{order_id} has been completed. Total: ${total:.2f}\n"
        summary += "Items:\n"
        for item in userdata.current_order["items"]:
            summary += f"- {item['quantity']}x {item['name']} (${item['price']} each)\n"

        # Reset the current order
        userdata.current_order = None

        return summary

    @function_tool
    async def transfer_to_festo(self, context: RunContext_T) -> Agent:
        """Transfer to Festo technical support for detailed product specifications."""
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = f"Thank you, {userdata.first_name}. I'll transfer you to our Festo technical support for detailed product specifications."
        else:
            message = "I'll transfer you to our Festo technical support for detailed product specifications."

        await self.session.say(message)
        return await self._transfer_to_agent("festo", context)

    @function_tool
    async def transfer_to_triage(self, context: RunContext_T) -> Agent:
        # Create a personalized message if customer is identified
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = f"Thank you, {userdata.first_name}. I'll transfer you back to our Triage agent who can better direct your inquiry."
        else:
            message = "I'll transfer you back to our Triage agent who can better direct your inquiry."

        await self.session.say(message)
        return await self._transfer_to_agent("triage", context)

    @function_tool
    async def transfer_to_returns(self, context: RunContext_T) -> Agent:
        # Create a personalized message if customer is identified
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = f"Thank you, {userdata.first_name}. I'll transfer you to our Returns department for assistance with your return request."
        else:
            message = "I'll transfer you to our Returns department for assistance with your return request."

        await self.session.say(message)
        return await self._transfer_to_agent("returns", context)


class ReturnsAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            instructions=load_prompt('returns_prompt.yaml'),
            stt=deepgram.STT(),
            llm=openai.LLM(model="gpt-4o-mini"),
            # tts=cartesia.TTS(),
            tts=openai.TTS(),
            vad=silero.VAD.load()
        )

    @function_tool
    async def identify_customer(self, first_name: str, last_name: str):
        """
        Identify a customer by their first and last name.

        Args:
            first_name: The customer's first name
            last_name: The customer's last name
        """
        userdata: UserData = self.session.userdata
        userdata.first_name = first_name
        userdata.last_name = last_name
        userdata.customer_id = db.get_or_create_customer(first_name, last_name)

        return f"Thank you, {first_name}. I've found your account."

    @function_tool
    async def get_order_history(self):
        """Get the order history for the current customer."""
        userdata: UserData = self.session.userdata
        if not userdata.is_identified():
            return "Please identify the customer first using the identify_customer function."

        order_history = db.get_customer_order_history(userdata.first_name, userdata.last_name)
        return order_history

    @function_tool
    async def process_return(self, order_id: int, item_name: str, reason: str):
        """
        Process a return for an item from a specific order.

        Args:
            order_id: The ID of the order containing the item to return
            item_name: The name of the item to return
            reason: The reason for the return
        """
        userdata: UserData = self.session.userdata
        if not userdata.is_identified():
            return "Please identify the customer first using the identify_customer function."

        # In a real system, we would update the order in the database
        # For this example, we'll just return a confirmation message
        return f"Return processed for {item_name} from Order #{order_id}. Reason: {reason}. A refund will be issued within 3-5 business days."

    @function_tool
    async def transfer_to_festo(self, context: RunContext_T) -> Agent:
        """Transfer to Festo technical support for product-related questions."""
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = f"Thank you, {userdata.first_name}. I'll transfer you to our Festo technical support for product-related questions."
        else:
            message = "I'll transfer you to our Festo technical support for product-related questions."

        await self.session.say(message)
        return await self._transfer_to_agent("festo", context)

    @function_tool
    async def transfer_to_triage(self, context: RunContext_T) -> Agent:
        # Create a personalized message if customer is identified
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = f"Thank you, {userdata.first_name}. I'll transfer you back to our Triage agent who can better direct your inquiry."
        else:
            message = "I'll transfer you back to our Triage agent who can better direct your inquiry."

        await self.session.say(message)
        return await self._transfer_to_agent("triage", context)

    @function_tool
    async def transfer_to_sales(self, context: RunContext_T) -> Agent:
        # Create a personalized message if customer is identified
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = f"Thank you, {userdata.first_name}. I'll transfer you to our Sales team who can help you find new products."
        else:
            message = "I'll transfer you to our Sales team who can help you find new products."

        await self.session.say(message)
        return await self._transfer_to_agent("sales", context)


class FestoAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            instructions=load_prompt('festo_prompt.yaml'),
            stt=deepgram.STT(),
            llm=openai.LLM(model="gpt-4o", temperature=0.3),
            tts=openai.TTS(),
            vad=silero.VAD.load()
        )

    @function_tool
    async def get_main_categories(self):
        """Use this tool to get all main categories from the IoT hardware shop."""
        logger.info("Getting all main categories from the IoT hardware shop.")
        try:
            return find_main_categories()
        except Exception as e:
            logger.error(f"Error getting main categories: {e}")
            return "Error retrieving main categories. Please try again."

    @function_tool
    async def check_sub_category_available(self, pimId: str):
        """Check if any sub categories are available for a given pimId."""
        try:
            categories = find_by_pimid(pimId)
            if len(categories) > 0:
                return categories
            else:
                return "No sub categories available for this pimId"
        except Exception as e:
            logger.error(f"Error checking subcategories for pimId {pimId}: {e}")
            return "Error checking subcategories. Please try again."

    @function_tool
    async def reset_filter_state(self):
        """Reset the filtering state to start a new filtering process."""
        userdata: UserData = self.session.userdata
        userdata.reset_festo_state()
        return "Filter state has been reset. Ready to start a new filtering process."

    @function_tool
    async def get_next_filter_question(self, endSubCategoryPimId: str):
        """Get the next filter question for a given end-level subcategory pimId."""
        userdata: UserData = self.session.userdata
        conversation_state = userdata.festo_conversation_state

        try:
            # Check engineering tool exist for end sub category
            selected_engineering_tool = get_available_engineering_tool(endSubCategoryPimId)
            if selected_engineering_tool != {} and selected_engineering_tool.get("sizing_configurations"):
                sizing_configurations = selected_engineering_tool["sizing_configurations"]
                current_engineering_tool = conversation_state.get("current_engineering_tool", {})
                if current_engineering_tool != {}:
                    answered_questions = current_engineering_tool.get("answered_questions", {})
                    skip_filter_questions = current_engineering_tool.get("skip_filter_questions", {})
                else:
                    answered_questions = {}
                    skip_filter_questions = {}
                
                logger.info(f"Current answered questions: {answered_questions}")
                next_filter = get_next_sizing_tool_filter(sizing_configurations, answered_questions, skip_filter_questions, endSubCategoryPimId)
                conversation_state["current_engineering_tool"] = {
                        "answered_questions": answered_questions,
                        "skip_filter_questions": skip_filter_questions,
                        "current_filter_data": next_filter
                    }
                if next_filter:
                    question = get_next_sizing_tool_question(next_filter, answered_questions, endSubCategoryPimId)
                    if question:
                        return question
                    else:
                        return "Error generating question for the next filter. Please try again."
                else:
                    return "All filter questions are answered."
            else:
                current_answered_query = conversation_state.get("current_answered_query", None)
                if current_answered_query is None:
                    conversation_state["current_answered_query"] = "~:sortByCoreRangeAndNewProduct"
                all_answered_query = conversation_state.get("all_answered_query", [])
                
                skip_filter_questions = conversation_state.get("skip_filter_questions", [])
                
                next_filter = get_next_filter(endSubCategoryPimId, current_answered_query, skip_filter_questions)
                
                if next_filter:
                    formatted_filter = get_formatted_filter(next_filter)
                    question = make_filter_question("session_room", endSubCategoryPimId, formatted_filter)
                    conversation_state["current_filter_data"] = formatted_filter
                    
                    if question:
                        return question
                    else:
                        return "Error generating question for the next filter. Please try again."
                else:
                    return "All filter questions are answered"
        except Exception as e:
            logger.error(f"Error getting next filter question: {e}")
            return "Error getting next filter question. Please try again."

    @function_tool
    async def validate_filter_answer(self, pimId: str, question: str, userAnswer: str):
        """Validate and process a user's answer to a filter question."""
        userdata: UserData = self.session.userdata
        conversation_state = userdata.festo_conversation_state

        try:
            # Check engineering tool exist for end sub category
            selected_engineering_tool = get_available_engineering_tool(pimId)
            if selected_engineering_tool != {} and selected_engineering_tool.get("sizing_configurations"):
                sizing_configurations = selected_engineering_tool["sizing_configurations"]
                current_engineering_tool = conversation_state.get("current_engineering_tool", {})
                if current_engineering_tool != {} and current_engineering_tool.get("current_filter_data", None):
                    formatted_filter = current_engineering_tool.get("current_filter_data", {})
                    answered_questions = current_engineering_tool.get("answered_questions", {})
                    skip_filter_questions = current_engineering_tool.get("skip_filter_questions", {})

                    # Validate the answer
                    answer_code = validate_sizing_tool_answer("session_room", pimId, question, userAnswer, formatted_filter, answered_questions)
                    
                    if answer_code:
                        answered_questions[formatted_filter["payload_attribute"]] = answer_code
                        conversation_state["current_engineering_tool"] = {
                            "answered_questions": answered_questions,
                            "skip_filter_questions": skip_filter_questions,
                            "current_filter_data": formatted_filter
                        }
                        return "Answer is valid and query is updated."
                    else:
                        return f"Answer is not valid. Please provide a valid answer from {question}"
                else:
                    return "Error: No filter data found. Please get a filter question first."
            else:
                current_answered_query = conversation_state.get("current_answered_query", None)
                if current_answered_query is None:
                    conversation_state["current_answered_query"] = "~:sortByCoreRangeAndNewProduct"
                all_answered_query = conversation_state.get("all_answered_query", [])
                
                formatted_filter = conversation_state.get("current_filter_data", None)

                if not formatted_filter:
                    return "Error: No filter data found. Please get a filter question first."
                
                # Validate the answer
                answer_code = get_answred_code_for_filter("session_room", formatted_filter, question, userAnswer)
                
                if answer_code:
                    selected_value_query = get_selected_value_query(formatted_filter, answer_code)
                    
                    if selected_value_query:
                        # Update the current query
                        current_answered_query = selected_value_query
                        all_answered_query.append(selected_value_query)
                        conversation_state["current_answered_query"] = current_answered_query
                        conversation_state["all_answered_query"] = all_answered_query
                        
                        return "Answer is valid and query is updated."
                    else:
                        return "Answer is valid but query could not be updated. Please try again."
                else:
                    return f"Answer is not valid. Please provide a valid answer from {question}"
        except Exception as e:
            logger.error(f"Error validating filter answer: {e}")
            return "Error validating answer. Please try again."

    @function_tool
    async def generate_final_url(self, endSubCategoryPimId: str):
        """Generate the final filtered product URL after all filter questions are answered."""
        userdata: UserData = self.session.userdata
        conversation_state = userdata.festo_conversation_state

        try:
            # Check if the end subcategory has an engineering tool
            selected_engineering_tool = get_available_engineering_tool(endSubCategoryPimId)
            if selected_engineering_tool != {} and selected_engineering_tool.get("sizing_configurations"):
                sizing_configurations = selected_engineering_tool["sizing_configurations"]
                current_engineering_tool = conversation_state.get("current_engineering_tool", {})
                if current_engineering_tool != {}:
                    answered_questions = current_engineering_tool.get("answered_questions", {})
                    url_details = generate_product_urls(endSubCategoryPimId, selected_engineering_tool, answered_questions)

                    for url_detail in url_details:
                        url = url_detail["url"]
                        return f'    {url}   '
                    return "No products found for the current filter query. Please try different filters or check the query."
            else:
                current_answered_query = conversation_state.get("current_answered_query", None)
                if current_answered_query is None:
                    conversation_state["current_answered_query"] = "~:sortByCoreRangeAndNewProduct"
                
                final_url = generate_url(endSubCategoryPimId, current_answered_query)
                
                if final_url:
                    return f'    {final_url}   '
                else:
                    return "No products found for the current filter query. Please try different filters or check the query."
        except Exception as e:
            logger.error(f"Error generating final URL: {e}")
            return "Error generating product URL. Please try again."

    @function_tool
    async def transfer_to_triage(self, context: RunContext_T) -> Agent:
        """Transfer to triage agent for general inquiries."""
        await self.session.say("I'll transfer you to our Triage agent who can help with general inquiries.")
        return await self._transfer_to_agent("triage", context)

    @function_tool
    async def transfer_to_sales(self, context: RunContext_T) -> Agent:
        """Transfer to sales agent for purchasing assistance."""
        await self.session.say("I'll transfer you to our Sales team for purchasing assistance.")
        return await self._transfer_to_agent("sales", context)

    @function_tool
    async def transfer_to_returns(self, context: RunContext_T) -> Agent:
        """Transfer to returns agent for return/exchange requests."""
        await self.session.say("I'll transfer you to our Returns department for return assistance.")
        return await self._transfer_to_agent("returns", context)


async def entrypoint(ctx: JobContext):
    # Initialize user data with context
    userdata = UserData(ctx=ctx)

    # Create agent instances
    triage_agent = TriageAgent()
    sales_agent = SalesAgent()
    returns_agent = ReturnsAgent()
    festo_agent = FestoAgent()

    # Register all agents in the userdata
    userdata.personas.update({
        "triage": triage_agent,
        "sales": sales_agent,
        "returns": returns_agent,
        "festo": festo_agent
    })

    # Create session with userdata
    session = AgentSession[UserData](userdata=userdata)

    await session.start(
        agent=festo_agent,  # Start with the Festo agent
        room=ctx.room
    )

    # Initial greeting message
    await session.say("Hi, I am Yobo, your pre-sales application engineering assistant in Festo. How can I help you today?", allow_interruptions=True)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
