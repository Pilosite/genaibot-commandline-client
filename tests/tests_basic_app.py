# test_app.py  
  
import pytest  
import asyncio  
import time  
from unittest.mock import patch, AsyncMock, MagicMock, call  
from datetime import datetime, timezone  
from fastapi.testclient import TestClient  
from prompt_toolkit.completion import Completion  
from basic_app import call_tested_llm, thread_id, LLM_NOTIFICATION_ENDPOINT  
import contextlib  

# Import the necessary components from your main script  
from basic_app import (  
    generate_thread_id,  
    load_system_prompt,  
    fastapi_app,  
    conversation_history,  
    call_tested_llm,  
    done_reaction_received,  
    REACTION_EMOJI_MAP,  
    print_with_timestamp,  
    reset_conversation,  
    show_last_internal_messages,  
    main,  
    start_uvicorn,  
    CommandCompleter,  
    COMMANDS,  
    thread_id,  
    last_user_message_index,  
)  
  
@pytest.fixture  
def client():  
    # Create a TestClient for the FastAPI app  
    return TestClient(fastapi_app)  
  
# Test the generate_thread_id function  
def test_generate_thread_id():  
    thread_id_1 = generate_thread_id()  
    time.sleep(0.001)  # Sleep for 1 millisecond to ensure a different timestamp  
    thread_id_2 = generate_thread_id()  
    assert isinstance(thread_id_1, str)  
    assert '.' in thread_id_1  
    assert thread_id_1 != thread_id_2  # Ensure uniqueness  
  
# Test the load_system_prompt function with an existing prompt  
def test_load_system_prompt_existing(tmp_path):  
    # Create a temporary prompts directory and a test prompt file  
    prompts_dir = tmp_path / "prompts"  
    prompts_dir.mkdir()  
    prompt_name = "test_prompt"  
    prompt_content = "This is a test system prompt."  
    prompt_file = prompts_dir / f"{prompt_name}.txt"  
    prompt_file.write_text(prompt_content, encoding="utf-8")  
      
    with patch('os.path.exists', return_value=True), \
         patch('os.path.join', return_value=str(prompt_file)):  
        loaded_prompt = load_system_prompt(prompt_name)  
        assert loaded_prompt == prompt_content  
  
# Test the load_system_prompt function with a non-existing prompt  
def test_load_system_prompt_non_existing():  
    prompt_name = "non_existing_prompt"  
    with patch('os.path.exists', return_value=False):  
        loaded_prompt = load_system_prompt(prompt_name)  
        assert loaded_prompt is None  
  
# Test the call_tested_llm function  
@pytest.mark.asyncio  
async def test_call_tested_llm():  
    user_input = "Hello, world!"  
    with patch('aiohttp.ClientSession.post') as mock_post:  
        mock_response = AsyncMock()  
        mock_response.status = 200  
        mock_post.return_value.__aenter__.return_value = mock_response  
          
        await call_tested_llm(user_input)  
          
        # Ensure the HTTP request was made with the correct parameters  
        mock_post.assert_called()  
        args, kwargs = mock_post.call_args  
        # URL is the first positional argument  
        assert args[0] == LLM_NOTIFICATION_ENDPOINT  # Use the actual endpoint from basic_app  
        assert kwargs['headers'] == {"Content-Type": "application/json"}  
        payload = kwargs['json']  
        assert payload['text'] == user_input  
        assert 'timestamp' in payload  
        assert 'thread_id' in payload  
        assert payload['thread_id'] == thread_id  # Ensure thread_id is correctly used  

# Test the FastAPI endpoint /api/receive_message for a normal message  
def test_receive_message_normal(client):  
    test_message = {  
        "event_type": "MESSAGE",  
        "text": "Hello from assistant",  
        "reaction_name": "",  
        "is_internal": False,  
    }  
  
    with patch('basic_app.print_with_timestamp') as mock_print:  
        response = client.post("/api/receive_message", json=test_message)  
        assert response.status_code == 200  
        assert response.json() == {"status": "OK"}  
  
        # Check that the message was added to the conversation history  
        assert conversation_history[-1]["content"] == "Hello from assistant"  
        assert conversation_history[-1]["role"] == "assistant"  
  
        # Verify that print_with_timestamp was called  
        mock_print.assert_called_with("Assistant", "Hello from assistant")  
  
