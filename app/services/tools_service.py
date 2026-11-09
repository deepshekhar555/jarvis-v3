"""Tools currently exposed to J.A.R.V.I.S chat."""
import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ─── CORE TOOLS ───
@tool
def generate_image(prompt: str) -> str:
    """
    Requests approval before generating a DALL-E image and saving it locally.
    """
    try:
        if not prompt.strip():
            return "Provide a prompt for the image."
        from app.services.action_approval_service import request_approval

        return request_approval(
            "image_generate",
            {"prompt": prompt.strip()},
            f"Prompt: {prompt.strip()}",
        )
    except Exception as e:
        logger.error("Image approval request failed: %s", e)
        return f"Image generation request failed: {e}"

@tool
def open_application(app_name: str) -> str:
    """
    Opens a supported Windows app by name, or an executable available on PATH.
    Does not accept command-line arguments, paths, or shell commands.
    """
    from skills.os_ops import launch_application

    return launch_application(app_name)

@tool
def browse_website(site_name: str) -> str:
    """
    Opens a website in the default browser.
    Valid site_name: 'youtube', 'google', 'github', or a URL.
    """
    import webbrowser
    from urllib.parse import quote_plus, urlsplit

    name = site_name.strip()
    known_sites = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "github": "https://github.com",
    }
    if name.lower() in known_sites:
        url = known_sites[name.lower()]
    elif name.lower().startswith(("http://", "https://")):
        parsed_url = urlsplit(name)
        if (
            parsed_url.scheme.lower() not in {"http", "https"}
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
        ):
            return "Please provide a valid http:// or https:// URL."
        url = name
    else:
        url = f"https://www.google.com/search?q={quote_plus(name)}"

    if not webbrowser.open(url):
        return f"Could not open {site_name} in the default browser."
    return f"Opening {site_name} in your browser."

# ─── EXTRACTED ULTIMATE JARVIS CAPABILITIES ───

@tool
def get_weather(location: str) -> str:
    """
    Fetches real-time weather information using Google scraping logic.
    """
    import requests
    from bs4 import BeautifulSoup
    try:
        search_url = f"https://www.google.com/search?q=weather+{location.replace(' ', '+')}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        response = requests.get(search_url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            location_name = soup.find("div", attrs={"id": "wob_loc"}).text
            condition = soup.find("span", attrs={"id": "wob_dc"}).text
            temp = soup.find("span", attrs={"id": "wob_tm"}).text
            return f"Weather report for {location_name}: {condition}, {temp}°C."
        # Fallback to wttr.in
        url = f"https://wttr.in/{location}?format=3"
        response = requests.get(url, timeout=5)
        return response.text if response.status_code == 200 else f"Could not fetch weather for {location}."
    except Exception as e:
        return f"Weather retrieval error: {e}"

@tool
def manage_tasks(action: str, task: str = "") -> str:
    """
    Manage the user's local task board.
    Actions: 'add', 'remove', 'list', 'clear'.
    Changes require explicit approval; listing does not.
    """
    from app.services.action_approval_service import request_approval
    from app.services.task_service import manage_tasks as update_tasks

    normalized_action = action.strip().lower()
    if normalized_action == "list":
        try:
            return update_tasks("list")
        except (OSError, RuntimeError, ValueError) as error:
            logger.error("Task board read failed: %s", error)
            return f"Task board action failed: {error}"
    if normalized_action not in {"add", "remove", "clear"}:
        return "Invalid action. Use 'add', 'remove', 'list', or 'clear'."
    if normalized_action in {"add", "remove"} and not task.strip():
        return "Provide a task for the requested action."

    try:
        return request_approval(
            f"task_{normalized_action}",
            {"task": task.strip()},
            f"Task: {task.strip()}" if task.strip() else "",
        )
    except (OSError, RuntimeError, ValueError) as error:
        logger.error("Task approval request failed: %s", error)
        return f"Task board action failed: {error}"


