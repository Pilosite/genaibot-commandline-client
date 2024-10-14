import os
import sys
import json
import asyncio
import logging
import argparse
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

import aiohttp
import aioconsole  # For asynchronous console input/output
import coloredlogs
import uvicorn
from fastapi import FastAPI, Request
from dotenv import load_dotenv

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

# Custom log levels
LLM_LEVEL = 21  # A number between INFO (20) and WARNING (30)
SUCCESS_LEVEL = 25  # A number between INFO (20) and WARNING (30)

# Adding new levels to the logging system
logging.addLevelName(LLM_LEVEL, "LLM")
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")

# Adjust uvicorn and asyncio logging
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("asyncio").propagate = False

# Custom logger
def setup_logging():
    # Create logger
    logger = logging.getLogger("app_logger")
    logger.setLevel(logging.INFO)

    # Define a function for logging LLM messages
    def llm(self, message, *args, **kws):
        if self.isEnabledFor(LLM_LEVEL):
            self._log(LLM_LEVEL, message, args, **kws)

    # Define a function for logging success messages
    def success(self, message, *args, **kws):
        if self.isEnabledFor(SUCCESS_LEVEL):
            self._log(SUCCESS_LEVEL, message, args, **kws)

    # Add the custom methods to the logger
    logging.Logger.llm = llm
    logging.Logger.success = success

    # Install coloredlogs with custom level styles
    coloredlogs.install(
        level='INFO',
        logger=logger,
        fmt='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
        level_styles={
            'info': {'color': 'white'},
            'llm': {'color': 'cyan', 'bold': True},
            'success': {'color': 'green', 'bold': True},
            'warning': {'color': 'yellow'},
            'error': {'color': 'red'},
            'critical': {'color': 'magenta', 'bold': True}
        }
    )

    return logger

# Setup the logger
logger = setup_logging()

conversation_history = []
test_completed_event = asyncio.Event()
show_internal_messages = False  # Will be set based on command-line argument

# Create an event to wait for LLM responses
llm_response_received = asyncio.Event()

# Generate a unique timestamp for the thread_id, with 4 digits after the decimal point
def generate_thread_id():
    current_timestamp = datetime.now(timezone.utc).timestamp()
    thread_id = "{:.4f}".format(current_timestamp)
    return thread_id

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

