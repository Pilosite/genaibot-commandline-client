import os  
import asyncio  
import logging  
import threading  
from datetime import datetime, timezone  
from io import StringIO  
import sys
import aiohttp  
import uvicorn  
from fastapi import FastAPI, Request  
from dotenv import load_dotenv  
from prompt_toolkit import PromptSession  
from prompt_toolkit.patch_stdout import patch_stdout  
from prompt_toolkit.completion import Completer, Completion  
  
import typer  
from rich.console import Console  
from rich.theme import Theme  
  
# Instantiate the Typer application  
app = typer.Typer()  
  
# Load environment variables from .env  
load_dotenv()  
  
# FastAPI application instance  
fastapi_app = FastAPI()  
  
# Retrieve environment variable values  
CLIENT_ID = os.getenv("CLIENT_ID", "default_client")  
LLM_NOTIFICATION_ENDPOINT = os.getenv("LLM_NOTIFICATION_ENDPOINT", "http://localhost:8000/api/receive_message")  
  
# Logging configuration  
logger = logging.getLogger("app_logger")  
logger.setLevel(logging.INFO)  
log_capture_string = StringIO()  
stream_handler = logging.StreamHandler(log_capture_string)  
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')  
stream_handler.setFormatter(formatter)  
logger.addHandler(stream_handler)  
logger.propagate = False  
  
# Initialize conversation history and flags  
conversation_history = []  # Stores messages and reactions  
show_internal_messages = False  # Toggle to display internal messages  
waiting_for_response = False  
  
# Generate a unique thread_id  
def generate_thread_id():  
    current_timestamp = datetime.now(timezone.utc).timestamp()  
    thread_id = "{:.4f}".format(current_timestamp)  
    return thread_id  
  
thread_id = generate_thread_id()  
  
# Define a custom theme for better readability  
custom_theme = Theme({  
    "assistant": "white",  
    "assistant_internal": "bright_black",  
    "reaction": "yellow",  
    "command": "cyan",  
    "error": "bold red",  
    "system": "bold magenta"  
})  
  
# Rich console for formatted output  
console = Console(theme=custom_theme)  
  
# Mapping of reaction names to emojis  
REACTION_EMOJI_MAP = {  
    "processing": "⚙️",  
    "done": "✅",  
    "acknowledge": "👀",  
    "generating": "🤔",  
    "writing": "✏️",  
    "error": "❌",  
    "wait": "⌚",  
}  
  
# Event to signal that the assistant has finished processing  
done_reaction_received = asyncio.Event()  
  
# Global variables for the main event loop and last user message index  
main_loop = None  
last_user_message_index = -1  
  
def print_with_timestamp(role: str, message: str):  
    """Prints a message with a timestamp."""  
    current_time = datetime.now().strftime("%H:%M:%S")  
  
    # Mapping of roles to styles  
    style_map = {  
        "Assistant": "assistant",  
        "ASSISTANT (internal)": "assistant_internal",  
        "Reaction": "reaction",  
        "Command": "command",  
        "Error": "error",  
        "System": "system"  
    }  
  
    style = style_map.get(role, None)  
  
    console.print(f"[{current_time}] [{role}] {message}", style=style)  
  
# Function to send user input to the tested LLM (LLM1)  
async def call_tested_llm(user_input: str):  
    global thread_id  
    headers = {"Content-Type": "application/json"}  
  
    # Generate a unique timestamp for the message  
    current_timestamp = datetime.now(timezone.utc).timestamp()  
    timestamp_with_millis = "{:.4f}".format(current_timestamp)  
  
    payload = {  
        "channel_id": 1,  
        "event_type": "MESSAGE",  
        "response_id": 1,  
        "text": user_input,  
        "thread_id": thread_id,  # Use the correct thread_id variable here  
        "timestamp": timestamp_with_millis,  
        "user_email": f"{CLIENT_ID}@example.com",  
        "user_id": 1,  
        "user_name": CLIENT_ID,  
        "reaction_name": None,  
        "files_content": [],  
        "images": [],  
        "is_mention": True,  
        "origin_plugin_name": CLIENT_ID,  
        "message_type": "TEXT",  
        "is_internal": False,  
        "raw_data": {"text": user_input},  
        "username": CLIENT_ID,  
        "event_label": "message",  
        "api_app_id": "genaibot",  
        "app_id": "genaibot"  
    }  
  
    async with aiohttp.ClientSession() as session:  
        try:  
            async with session.post(LLM_NOTIFICATION_ENDPOINT, headers=headers, json=payload) as response:  
                if response.status in [200, 202]:  
                    logger.info("Message accepted by LLM [ASSISTANT] successfully.")  
                else:  
                    logger.error(f"Failed to send message to LLM [ASSISTANT]: {response.status}")  
        except Exception as e:  
            logger.error(f"Error during LLM [ASSISTANT] interaction: {str(e)}.")  
  