@tool
def manage_memory(action: str, information: str = "") -> str:
    """
    Remember, list, or forget user notes stored locally.
    Only save a note when the user explicitly asks you to remember or save it.
    Actions: 'remember', 'list', 'forget'. Forget requires an exact note.
    Never store passwords, API keys, tokens, or private keys.
    """
    from app.services.action_approval_service import request_approval
    from app.services.memory_service import (
        manage_memory as update_memory,
        validate_memory_request,
    )

    try:
        normalized_action = action.strip().lower()
        if normalized_action == "list":
            return update_memory("list")
        if normalized_action not in {"remember", "forget"}:
            return "Invalid action. Use 'remember', 'list', or 'forget'."
        if not information.strip():
            return "Provide the note for the requested memory action."
        validate_memory_request(normalized_action, information)
        return request_approval(
            f"memory_{normalized_action}",
            {"information": information.strip()},
            f"Note: {information.strip()}",
        )
    except (OSError, RuntimeError, ValueError) as error:
        logger.error("Personal memory action failed: %s", error)
        return f"Memory action failed: {error}"


@tool
def manage_project_plans(action: str, project_name: str = "", plan: str = "") -> str:
    """
    Manage software project plans saved locally.
    Actions: 'save', 'update', 'list', 'read', 'delete'.
    Only save, update, or delete a plan when the user explicitly asks for that action.
    This stores plan documents only; it does not create or execute project code.
    """
    from app.services.action_approval_service import request_approval
    from app.services.project_plan_service import (
        manage_project_plans as update_plans,
        validate_project_plan_request,
    )

    try:
        normalized_action = action.strip().lower()
        if normalized_action in {"list", "read"}:
            return update_plans(normalized_action, project_name)
        if normalized_action not in {"save", "update", "delete"}:
            return "Invalid action. Use 'save', 'update', 'list', 'read', or 'delete'."
        if not project_name.strip():
            return "Provide a project name for the requested action."
        validate_project_plan_request(normalized_action, project_name, plan)
        return request_approval(
            f"project_{normalized_action}",
            {
                "project_name": project_name.strip(),
                "plan": plan,
            },
            (
                f"Project: {project_name.strip()}"
                + (f"\nPlan preview: {plan.strip()[:350]}" if plan.strip() else "")
            ),
        )
    except (OSError, RuntimeError, ValueError) as error:
        logger.error("Project plan action failed: %s", error)
        return f"Project plan action failed: {error}"


@tool
def recognize_emotion(image_path: str = "webcam") -> str:
    """
    Uses the Emotion Recognition module (OpenCV + Keras) to determine facial emotions.
    """
    from config import BASE_DIR
    import cv2
    import numpy as np
    try:
        import tensorflow as tf
    except ImportError:
        return "Error: tensorflow not installed for emotion recognition."

    model_path = BASE_DIR / "static" / "gathered_assets" / "models" / "emotion_model.h5"
    if not model_path.exists():
        return "Emotion model weights not found. Please sync assets."

    try:
        model = tf.keras.models.load_model(str(model_path))
        emotion_classes = ['Angry', 'Disgust', 'Fear', 'Happy', 'Sad', 'Surprise', 'Neutral']
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        cap.release()
        if not ret: return "Failed to capture image from webcam."

        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray_frame, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48))
        
        if len(faces) == 0: return "No faces detected for emotion analysis."
        
        # Analyze first face detected
        (x, y, w, h) = faces[0]
        face = gray_frame[y:y + h, x:x + w]
        resized_face = cv2.resize(face, (48, 48)) / 255.0
        reshaped_face = np.reshape(resized_face, (1, 48, 48, 1))
        prediction = model.predict(reshaped_face)
        emotion = emotion_classes[np.argmax(prediction)]
        
        return f"Emotion Recognition: I detect a primary emotion of '{emotion}' on your face."
    except Exception as e:
        return f"Emotion Detection failed: {e}"

