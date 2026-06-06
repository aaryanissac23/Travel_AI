# Asynchronous & Cyclical Travel Planner Engine

An adaptive travel planner application built with **LangGraph** and the **Groq API** (`llama-3.3-70b-versatile`). The engine fetches flight and hotel options concurrently using asynchronous processes, selects an itinerary, and critiques the budget using Groq's structured JSON outputs. If the itinerary exceeds the budget, the graph self-corrects by evaluating progressively cheaper alternative flight and hotel options iteratively until an optimal package fits the budget or the iteration limit is reached.

## Features
- **Parallel Fan-Out/Fan-In Execution**: Fetches flights and hotels concurrently using `asyncio.gather` with proof in console execution timestamps.
- **Graph Visualization**: Renders an ASCII text-based representation of the compiled LangGraph workflow topology automatically on startup (requires `grandalf`).
- **Groq Structured Output Critique**: Utilizes Pydantic validation schemas directly with Groq (`llama-3.3-70b-versatile`) to verify numbers and audit the budget.
- **Cyclical Self-Correction Loop**: Routes state back to gather cheaper prices if budget constraints are violated, passing error context backward.
- **Resiliency & Validation**:
  - `max_retries` configured on `ChatGoogleGenerativeAI`.
  - Non-negative validation on prices.
  - Non-empty validation on destinations.
  - Iteration limits to prevent infinite loops (raises `RuntimeError`).

---

## Setup Instructions

### 1. Environment Setup
Create a virtual environment:
```bash
python -m venv venv
```

Activate the virtual environment:
- **On Windows**:
  ```cmd
  venv\Scripts\activate
  ```
- **On macOS/Linux**:
  ```bash
  source venv/bin/activate
  ```

### 2. Install Dependencies
Install all required libraries:
```bash
pip install -r requirements.txt
```

### 3. Set API Key
Export your Groq API Key as an environment variable:
- **On Windows Command Prompt (cmd)**:
  ```cmd
  set GROQ_API_KEY=your_api_key_here
  ```
- **On Windows PowerShell**:
  ```powershell
  $env:GROQ_API_KEY="your_api_key_here"
  ```
- **On macOS/Linux**:
  ```bash
  export GROQ_API_KEY="your_api_key_here"
  ```

### 4. Run the Application
Start the interactive CLI:
```bash
python main.py
```

---

## Interactive Menu Options
When running `python main.py`, the CLI provides options to run preset scenarios:
1. **Success Demo (Japan, Budget $800)**: Resolves instantly on Iteration 0.
2. **Self-Correction Demo (Japan, Budget $150)**: Exceeds budget initially, loops back to fetch systematically cheaper alternative flight and hotel options, and passes successfully.
3. **Failure Demo (Japan, Budget $80)**: Triggers the maximum iterations count and cleanly reports that the budget is not justifiable.
4. **Custom Input**: Manually specify any country and budget.
5. **Exit**: Exits the planner.