# Test the receive_message endpoint for an internal message  
def test_receive_message_internal(client):  
    test_message = {  
        "event_type": "MESSAGE",  
        "text": "Internal assistant message",  
        "reaction_name": "",  
        "is_internal": True,  
    }  
  
    with patch('basic_app.print_with_timestamp') as mock_print:  
        response = client.post("/api/receive_message", json=test_message)  
        assert response.status_code == 200  
        assert response.json() == {"status": "OK"}  
  
        # The message should be added to the conversation history  
        assert conversation_history[-1]["content"] == "Internal assistant message"  
        assert conversation_history[-1]["role"] == "assistant_internal"  
  
        # Since show_internal_messages is False by default, print_with_timestamp should not be called  
        mock_print.assert_not_called()  
  
# Test the receive_message endpoint for a reaction 'done'  
def test_receive_message_reaction_done(client):  
    # Add a user message to the conversation history  
    conversation_history.append({  
        "role": "user",  
        "content": "User message",  
        "reactions": [],  
    })  
  
    test_message = {  
        "event_type": "REACTION_ADD",  
        "text": "",  
        "reaction_name": "done",  
        "is_internal": False,  
    }  
  
    # Mock the event loop and the method call_soon_threadsafe  
    loop = asyncio.get_event_loop()  
    with patch('basic_app.main_loop', loop), \
         patch.object(loop, 'call_soon_threadsafe') as mock_call_soon_threadsafe, \
         patch('basic_app.print_with_timestamp') as mock_print:  
        response = client.post("/api/receive_message", json=test_message)  
        assert response.status_code == 200  
        assert response.json() == {"status": "OK"}  
  
        # Verify that the reaction was added to the last user message  
        assert "✅" in conversation_history[-1]["reactions"]  
  
        # Verify that done_reaction_received.set was scheduled  
        mock_call_soon_threadsafe.assert_called_with(done_reaction_received.set)  
  
        # Verify that the reaction message was printed  
        mock_print.assert_called_with("Reaction", "'✅' added to your last message.")  
  
    # Clean up the conversation history  
    conversation_history.pop()  
  
# Test the reset_conversation function  
def test_reset_conversation():  
    # Add some messages to the conversation history  
    conversation_history.extend([  
        {"role": "user", "content": "Message 1", "reactions": []},  
        {"role": "assistant", "content": "Response 1", "reactions": []}  
    ])  
    # Mock the console methods  
    with patch('basic_app.console.clear') as mock_clear, \
         patch('basic_app.print_with_timestamp') as mock_print, \
         patch('basic_app.console.print') as mock_console_print:  
        reset_conversation()  
        assert len(conversation_history) == 0  
        # Verify that console.clear was called  
        mock_clear.assert_called()  
        # Verify that print_with_timestamp was called with reset message  
        mock_print.assert_any_call("System", "Conversation history has been reset.")  
        # Verify that a new thread ID was generated and printed  
        # Capture the actual call arguments  
        calls = mock_print.call_args_list  
        new_thread_id_message = None  
        for call_args in calls:  
            args, kwargs = call_args  
            if args[0] == "System" and args[1].startswith("New thread ID generated: "):  
                new_thread_id_message = args[1]  
                break  
        assert new_thread_id_message is not None, "New thread ID message not found"  
        # Optionally, extract the thread ID and assert it's not empty  
        new_thread_id = new_thread_id_message.split(": ")[1]  
        assert new_thread_id != "" and new_thread_id is not None  
  
# Test the show_last_internal_messages function  
def test_show_last_internal_messages():  
    # Set up the conversation history  
    conversation_history.clear()  
    conversation_history.extend([  
        {"role": "user", "content": "User message", "reactions": []},  
        {"role": "assistant_internal", "content": "Internal message 1", "reactions": []},  
        {"role": "assistant_internal", "content": "Internal message 2", "reactions": []},  
    ])  
  
    # Set the last_user_message_index  
    global last_user_message_index  
    last_user_message_index = 0  # Index of the user message  
  
    with patch('basic_app.print_with_timestamp') as mock_print, \
         patch('basic_app.console.print') as mock_console_print:  
        show_last_internal_messages()  
        # Verify that print_with_timestamp was called  
        mock_print.assert_called_with("System", "Internal messages since your last message:")  
        # Verify that internal messages were printed  
        calls = [  
            call("1. Internal message 1", style="assistant_internal"),  
            call("2. Internal message 2", style="assistant_internal")  
        ]  
        mock_console_print.assert_has_calls(calls, any_order=False)  
  
    # Test when there are no internal messages  
    conversation_history.clear()  
    conversation_history.append({"role": "user", "content": "User message", "reactions": []})  
    last_user_message_index = 0  
  
    with patch('basic_app.print_with_timestamp') as mock_print:  
        show_last_internal_messages()  
        mock_print.assert_called_with("System", "No internal messages since your last message.")  
  