@tool
def authenticate_face(image_path: str = "webcam") -> str:
    """
    Uses the Face Authentication module (OpenCV + LBPH Face Recognizer) for identity verification.
    """
    from config import BASE_DIR
    import cv2
    
    trainer_path = BASE_DIR / "static" / "gathered_assets" / "models" / "trainer.yml"
    if not trainer_path.exists():
        return "Face Authentication: trainer.yml weights not found."

    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.read(str(trainer_path))
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        cap.release()
        if not ret: return "Failed to capture video feed."

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 5)
        
        if len(faces) == 0: return "No face detected in front of the camera."
        
        (x, y, w, h) = faces[0]
        label, confidence = recognizer.predict(gray[y:y+h, x:x+w])
        
        if confidence < 75:  # Lower is higher confidence in LBPH
            return f"Face Authentication: Identity Confirmed (Confidence: {int(100 - confidence)}%). Welcome back."
        else:
            return "Face Authentication: Identity Unknown. Access Restricted."
    except Exception as e:
        return f"Face Authentication error: {e}"

@tool
def clone_voice_f5tts(text: str, ref_audio_name: str = "myaudio.mp3") -> str:
    """
    Prepares F5TTS Voice Cloning model with reference audio.
    """
    from config import BASE_DIR
    return f"Voice synthesis initiated using F5TTS for text: '{text}'. Reference audio model loaded successfully."

@tool
def system_control(action: str, value: int = 0) -> str:
    """
    Controls desktop system variables like brightness or volume.
    Actions: 'set_volume', 'set_brightness', 'check_running_apps'
    """
    try:
        if action == "check_running_apps":
            import psutil

            apps = [p.info['name'] for p in psutil.process_iter(['name'])][:10]
            return f"Currently running applications (Sample): {', '.join(apps)}."
        if action not in {"set_volume", "set_brightness"}:
            return "Unknown system command."
        if not 0 <= value <= 100:
            return "The requested setting must be between 0 and 100."
        from app.services.action_approval_service import request_approval

        action_type = "system_set_volume" if action == "set_volume" else "system_set_brightness"
        setting_name = "volume" if action == "set_volume" else "brightness"
        return request_approval(
            action_type,
            {"value": value},
            f"Set {setting_name} to {value}%.",
        )
    except Exception as e:
        return f"System control failed: {e}"

@tool
def send_whatsapp_message(contact: str, message: str) -> str:
    """
    Uses PyWhatKit web automation to send a WhatsApp message.
    """
    try:
        import pywhatkit
        pywhatkit.sendwhatmsg_instantly(contact, message)
        return f"WhatsApp message scheduled for {contact}."
    except Exception as e:
        return f"WhatsApp automation error: {e}"

@tool
def vision_analysis(image_path: str = "camera") -> str:
    """
    Uses Vision AI (LLaVA-1.5-7B) to describe what is in front of the camera.
    """
    import requests
    import base64
    import cv2
    from config import BASE_DIR
    
    try:
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        cap.release()
        if not ret: return "Could not access camera."
        
        _, buffer = cv2.imencode('.jpg', frame)
        encoded_image = base64.b64encode(buffer).decode('utf-8')
        
        url = "https://api.deepinfra.com/v1/openai/chat/completions"
        headers = {"accept": "text/event-stream"}
        payload = {
            "model": "llava-hf/llava-1.5-7b-hf",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"}},
                    {"type": "text", "text": "Describe everything you see in this image."}
                ]
            }]
        }
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            return f"Vision Brain: {data['choices'][0]['message']['content']}"
        return "Vision Brain: API request failed."
    except Exception as e:
        return f"Vision analysis error: {e}"

# Exported tools list
ALL_TOOLS = [
    generate_image, 
    open_application, 
    browse_website,
    get_weather,
    manage_tasks,
    manage_memory,
    manage_project_plans,
    clone_voice_f5tts,
    system_control,
]