# FastAPI endpoint to receive messages from LLM1  
@fastapi_app.post("/api/receive_message")  
async def receive_message(request: Request):  
    global conversation_history, waiting_for_response, show_internal_messages, main_loop  
    try:  
        message = await request.json()  
        event_type = message.get("event_type", "")  
        text = message.get("text", "")  
        reaction_name = message.get("reaction_name", "")  
        is_internal = message.get("is_internal", False)  
  
        if event_type == "MESSAGE":  
            # Different display for internal messages  
            if is_internal:  
                conversation_history.append({  
                    "role": "assistant_internal",  
                    "content": text,  
                    "reactions": [],  
                })  
                if show_internal_messages:  
                    print_with_timestamp("ASSISTANT (internal)", text)  
            else:  
                conversation_history.append({  
                    "role": "assistant",  
                    "content": text,  
                    "reactions": [],  
                })  
                print_with_timestamp("Assistant", text)  
        elif event_type == "REACTION_ADD":  
            emoji = REACTION_EMOJI_MAP.get(reaction_name.lower(), f":{reaction_name}:")  
            # Find the last user message  
            last_user_message = next((msg for msg in reversed(conversation_history) if msg["role"] == "user"), None)  
            if last_user_message:  
                if emoji not in last_user_message["reactions"]:  
                    last_user_message["reactions"].append(emoji)  
                    print_with_timestamp("Reaction", f"'{emoji}' added to your last message.")  
                if reaction_name.lower() == 'done':  
                    waiting_for_response = False  
                    if main_loop is not None:  
                        main_loop.call_soon_threadsafe(done_reaction_received.set)  
        return {"status": "OK"}  
  
    except Exception as e:  
        logger.error(f"Error receiving message from LLM1: {str(e)}")  
        return {"status": "ERROR", "message": str(e)}  
  
# Function to start the uvicorn server in a separate thread  
def start_uvicorn():  
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8000, log_level="warning")  
    server = uvicorn.Server(config)  
    server.run()  
  
# Function to reset the conversation history and refresh the console  
def reset_conversation():  
    global conversation_history, thread_id, last_user_message_index  
    conversation_history.clear()  
    console.clear()  
    print_with_timestamp("System", "Conversation history has been reset.")  
    console.print("Available Commands:")  
    console.print("  /toggle_internal - Toggle internal messages on/off.")  
    console.print("  /reset           - Clear the conversation history.")  
    console.print("  /show_last_mind  - Display internal messages since your last message.")  
    console.print("  /exit or /quit   - Exit the application.\n")  
  
    # Generate a new unique thread_id  
    thread_id = generate_thread_id()  
    print_with_timestamp("System", f"New thread ID generated: {thread_id}")  
  
    # Reset the last user message index  
    last_user_message_index = -1  
  
# Function to display internal messages since the last user message  
def show_last_internal_messages():  
    global conversation_history, last_user_message_index  
    # Collect internal messages since the last user message  
    internal_messages = []  
    for msg in conversation_history[last_user_message_index+1:]:  
        if msg["role"] == "assistant_internal":  
            internal_messages.append(msg["content"])  
    if internal_messages:  
        print_with_timestamp("System", "Internal messages since your last message:")  
        for idx, msg in enumerate(internal_messages, 1):  
            console.print(f"{idx}. {msg}", style="assistant_internal")  
    else:  
        print_with_timestamp("System", "No internal messages since your last message.")  
  
# Define a list of available commands for autocompletion  
COMMANDS = [  
    "/toggle_internal",  
    "/reset",  
    "/show_last_mind",  
    "/exit",  
    "/quit"  
]  
  
# Implement a custom completer  
class CommandCompleter(Completer):  
    def get_completions(self, document, complete_event):  
        # Tokenize the input so far  
        text = document.text_before_cursor  
        if text.startswith('/'):  
            for cmd in COMMANDS:  
                if cmd.startswith(text):  
                    yield Completion(cmd, start_position=-len(text))  
  
