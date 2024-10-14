import os
import sys
import json
import asyncio
import logging
import argparse
from datetime import datetime, timezone
from io import StringIO

import aiohttp
import uvicorn
from fastapi import FastAPI, Request
from dotenv import load_dotenv

from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout

from prompt_toolkit import PromptSession

# Load environment variables from .env
load_dotenv()

# FastAPI instance
app = FastAPI()

# Retrieve values from environment variables
CLIENT_ID = os.getenv("CLIENT_ID", "default_client")
BOT_ID = os.getenv("BOT_ID", "default_bot")
LLM_NOTIFICATION_ENDPOINT = os.getenv("LLM_NOTIFICATION_ENDPOINT", "http://localhost:8000/api/receive_message")
MAX_INTERACTIONS = int(os.getenv("MAX_INTERACTIONS", 10))  # Maximum number of interactions
TIMEOUT = int(os.getenv("TIMEOUT", 30))  # Timeout in seconds

# Set up logging
logger = logging.getLogger("app_logger")
logger.setLevel(logging.INFO)
log_capture_string = StringIO()

# Set up standard logging handler
stream_handler = logging.StreamHandler(log_capture_string)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)
logger.propagate = False  # Prevent logs from being printed to the console

conversation_history = []  # Stores messages and reactions
internal_messages = []     # Stores internal messages
test_completed_event = asyncio.Event()
show_internal_messages = False  # Will be set based on command-line argument

# Create an event to wait for LLM responses
llm_response_received = asyncio.Event()

# Flag to indicate waiting for LLM response
waiting_for_response = False

# Rich console for formatted output
console = Console()
live = Live(console=console, refresh_per_second=4)

# Map reaction names to emojis
REACTION_EMOJI_MAP = {
    "processing": "⚙️",
    "done": "✅",
    "acknowledge": "👀",
    "generating": "🤔",
    "writing": "✏️",
    "error": "❌",
    "wait": "⌚",
}