# Test the print_with_timestamp function  
def test_print_with_timestamp():  
    with patch('basic_app.console.print') as mock_console_print:  
        print_with_timestamp("Assistant", "Test assistant message")  
        mock_console_print.assert_called()  
  
# Test the CommandCompleter  
def test_command_completer():  
    completer = CommandCompleter()  
    document = MagicMock()  
    document.text_before_cursor = "/"  
    completions = list(completer.get_completions(document, None))  
    # All commands should be suggested  
    assert len(completions) == len(COMMANDS)  
    assert all(isinstance(c, Completion) for c in completions)  
    # Test autocompletion for partial command  
    document.text_before_cursor = "/to"  
    completions = list(completer.get_completions(document, None))  
    # Only '/toggle_internal' should be suggested  
    assert len(completions) == 1  
    assert completions[0].text == "/toggle_internal"  
  
# Test the main function for handling the /toggle_internal command  
@pytest.mark.asyncio  
async def test_main_toggle_internal():  
    with patch('basic_app.start_uvicorn'), \
         patch('basic_app.print_with_timestamp') as mock_print, \
         patch('basic_app.console.print'), \
         patch('basic_app.patch_stdout', return_value=contextlib.nullcontext()):
        # Mock the PromptSession  
        mock_prompt_session = AsyncMock()  
        mock_prompt_session.prompt_async = AsyncMock(side_effect=["/toggle_internal", "/exit"])  
        with patch('basic_app.PromptSession', return_value=mock_prompt_session):  
            await main(show_internal_messages_arg=False, prompt_name=None)  
    # Verify that print_with_timestamp was called with the toggle message  
    mock_print.assert_any_call("Command", "Internal messages display toggled ON.")  
  
# Test the main function for handling the /show_last_mind command  
@pytest.mark.asyncio  
async def test_main_show_last_mind():  
    # Set up the conversation history  
    conversation_history.clear()  
    conversation_history.extend([  
        {"role": "user", "content": "User message 1", "reactions": []},  
        {"role": "assistant_internal", "content": "Internal message 1", "reactions": []},  
        {"role": "assistant_internal", "content": "Internal message 2", "reactions": []},  
    ])  
  
    with patch('basic_app.start_uvicorn'), \
         patch('basic_app.print_with_timestamp') as mock_print, \
         patch('basic_app.console.print') as mock_console_print, \
         patch('basic_app.patch_stdout', return_value=contextlib.nullcontext()):
        # Set last_user_message_index to 0  
        global last_user_message_index  
        last_user_message_index = 0  
  
        # Mock the PromptSession  
        mock_prompt_session = AsyncMock()  
        mock_prompt_session.prompt_async = AsyncMock(side_effect=["/show_last_mind", "/exit"])  
        with patch('basic_app.PromptSession', return_value=mock_prompt_session):  
            await main(show_internal_messages_arg=False, prompt_name=None)  
    # Verify that print_with_timestamp was called with the internal messages  
    mock_print.assert_any_call("System", "Internal messages since your last message:")  
    calls = [  
        call("1. Internal message 1", style="assistant_internal"),  
        call("2. Internal message 2", style="assistant_internal")  
    ]  
    mock_console_print.assert_has_calls(calls, any_order=False)  
  
# Test the main function for handling an unknown command  
@pytest.mark.asyncio  
async def test_main_unknown_command():  
    with patch('basic_app.start_uvicorn'), \
         patch('basic_app.print_with_timestamp') as mock_print, \
         patch('basic_app.console.print'), \
         patch('basic_app.patch_stdout', return_value=contextlib.nullcontext()):  
        # Mock the PromptSession  
        mock_prompt_session = AsyncMock()  
        mock_prompt_session.prompt_async = AsyncMock(side_effect=["/unknown", "/exit"])  
        with patch('basic_app.PromptSession', return_value=mock_prompt_session):  
            await main(show_internal_messages_arg=False, prompt_name=None)  
    # Verify that print_with_timestamp was called with the error message  
    mock_print.assert_any_call("Error", "Unknown command.")  
  
# Test start_uvicorn function  
def test_start_uvicorn():  
    with patch('uvicorn.Server') as mock_server:  
        start_uvicorn()  
      
        # Verify that the server was started  
        mock_server.return_value.run.assert_called()  
  
# Test the color change for assistant_internal messages  
def test_console_theme():  
    from basic_app import custom_theme  
    # Verify that assistant_internal is set to 'bright_black'  
    style = custom_theme.styles['assistant_internal']  
    # The style object can be compared by its color name  
    assert style.color.name == 'bright_black'  