# Main function to run the interactive session  
async def main(show_internal_messages_arg: bool, prompt_name: str):  
    global waiting_for_response, show_internal_messages, main_loop, thread_id, last_user_message_index  
  
    # Set the flag for internal messages  
    show_internal_messages = show_internal_messages_arg  
  
    # Start the FastAPI server in a separate thread  
    server_thread = threading.Thread(target=start_uvicorn, daemon=True)  
    server_thread.start()  
    logger.info("FastAPI server started.")  
  
    # Get the main event loop  
    main_loop = asyncio.get_running_loop()  
  
    # Create the PromptSession with the CommandCompleter  
    session = PromptSession(completer=CommandCompleter())  
  
    # Display a welcome message  
    print_with_timestamp("System", "Welcome to the Assistant CLI!")  
    console.print("Available Commands:")  
    console.print("  /toggle_internal - Toggle internal messages on/off.")  
    console.print("  /reset           - Clear the conversation history.")  
    console.print("  /show_last_mind  - Display internal messages since your last message.")  
    console.print("  /exit or /quit   - Exit the application.\n")  
  
    # Display the current thread_id  
    print_with_timestamp("System", f"Current thread ID: {thread_id}")  
  
    # Load the system prompt if provided  
    if prompt_name:  
        system_prompt = load_system_prompt(prompt_name)  
        if not system_prompt:  
            print_with_timestamp("System", f"Prompt '{prompt_name}' not found.")  
        else:  
            conversation_history.append({  
                "role": "system",  
                "content": system_prompt,  
                "reactions": [],  
            })  
            print_with_timestamp("System", f"System Prompt: {system_prompt}")  
  
    # Interaction loop with the user  
    try:  
        while True:  
            with patch_stdout():  
                user_input = await session.prompt_async("You: ")  
                user_input = user_input.strip()
  
            # Check for slash commands  
            if user_input.startswith("/"):  
                if user_input == "/toggle_internal":  
                    show_internal_messages = not show_internal_messages  
                    status = "ON" if show_internal_messages else "OFF"  
                    print_with_timestamp("Command", f"Internal messages display toggled {status}.")  
                    continue  
                elif user_input == "/reset":  
                    reset_conversation()  
                    continue  
                elif user_input == "/show_last_mind":  
                    show_last_internal_messages()  
                    continue  
                elif user_input in ('/exit', '/quit'):  
                    print_with_timestamp("System", "Exiting.")  
                    break  
                else:  
                    print_with_timestamp("Error", "Unknown command.")  
                    continue  
  
            # Add the user's message to the history  
            conversation_history.append({  
                "role": "user",  
                "content": user_input,  
                "reactions": [],  
            })  
  
            # Update the index of the last user message  
            last_user_message_index = len(conversation_history) - 1  
  
            # Send the user's message to LLM1  
            await call_tested_llm(user_input)  
  
            # Display the waiting message  
            waiting_for_response = True  
            print_with_timestamp("System", "Waiting for assistant to respond...")  
  
            # Reset the event before waiting  
            done_reaction_received.clear()  
  
            # Wait for the 'done' reaction to be received  
            await done_reaction_received.wait()  
  
            # After receiving 'done', resume control  
            waiting_for_response = False  
  
            # Print an empty line to separate interactions  
            console.print()  
  
    except Exception as e:  
        logger.error(f"Error in user input: {str(e)}")
        if 'pytest' in sys.modules:  
            raise  # Re-raise the exception during testing  
    finally:  
        # No need to stop the server; it stops with the daemon thread  
        pass  
  
# Function to load the system prompt  
def load_system_prompt(prompt_name: str):  
    try:  
        prompt_path = os.path.join("prompts", f"{prompt_name}.txt")  
        if os.path.exists(prompt_path):  
            with open(prompt_path, "r", encoding="utf-8") as file:  
                return file.read().strip()  
        else:  
            return None  
    except Exception as e:  
        logger.error(f"Error loading system prompt: {str(e)}")  
        return None  
  
# Define the CLI entry point with Typer  
@app.command()  
def run(  
    prompt_name: str = typer.Option(None, help="Name of the prompt to use."),  
    show_internal_messages: bool = typer.Option(False, help="Display internal messages."),  
):  
    """Run the interactive LLM script."""  
    try:  
        asyncio.run(main(show_internal_messages, prompt_name))  
    except (SystemExit, KeyboardInterrupt):  
        print_with_timestamp("System", "Application interrupted by user.")  
  
if __name__ == "__main__":  
    app()  