# Function to send user input to the tested LLM (LLM1)
async def call_tested_llm(user_input):
    headers = {"Content-Type": "application/json"}

    # Generate a unique timestamp for the message
    current_timestamp = datetime.now(timezone.utc).timestamp()
    timestamp_with_millis = "{:.4f}".format(current_timestamp)

    payload = {
        "channel_id": 1,
        "event_type": "MESSAGE",
        "response_id": 1,
        "text": user_input,
        "thread_id": 1,
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
                    test_completed_event.set()
                    return
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Connection error: {str(e)}. Exiting.")
            test_completed_event.set()
            return
        except Exception as e:
            logger.error(f"Error during LLM [ASSISTANT] interaction: {str(e)}. Exiting.")
            test_completed_event.set()
            return

# Receive message from LLM1
@app.post("/api/receive_message")
async def receive_message(request: Request):
    global conversation_history, internal_messages, waiting_for_response
    try:
        message = await request.json()
        event_type = message.get("event_type", "")
        is_internal = message.get("is_internal", False)
        text = message.get("text", "")
        reaction_name = message.get("reaction_name", "")

        if event_type == "MESSAGE":
            if is_internal:
                # Store internal messages regardless
                internal_messages.append(text)
                if show_internal_messages:
                    update_display()
            else:
                # Add assistant's message to conversation history
                conversation_history.append({
                    "role": "assistant",
                    "content": text,
                    "reactions": [],
                    "message_id": None  # Not needed for this simplified version
                })
                waiting_for_response = False
                llm_response_received.set()
                update_display()
        elif event_type in ["REACTION_ADD", "REACTION_REMOVE"]:
            # Handle reactions by adding/removing them to/from the last user message
            emoji = REACTION_EMOJI_MAP.get(reaction_name, f":{reaction_name}:")
            # Find the last user message
            for msg in reversed(conversation_history):
                if msg["role"] == "user":
                    if event_type == "REACTION_ADD":
                        if emoji not in msg["reactions"]:
                            msg["reactions"].append(emoji)
                            logger.info(f"Reaction '{emoji}' added to the last user message.")
                    elif event_type == "REACTION_REMOVE":
                        if emoji in msg["reactions"]:
                            msg["reactions"].remove(emoji)
                            logger.info(f"Reaction '{emoji}' removed from the last user message.")
                    break
            else:
                logger.warning("No user message found to add/remove reaction.")
            update_display()
        else:
            logger.debug(f"Ignored message with event_type: {event_type}")
        return {"status": "OK"}

    except Exception as e:
        logger.error(f"Error receiving message from LLM1: {str(e)}")
        test_completed_event.set()
        return

# Function to update the conversation display
def update_display():
    layout = Layout()

    # Split the layout into two columns using split_row()
    layout.split_row(
        Layout(name="left"),
        Layout(name="right")
    )

    # Left Panel: Conversation
    messages = []
    # Display only the last 10 messages to prevent overflow
    for idx, msg in enumerate(conversation_history[-10:], max(1, len(conversation_history) - 9)):
        role = msg.get("role")
        content = msg.get("content")
        reactions = msg.get("reactions", [])
        message_number = idx

        if role == "user":
            messages.append(f"[bold blue]{message_number}. You[/bold blue]: {content}")
        elif role == "assistant":
            messages.append(f"[bold green]{message_number}. LLM [ASSISTANT][/bold green]: {content}")
        elif role == "system":
            messages.append(f"[bold]{content}[/bold]")

        if reactions:
            reaction_str = ' '.join(reactions)
            messages.append(f"  [yellow]{reaction_str}[/yellow]")

    conversation_panel = Panel('\n'.join(messages), title="Conversation")
    layout["left"].update(conversation_panel)

    # Right Panel: Combined Logs and Internal Messages
    combined_content = ""

    # Add internal messages if enabled
    if show_internal_messages and internal_messages:
        internal_msgs = '\n'.join(f"[italic grey50]{msg}[/italic grey50]" for msg in internal_messages[-10:])
        combined_content += f"Internal Messages:\n{internal_msgs}\n\n"

    # Add logs
    log_contents = log_capture_string.getvalue()
    combined_content += f"Logs:\n{log_contents}"

    # Add waiting status if applicable
    if waiting_for_response:
        logger.info("Waiting for LLM [ASSISTANT] to respond...")        

    # Create a single panel
    combined_panel = Panel(combined_content.strip(), title="Logs & Internal Messages")
    layout["right"].update(combined_panel)

    live.update(layout)


# Handle user input asynchronously
async def handle_user_input():
    global conversation_history, show_internal_messages, waiting_for_response
    session = PromptSession()
    try:
        while True:
            # Stop the Live display
            live.stop()

            # Prompt user input
            user_input = await session.prompt_async("You: ")

            # Start the Live display
            live.start()

            if user_input.lower() in ('exit', 'quit'):
                console.print("Exiting.")
                test_completed_event.set()
                break

            # Send the user's message to LLM1
            await call_tested_llm(user_input)

            # Update the conversation history
            conversation_history.append({
                "role": "user",
                "content": user_input,
                "reactions": [],
                "message_id": None  # Not needed for this simplified version
            })
            update_display()

            # Show waiting message
            waiting_for_response = True
            update_display()

            # Wait for the LLM's response
            await llm_response_received.wait()
            llm_response_received.clear()

            update_display()

        # Exit when done
        test_completed_event.set()

    except Exception as e:
        logger.error(f"Error in user input: {str(e)}")
        test_completed_event.set()

# Main function to run the interactive session
async def main(show_internal_messages_arg, prompt_name):
    global show_internal_messages
    show_internal_messages = show_internal_messages_arg
    user_input_task = None  # Initialize to None
    try:
        # Start the FastAPI server in the same event loop
        config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve())
        logger.info("FastAPI server started.")

        # Load the system prompt if provided
        if prompt_name:
            system_prompt = load_system_prompt(prompt_name)
            if not system_prompt:
                console.print(f"[red]Prompt '{prompt_name}' not found.[/red]")
                test_completed_event.set()
                server.should_exit = True
                await server_task
                return
            # Add system prompt to conversation history
            conversation_history.append({
                "role": "system",
                "content": system_prompt,
                "reactions": [],
                "message_id": "system"
            })

        # Start the user input handler
        with live:
            update_display()
            user_input_task = asyncio.create_task(handle_user_input())

            # Wait for the session to be completed
            await test_completed_event.wait()
            logger.info("Session completed.")

    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
    finally:
        # Now stop the server
        logger.info("Stopping the FastAPI server...")
        server.should_exit = True

        # Cancel the user input task if it was started
        if user_input_task:
            user_input_task.cancel()
            try:
                await user_input_task
            except asyncio.CancelledError:
                pass

        # Wait for the server to finish
        await server_task

# Function to load the system prompt based on the prompt name (if needed)
def load_system_prompt(prompt_name):
    try:
        prompt_path = os.path.join("prompts", f"{prompt_name}.txt")
        if os.path.exists(prompt_path):
            # Specify UTF-8 encoding to handle special characters
            with open(prompt_path, "r", encoding="utf-8") as file:
                return file.read().strip()
        else:
            return None  # Return None if the prompt file doesn't exist
    except Exception as e:
        logger.error(f"Error loading system prompt: {str(e)}")
        return None

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Run the interactive LLM script.")
    parser.add_argument("--prompt_name", help="Name of the prompt to use for the session.")
    parser.add_argument("--show-internal-messages", action="store_true", help="Display internal messages.")
    args = parser.parse_args()

    show_internal_messages = args.show_internal_messages
    prompt_name = args.prompt_name

    try:
        asyncio.run(main(show_internal_messages, prompt_name))
    except (SystemExit, KeyboardInterrupt):
        pass