# Function to send user input to the tested LLM (LLM1)
async def call_tested_llm(user_input, thread_id):
    headers = {"Content-Type": "application/json"}

    # Generate a unique timestamp for the message
    current_timestamp = datetime.now(timezone.utc).timestamp()
    timestamp_with_millis = "{:.4f}".format(current_timestamp)

    payload = {
        "channel_id": 1,
        "event_type": "MESSAGE",
        "response_id": None,
        "text": user_input,
        "thread_id": thread_id,
        "timestamp": timestamp_with_millis,
        "user_email": f"{CLIENT_ID}@example.com",
        "user_id": CLIENT_ID,
        "user_name": CLIENT_ID,
        "reaction_name": None,
        "files_content": [],
        "images": [],
        "is_mention": True,
        "origin_plugin_name": CLIENT_ID,
        "message_type": "TEXT",
        "is_internal": False,
        "raw_data": user_input,
        "username": CLIENT_ID,
        "event_label": "message",
        "api_app_id": "genaibot",
        "app_id": "genaibot"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(LLM_NOTIFICATION_ENDPOINT, headers=headers, json=payload) as response:
                if response.status in [200, 202]:
                    await aioconsole.aprint("Message accepted by LLM [ASSISTANT] successfully.")
                else:
                    await aioconsole.aprint(f"Failed to send message to LLM [ASSISTANT]: {response.status}")
                    test_completed_event.set()
                    return
        except aiohttp.ClientConnectorError as e:
            await aioconsole.aprint(f"Connection error: {str(e)}. Exiting.")
            test_completed_event.set()
            return
        except Exception as e:
            await aioconsole.aprint(f"Error during LLM [ASSISTANT] interaction: {str(e)}. Exiting.")
            test_completed_event.set()
            return

# ReactionBase and GenericRestReactions classes
class ReactionBase:
    pass

class GenericRestReactions(ReactionBase):
    PROCESSING = "processing"
    DONE = "done"
    ACKNOWLEDGE = "acknowledge"
    GENERATING = "generating"
    WRITING = "writing"
    ERROR = "error"
    WAIT = "wait"

    def get_reaction(self):
        return self.value

# Function to map reaction names to GenericRestReactions
def map_reaction(reaction_name):
    try:
        for reaction in GenericRestReactions.__dict__:
            if not reaction.startswith('__') and getattr(GenericRestReactions, reaction) == reaction_name:
                return reaction  # Return the enum name
        return reaction_name  # Return as-is if not found
    except Exception as e:
        logger.error(f"Error mapping reaction: {str(e)}")
        return reaction_name

# Receive message from LLM1
@app.post("/api/receive_message")
async def receive_message(request: Request):
    global conversation_history
    try:
        message = await request.json()
        event_type = message.get("event_type", "")
        is_internal = message.get("is_internal", False)  # default to False

        if event_type == "MESSAGE":
            llm1_response = message.get("text", "")
            if is_internal and show_internal_messages:
                await aioconsole.aprint(f"\n[INTERNAL MESSAGE]: {llm1_response}")
            elif not is_internal:
                await aioconsole.aprint(f"\nLLM [ASSISTANT]: {llm1_response}")
                # Optionally, update conversation history
                conversation_history.append({"role": "assistant", "content": llm1_response})

                # Signal that the LLM has responded
                llm_response_received.set()

        elif event_type == "ADD_REACTION":
            reaction_name = message.get("reaction_name", "")
            reaction = map_reaction(reaction_name)
            await aioconsole.aprint(f"\n[Reaction added]: {reaction}")

        elif event_type == "REMOVE_REACTION":
            reaction_name = message.get("reaction_name", "")
            reaction = map_reaction(reaction_name)
            await aioconsole.aprint(f"\n[Reaction removed]: {reaction}")

        else:
            logger.debug(f"Ignored message with event_type: {event_type}")

        return {"status": "OK"}

    except Exception as e:
        await aioconsole.aprint(f"Error receiving message from LLM1: {str(e)}")
        test_completed_event.set()
        return

# Handle user input asynchronously
async def handle_user_input(thread_id):
    global conversation_history
    try:
        while True:
            user_input = await aioconsole.ainput("You: ")
            if user_input.lower() in ('exit', 'quit'):
                await aioconsole.aprint("Exiting.")
                test_completed_event.set()
                break

            # Send the user's message to LLM1
            await call_tested_llm(user_input, thread_id)

            # Update the conversation history
            conversation_history.append({"role": "user", "content": user_input})

            await aioconsole.aprint("Waiting for LLM [ASSISTANT] to respond...")

            # Wait for the LLM's response
            await llm_response_received.wait()
            llm_response_received.clear()

    except Exception as e:
        await aioconsole.aprint(f"Error in user input: {str(e)}")
        test_completed_event.set()

# Main function to run the interactive session
async def main(show_internal_messages_arg, prompt_name):
    global show_internal_messages
    show_internal_messages = show_internal_messages_arg
    try:
        # Start the FastAPI server in the same event loop
        config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve())
        logger.info("FastAPI server started.")

        # Generate the thread_id once at the beginning
        thread_id = generate_thread_id()

        # Load the system prompt if provided
        if prompt_name:
            system_prompt = load_system_prompt(prompt_name)
            if not system_prompt:
                await aioconsole.aprint(f"Prompt '{prompt_name}' not found.")
                test_completed_event.set()
                server.should_exit = True
                await server_task
                return
            conversation_history.append({"role": "system", "content": system_prompt})

        # Start the user input handler
        user_input_task = asyncio.create_task(handle_user_input(thread_id))

        # Wait for the session to be completed
        await test_completed_event.wait()
        logger.info("Session completed.")

    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
    finally:
        # Now stop the server
        logger.info("Stopping the FastAPI server...")
        server.should_exit = True

        # Cancel the user input task
        user_input_task.cancel()
        try:
            await user_input_task
        except asyncio.CancelledError:
            pass

        # Wait for the server to finish
        await server_task

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
