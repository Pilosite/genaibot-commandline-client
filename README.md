# Genai Bot Assistant CLI Application

Welcome to the **Genai Bot Assistant CLI Application**! This command-line interface allows you to interact with an AI assistant through a terminal. It provides features like sending messages, viewing internal assistant messages, and handling reactions.

This repository contains the application code and a comprehensive test suite to ensure its functionality.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Running the Application](#running-the-application)
  - [Available Commands](#available-commands)
- [Testing](#testing)
  - [Running Tests](#running-tests)
- [Customization](#customization)
  - [System Prompts](#system-prompts)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Interactive Prompt**: Communicate with the assistant in real-time via the terminal.
- **Command Support**: Use slash commands to control the application (e.g., `/reset`, `/toggle_internal`).
- **Internal Messages**: View internal assistant messages for deeper insights.
- **Reactions Handling**: The assistant can send reactions to your messages.
- **Thread Management**: Each conversation session uses a unique thread ID.
- **Extensive Testing**: A suite of tests ensures that the application works as expected.

## Prerequisites

- **Python 3.7+**
- **pip** (Python package installer)
- Recommended to use a virtual environment (e.g., `venv`, `conda`)
- **Younited Genaibot Framework**

  The assistant relies on the [Younited Genaibot framework](https://github.com/YounitedCredit/younited-genaibots) for processing messages and reactions.

## Installation

1. **Clone the Repository**

   ```bash
   git clone https://github.com/yourusername/assistant-cli.git
   cd assistant-cli
   ```

2. **Create a Virtual Environment**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

   The `requirements.txt` includes:

   - `fastapi`
   - `uvicorn`
   - `aiohttp`
   - `typer`
   - `rich`
   - `prompt_toolkit`
   - `pytest`
   - `pytest-asyncio`
   - `pytest-cov`
   - `python-dotenv`

4. **Install Younited Genaibot Framework**

   The Assistant CLI application requires the Younited Genaibot framework to function properly.

   **Clone the Younited Genaibot Repository**

   ```bash
   git clone https://github.com/YounitedCredit/younited-genaibots.git
   ```

   **Navigate to the Repository Directory**

   ```bash
   cd younited-genaibots
   ```

   **Install the Framework Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

   **Set Up the Configuration**

   Configure the `config.yaml` file as described in the [Configuration of Younited Genaibot Framework](#configuration-of-younited-genaibot-framework) section.

## Configuration

Before running the application, you need to set up your environment variables and configure the Younited Genaibot framework.

### Setting Up the `.env` File

1. **Create a `.env` File**

   Copy the `.env.template` file to `.env`:

   ```bash
   cp env.template .env
   ```

2. **Fill in the Required Values**

   Open the `.env` file and fill in the necessary values:

   - **CLIENT_ID**: An identifier for your client application.
   - **LLM_NOTIFICATION_ENDPOINT**: The endpoint URL where the assistant sends and receives messages.
     - Example: `http://localhost:8000/api/receive_message`
   - **TIMEOUT**: (Optional) Timeout duration in seconds.
   - **MAX_ITERATIONS**: (Optional) Maximum number of iterations.
   - **DEBUG_MODE**: (Optional) Set to `True` for debug mode.

### Configuration of Younited Genaibot Framework

You need to configure the `config.yaml` file of the Younited Genaibot framework to enable communication with the Assistant CLI application.

1. **Locate the `config.yaml` File**

   The `config.yaml` file is typically located in the root directory of the Younited Genaibot framework repository.

2. **Edit the `config.yaml` File**

   Add or update the following section in the `config.yaml`:

   ```yaml
   USER_INTERACTIONS:
     CUSTOM_API:
       # {}
       GENERIC_REST:
         PLUGIN_NAME: "generic_rest"
         GENERIC_REST_ROUTE_PATH: "/api/get_generic_rest_notification"
         GENERIC_REST_ROUTE_METHODS: ["POST"]
         GENERIC_REST_BEHAVIOR_PLUGIN_NAME: "im_default_behavior"
         GENERIC_REST_MESSAGE_URL: "http://localhost:8000/api/receive_message"
         GENERIC_REST_REACTION_URL: "http://localhost:8000/api/receive_message"
         GENERIC_REST_BOT_ID: "GenaiBotDebugger"
   ```

   **Explanation of the Configuration**:

   - **PLUGIN_NAME**: Specifies the plugin used for the generic REST interaction.
   - **GENERIC_REST_ROUTE_PATH**: The API route path for receiving notifications.
   - **GENERIC_REST_ROUTE_METHODS**: The HTTP methods allowed for the route.
   - **GENERIC_REST_BEHAVIOR_PLUGIN_NAME**: The behavior plugin to use.
   - **GENERIC_REST_MESSAGE_URL**: The URL where the bot receives messages from the assistant.
   - **GENERIC_REST_REACTION_URL**: The URL where the bot sends reactions to the assistant.
   - **GENERIC_REST_BOT_ID**: An identifier for the bot.

3. **Ensure Endpoints Match**

   - The `GENERIC_REST_MESSAGE_URL` and `GENERIC_REST_REACTION_URL` should match the `LLM_NOTIFICATION_ENDPOINT` specified in your `.env` file for the Assistant CLI application (e.g., `http://localhost:8000/api/receive_message`).

### Running the Younited Genaibot Framework

Before starting the Assistant CLI application, you need to run the Younited Genaibot backend:

```bash
# Inside the younited-genaibots directory
python run.py
```

Ensure that the framework is running and listening on the appropriate ports as configured.

## Usage

### Running the Application

To start the Assistant CLI application, make sure the Younited Genaibot framework is running, then run:

```bash
python basic_app.py run
```

#### Optional Arguments

- `--prompt-name TEXT`: Name of a system prompt to load from the `prompts/` directory.
- `--show-internal-messages`: Display internal assistant messages during the conversation.

**Example:**

```bash
python basic_app.py run --prompt-name my_prompt --show-internal-messages
```

### Available Commands

Within the application, you can use the following commands:

- `/toggle_internal`: Toggle the display of internal messages on or off.
- `/reset`: Clear the conversation history and reset the thread ID.
- `/show_last_mind`: Display internal messages since your last message.
- `/exit` or `/quit`: Exit the application.

**Note**: Commands must be typed exactly as shown, starting with a forward slash (`/`).

## Testing

The project includes a suite of tests located in `tests/test_app.py` to ensure the application's functionality.

### Running Tests

To run the tests, use:

```bash
pytest --cov=basic_app tests/test_app.py
```

This command runs the tests and generates a coverage report.

#### Generating an HTML Coverage Report

To generate an HTML report of the test coverage:

```bash
pytest --cov=basic_app --cov-report=html tests/test_app.py
```

The report will be available in the `htmlcov` directory. Open `htmlcov/index.html` in your browser to view it.

#### Resolving Test Environment Issues

When running tests, you might encounter a `NoConsoleScreenBufferError` on Windows. This is due to `prompt_toolkit` attempting to access the console in a test environment.

**Solution**: The tests have been adjusted to mock `patch_stdout` during testing.

## Customization

### System Prompts

You can provide custom system prompts for the assistant by placing `.txt` files in the `prompts/` directory.

**Steps to Add a Custom Prompt:**

1. Create a `prompts` directory if it doesn't exist:

   ```bash
   mkdir prompts
   ```

2. Add your prompt file:

   ```bash
   echo "Your custom prompt content here." > prompts/my_prompt.txt
   ```

3. Run the application with the `--prompt-name` argument:

   ```bash
   python basic_app.py run --prompt-name my_prompt
   ```

## Contributing

Contributions are welcome! Please follow these steps:

1. **Fork the Repository**

   Click the "Fork" button at the top right corner of the GitHub page.

2. **Clone Your Fork**

   ```bash
   git clone https://github.com/yourusername/assistant-cli.git
   cd assistant-cli
   ```

3. **Create a New Branch**

   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **Make Changes**

   Implement your feature or fix.

5. **Run Tests**

   Ensure all tests pass before committing your changes.

   ```bash
   pytest --cov=basic_app tests/test_app.py
   ```

6. **Commit and Push**

   ```bash
   git add .
   git commit -m "Describe your changes"
   git push origin feature/your-feature-name
   ```

7. **Create a Pull Request**

   Go to your forked repository on GitHub and create a pull request to the main repository.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

🤖 **Assistant CLI Application** - Empowering your terminal interactions with an AI assistant!

Feel free to open issues or submit pull requests for improvements or bug fixes.

---

## Support

If you encounter any issues or have questions about the setup, please open an issue on the GitHub repository or contact the maintainer.

---

**Note**: Always ensure that both the Assistant CLI application and the Younited Genaibot framework are running simultaneously and properly configured to communicate with each other.
