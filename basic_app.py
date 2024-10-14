import os  
import asyncio  
import logging  
import threading  
from datetime import datetime, timezone  
from io import StringIO  
  
import aiohttp  
import uvicorn  
from fastapi import FastAPI, Request  
from dotenv import load_dotenv  
from prompt_toolkit import PromptSession  
from prompt_toolkit.patch_stdout import patch_stdout  
  
import typer  
from rich.console import Console  
from rich.theme import Theme  
  
# Instanciation de l'application Typer  
app = typer.Typer()  
  
# Chargement des variables d'environnement depuis .env  
load_dotenv()  
  
# Instance FastAPI  
fastapi_app = FastAPI()  
  
# Récupération des valeurs des variables d'environnement  
CLIENT_ID = os.getenv("CLIENT_ID", "default_client")  
LLM_NOTIFICATION_ENDPOINT = os.getenv("LLM_NOTIFICATION_ENDPOINT", "http://localhost:8000/api/receive_message")  
  
# Configuration du logging  
logger = logging.getLogger("app_logger")  
logger.setLevel(logging.INFO)  
log_capture_string = StringIO()  
stream_handler = logging.StreamHandler(log_capture_string)  
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')  
stream_handler.setFormatter(formatter)  
logger.addHandler(stream_handler)  
logger.propagate = False  
  
# Initialisation de l'historique des conversations et des flags  
conversation_history = []  # Stocke les messages et réactions  
show_internal_messages = False  # Toggle pour afficher les messages internes  
waiting_for_response = False  
  
# Définition d'un thème personnalisé pour une meilleure lisibilité  
custom_theme = Theme({  
    "you": "bold blue",  
    "assistant": "bold green",  
    "assistant_internal": "bold yellow",  
    "reaction": "yellow",  
    "command": "cyan",  
    "error": "bold red",  
    "system": "bold magenta"  
})  
  
# Console Rich pour l'affichage formaté  
console = Console(theme=custom_theme)  
  
# Mapping des noms de réactions aux emojis  
REACTION_EMOJI_MAP = {  
    "processing": "⚙️",  
    "done": "✅",  
    "acknowledge": "👀",  
    "generating": "🤔",  
    "writing": "✏️",  
    "error": "❌",  
    "wait": "⌚",  
}  
  
# Événement pour signaler que l'assistant a terminé le traitement  
done_reaction_received = asyncio.Event()  
  
# Variable globale pour la boucle d'événements principale  
main_loop = None  
  
def print_with_timestamp(role: str, message: str):  
    """Affiche un message avec un timestamp."""  
    current_time = datetime.now().strftime("%H:%M:%S")  
    console.print(f"[{current_time}] [{role}] {message}")  
  
# Fonction pour envoyer l'entrée utilisateur au LLM testé (LLM1)  
async def call_tested_llm(user_input: str):  
    headers = {"Content-Type": "application/json"}  
  
    # Génération d'un timestamp unique pour le message  
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
        except Exception as e:  
            logger.error(f"Error during LLM [ASSISTANT] interaction: {str(e)}.")  
  
# Endpoint FastAPI pour recevoir les messages de LLM1  
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
            # Affichage différent pour les messages internes  
            if is_internal and show_internal_messages:  
                conversation_history.append({  
                    "role": "assistant_internal",  
                    "content": text,  
                    "reactions": [],  
                })  
                print_with_timestamp("ASSISTANT (internal)", text)  
            elif not is_internal:  
                conversation_history.append({  
                    "role": "assistant",  
                    "content": text,  
                    "reactions": [],  
                })  
                print_with_timestamp("Assistant", text)  
        elif event_type == "REACTION_ADD":  
            emoji = REACTION_EMOJI_MAP.get(reaction_name.lower(), f":{reaction_name}:")  
            # Trouver le dernier message de l'utilisateur  
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
  
# Fonction pour démarrer le serveur uvicorn dans un thread séparé  
def start_uvicorn():  
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8000, log_level="warning")  
    server = uvicorn.Server(config)  
    server.run()  
  
# Fonction pour réinitialiser l'historique de la conversation et rafraîchir la console  
def reset_conversation():  
    global conversation_history  
    conversation_history.clear()  
    console.clear()  
    print_with_timestamp("System", "Conversation history has been reset.")  
    console.print("Available Commands:")  
    console.print("  /toggle_internal - Toggle internal messages on/off.")  
    console.print("  /reset            - Clear the conversation history.")  
    console.print("  /exit or /quit    - Exit the application.\n")  
  
# Fonction principale pour exécuter la session interactive  
async def main(show_internal_messages_arg: bool, prompt_name: str):  
    global waiting_for_response, show_internal_messages, main_loop  
  
    # Définir le flag pour les messages internes  
    show_internal_messages = show_internal_messages_arg  
  
    # Démarrer le serveur FastAPI dans un thread séparé  
    server_thread = threading.Thread(target=start_uvicorn, daemon=True)  
    server_thread.start()  
    logger.info("FastAPI server started.")  
  
    # Obtenir la boucle d'événements principale  
    main_loop = asyncio.get_running_loop()  
  
    session = PromptSession()  
  
    # Afficher un message de bienvenue  
    print_with_timestamp("System", "Welcome to the Assistant CLI!")  
    console.print("Available Commands:")  
    console.print("  /toggle_internal - Toggle internal messages on/off.")  
    console.print("  /reset            - Clear the conversation history.")  
    console.print("  /exit or /quit    - Exit the application.\n")  
  
    # Charger le prompt système si fourni  
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
  
    # Boucle d'interaction avec l'utilisateur  
    try:  
        while True:  
            with patch_stdout():  
                user_input = await session.prompt_async("You: ")  
  
            # Vérifier les commandes slash  
            if user_input.startswith("/"):  
                if user_input == "/toggle_internal":  
                    show_internal_messages = not show_internal_messages  
                    status = "ON" if show_internal_messages else "OFF"  
                    print_with_timestamp("Command", f"Internal messages display toggled {status}.")  
                    continue  
                elif user_input == "/reset":  
                    reset_conversation()  
                    continue  
                elif user_input in ('/exit', '/quit'):  
                    print_with_timestamp("System", "Exiting.")  
                    break  
                else:  
                    print_with_timestamp("Error", "Unknown command.")  
                    continue  
  
            # Ajouter le message de l'utilisateur à l'historique  
            conversation_history.append({  
                "role": "user",  
                "content": user_input,  
                "reactions": [],  
            })  
  
            # Afficher l'entrée utilisateur avec timestamp  
            print_with_timestamp("You", user_input)  
  
            # Envoyer le message de l'utilisateur au LLM1  
            await call_tested_llm(user_input)  
  
            # Afficher le message d'attente  
            waiting_for_response = True  
            print_with_timestamp("System", "Waiting for assistant to respond...")  
  
            # Réinitialiser l'événement avant d'attendre  
            done_reaction_received.clear()  
  
            # Attendre la réception de la réaction 'done'  
            await done_reaction_received.wait()  
  
            # Après la réception de 'done', reprendre le contrôle  
            waiting_for_response = False  
  
            # Afficher une ligne vide pour séparer les interactions  
            console.print()  
  
    except Exception as e:  
        logger.error(f"Error in user input: {str(e)}")  
    finally:  
        # Pas besoin d'arrêter le serveur, il s'arrête avec le thread daemon  
        pass  
  
# Fonction pour charger le prompt système  
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
  
# Définir le point d'entrée CLI avec Typer  
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
