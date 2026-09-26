# AI Cook Assistant Documentation

## 1. System Overview
The AI Cook Assistant is a voice-first, vision-enabled cooking companion application. It is designed to assist users, including those with visual impairments, by providing step-by-step recipe instructions, identifying objects, evaluating food doneness, and tracking kitchen hazards in real time.

The application operates via a local FastAPI backend serving a vanilla JavaScript frontend. It utilizes local computer vision models for real-time detection and cloud-based Large Language Models (LLMs) for complex reasoning and voice transcription.

## 2. Architecture and Technology Stack

### Backend
*   **Framework**: FastAPI (Python) running on Uvicorn.
*   **Database**: SQLite (`cook.db`), populated on first boot from a version-controlled JSON seed file (`recipes.json`).
*   **Local Computer Vision**: OpenVINO and YOLO models for real-time continuous object and hand detection.
*   **Cloud AI Integration**: OpenAI API (GPT-4o-mini) for image analysis, step reasoning, and Whisper for audio transcription.
*   **Security**: Local pairing token authentication for LAN access. Output guardrails and heuristic checks to prevent LLM prompt injection and false safety claims.

### Frontend
*   **Framework**: Vanilla HTML, CSS, and JavaScript.
*   **Media Handling**: `getUserMedia` for continuous camera access and microphone recording.
*   **Accessibility**: Full screen reader compatibility, ARIA live regions, and audible feedback (earcons/speech synthesis) for state changes.

## 3. Core Features

### 3.1. Voice Command System
The system relies on a structured voice interface to prevent accidental triggers in a noisy kitchen environment.
*   **Push-to-Talk**: Users hold a physical or virtual button to record audio. The audio blob is sent to the backend, transcribed, and mapped to a strict closed list of actions (e.g., next_step, start_timer, repeat_step).
*   **Text-Based Wake Word (Experimental)**: A continuous local listener utilizing the browser Web Speech API designed to trigger hands-free commands. It captures text locally and posts directly to a `/voice/text` endpoint, bypassing audio uploads.

### 3.2. Vision and Reasoning
*   **Identify (What is this?)**: Captures the current camera frame and asks the LLM to identify ingredients or tools.
*   **Check Doneness (Is it ready?)**: Evaluates the food against the expected state of the current recipe step, utilizing reference images and textual heuristics.
*   **Safety Monitoring**: The LLM flags critical hazards (e.g., raw poultry cross-contamination, burning oil). Output guards silently downgrade LLM responses that claim high confidence without sufficient evidence.

### 3.3. Real-Time Detection
*   A background loop captures frames at a target of 4 to 5 FPS and sends them to the local detection API.
*   The backend returns bounding boxes and confidence scores for hands, utensils, cookware, and hazards.
*   The frontend renders these boxes on a canvas overlay and displays a tabular summary.

### 3.4. Recipe Management
*   **Data Structure**: Recipes contain localized names, aliases, ingredients, and sequential steps with expected durations and safety markers.
*   **Import Pipeline**: Dedicated Python scripts scrape and normalize recipes from external URLs (including Greek websites).
*   **Curation**: Imported recipes are staged, merged, and deduplicated locally before being written to the primary `recipes.json` datastore.

## 4. Development Process Summary

The recent development cycles focused on expanding the recipe database, improving local development workflows, and refining the user experience.

1.  **Database Expansion**: Populated the seed JSON with bilingual (English and Greek) recipes, complete with safety metadata and timings.
2.  **Import Tooling**: Developed command-line utilities to pull and format copyrighted recipes from Greek domains for local usage.
3.  **Authentication Adjustments**: Modified the authentication middleware to automatically bypass pairing token requirements for local connections (127.0.0.1), streamlining testing.
4.  **Wake Word Integration**: Built a frontend Web Speech API listener to detect a trigger phrase (Hey Chef) and submit transcribed text to a newly created backend text command endpoint. Added robust phonetic matching to account for Greek transcription quirks.
5.  **Caching and Lifecycle UX**: 
    *   Implemented strict no-cache headers in the FastAPI server to prevent aggressive browser caching in local PWA windows.
    *   Updated the startup sequence to audibly notify the user when the local detection model finishes loading into memory, followed by a conversational prompt.

## 5. Known Limitations
*   The experimental Web Speech API wake word relies on continuous browser transcription, which is entirely unsupported in Firefox and can be preempted by OS-level microphone exclusivity locks in certain Chrome/Edge configurations.
*   Real-time detection latency is heavily dependent on the host machine CPU. Frame rate is throttled dynamically to prevent thermal throttling.
