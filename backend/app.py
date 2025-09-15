import os
import json
import uuid
import re
import subprocess
from datetime import datetime
from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv(override=True)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['VIDEO_FOLDER'] = 'media/videos'
app.config['THUMBNAIL_FOLDER'] = 'thumbnails'

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['VIDEO_FOLDER'], exist_ok=True)
os.makedirs(app.config['THUMBNAIL_FOLDER'], exist_ok=True)

# Initialize AI clients
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
gemini_api_key = os.getenv("API_KEY")
openrouter_base_url = os.getenv("OPENROUTER_BASE_URL")
google_base_url = os.getenv("GOOGLE_BASE_URL")
deepseek_model_name = os.getenv("DEEPSEEK_MODEL_NAME")
llama_model_name = os.getenv("LLAMA_MODEL_NAME")
gemini_model_name = os.getenv("GEMINI_MODEL_NAME")

# Initialize AI clients
gemini_client = OpenAI(api_key=gemini_api_key, base_url=google_base_url)
openrouter_client = OpenAI(api_key=openrouter_api_key, base_url=openrouter_base_url)

# In-memory storage (replace with a database in production)
users = {
    'user123': {
        'user_id': 'user123', 
        'name': 'Alex Doe', 
        'email': 'alex.doe@example.com',
        'password': 'password123'  # In production, use proper password hashing
    }
}

videos = [
    {
        'video_id': 'vid001', 
        'user_id': 'user123', 
        'title': 'The History of Space Exploration', 
        'thumbnail_url': 'https://placehold.co/600x400/1a202c/ffffff?text=Space+History', 
        'video_file_url': 'media/videos/space_history.mp4',
        'caption_content': 'The history of space exploration spans centuries, beginning with early astronomical observations and culminating in crewed missions to the Moon and robotic exploration of the solar system.',
        'topic_tags': ['space', 'exploration', 'history'],
        'created_at': datetime.now().isoformat()
    },
    {
        'video_id': 'vid002', 
        'user_id': 'user123', 
        'title': 'Deep Dive into Neural Networks', 
        'thumbnail_url': 'https://placehold.co/600x400/1a202c/ffffff?text=AI+Deep+Dive', 
        'video_file_url': 'media/videos/neural_networks.mp4',
        'caption_content': 'Neural networks are computing systems inspired by the human brain. They consist of interconnected nodes that process information and can learn to perform tasks by considering examples.',
        'topic_tags': ['ai', 'neural networks', 'machine learning'],
        'created_at': datetime.now().isoformat()
    }
]

quizzes = {}

# Helper functions
def generate_video_id():
    return f"vid_{uuid.uuid4().hex[:8]}"

def generate_quiz_id():
    return f"quiz_{uuid.uuid4().hex[:8]}"

def generate_manim_animation(prompt):
    """Generate a Manim animation based on the prompt"""
    try:
        # Read the system prompt
        with open("fine_tuned_system_prompt.txt", "r") as f:
            system_prompt = f.read()
        
        # Generate code using Gemini
        response = gemini_client.chat.completions.create(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': prompt}
            ],
            model=gemini_model_name
        )
        
        code = response.choices[0].message.content
        
        # Extract Python code from markdown
        extracted_code = re.search(r"```python(.*?)```", code, re.DOTALL)
        if extracted_code:
            python_code = extracted_code.group(1).strip()
            
            # Save the extracted code to a file
            filename = f"manim_animation_{uuid.uuid4().hex[:8]}.py"
            with open(filename, "w") as f:
                f.write(python_code)
            
            # Run Manim to generate the video
            try:
                result = subprocess.run([
                    "manim", "-pql", filename, "MainScene"
                ], capture_output=True, text=True, timeout=120)
                
                if result.returncode == 0:
                    # Find the generated video file
                    video_files = [f for f in os.listdir(app.config['VIDEO_FOLDER']) 
                                 if f.startswith('MainScene') and f.endswith('.mp4')]
                    
                    if video_files:
                        # Get the most recent video file
                        video_files.sort(key=lambda x: os.path.getmtime(os.path.join(app.config['VIDEO_FOLDER'], x)), reverse=True)
                        video_filename = video_files[0]
                        return os.path.join(app.config['VIDEO_FOLDER'], video_filename)
                    else:
                        return None
                else:
                    print(f"Manim execution failed: {result.stderr}")
                    return None
                    
            except subprocess.TimeoutExpired:
                print("Manim execution timed out")
                return None
            except FileNotFoundError:
                print("Manim not found. Please ensure manim is installed and in PATH")
                return None
            except Exception as e:
                print(f"Error running Manim: {e}")
                return None
        else:
            print("No Python code found in the response")
            return None
            
    except Exception as e:
        print(f"Error generating animation: {e}")
        return None

def generate_quiz_with_gemini(caption_content, video_id):
    """Generate a quiz using Gemini API based on caption content"""
    try:
        system_prompt = """You are an expert quiz creator for educational content. Based on the provided transcript, 
        generate a JSON object representing a quiz. The quiz must have exactly 4 multiple-choice questions. 
        Each question object inside the 'questions' array must have the following properties: 
        'id' (a unique number), 'text' (the question string), 'options' (an array of 4 unique strings: 
        one correct answer and three plausible distractors), and 'answer' (the string of the correct answer, 
        which must also be present in the 'options' array). Do not output any text, markdown, or code outside of the single JSON object."""
        
        user_query = f"Here is the transcript:\n\n---\n{caption_content}\n---"
        
        response = gemini_client.chat.completions.create(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_query}
            ],
            model=gemini_model_name,
            response_format={"type": "json_object"}
        )
        
        quiz_data = json.loads(response.choices[0].message.content)
        quiz_data['quiz_id'] = generate_quiz_id()
        quiz_data['video_id'] = video_id
        
        return quiz_data
        
    except Exception as e:
        print(f"Error generating quiz with Gemini: {e}")
        # Return a fallback quiz structure on error
        return {
            'quiz_id': generate_quiz_id(),
            'video_id': video_id, 
            'questions': []
        }

def summarize_transcript_with_gemini(caption_content):
    """Summarize transcript using Gemini API"""
    try:
        system_prompt = "You are an expert at summarizing educational content. Provide 3-4 key bullet points summarizing the most important information from the following transcript. Use a '-' for each bullet point."
        user_query = f"Transcript:\n\n{caption_content}"
        
        response = gemini_client.chat.completions.create(
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_query}
            ],
            model=gemini_model_name
        )
        
        return response.choices[0].message.content or "Could not generate summary."
        
    except Exception as e:
        print(f"Error summarizing transcript: {e}")
        return "Sorry, there was an error generating the summary."

# API Routes
@app.route('/api/login', methods=['POST'])
def login():
    """Handle user login"""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    # Find user by email
    user = next((u for u in users.values() if u['email'] == email), None)
    
    if user and user['password'] == password:
        # In production, use JWT tokens for authentication
        return jsonify({
            'user_id': user['user_id'],
            'name': user['name'],
            'email': user['email']
        }), 200
    else:
        return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/videos/generate', methods=['POST'])
def generate_video():
    """Generate a video based on a prompt"""
    data = request.get_json()
    prompt = data.get('prompt')
    user_id = data.get('user_id')
    
    if not prompt or not user_id:
        return jsonify({'error': 'Prompt and user_id are required'}), 400
    
    # Generate video ID and basic info
    video_id = generate_video_id()
    title = prompt[:30] + '...' if len(prompt) > 30 else prompt
    
    # Generate caption content (in a real app, this would come from the video generation process)
    caption_content = f"This is a generated video about {prompt}. The video explains the key concepts and provides detailed information on the topic."
    
    # Generate video file (using Manim)
    video_file_path = generate_manim_animation(prompt)
    
    if not video_file_path:
        # Fallback to mock video if generation fails
        video_file_url = 'mock_video.mp4'
    else:
        video_file_url = video_file_path
    
    # Create video object
    new_video = {
        'video_id': video_id,
        'user_id': user_id,
        'title': title,
        'thumbnail_url': f'https://placehold.co/600x400/1a202c/ffffff?text={title.replace(" ", "+")}',
        'video_file_url': video_file_url,
        'caption_content': caption_content,
        'topic_tags': [tag for tag in prompt.lower().split() if len(tag) > 3],
        'created_at': datetime.now().isoformat()
    }
    
    # Add to videos list
    videos.append(new_video)
    
    # Generate quiz for the video
    quiz = generate_quiz_with_gemini(caption_content, video_id)
    quizzes[video_id] = quiz
    
    return jsonify({
        'video': new_video,
        'quiz': quiz
    }), 200

@app.route('/api/videos/user/<user_id>', methods=['GET'])
def get_user_videos(user_id):
    """Get all videos for a specific user"""
    user_videos = [v for v in videos if v['user_id'] == user_id]
    return jsonify(user_videos), 200

@app.route('/api/videos/search', methods=['GET'])
def search_videos():
    """Search videos by query"""
    query = request.args.get('q', '').lower()
    
    if not query:
        # Return some popular videos if no query
        popular_videos = [
            {
                'video_id': 'vid003', 
                'user_id': 'user456', 
                'title': 'Beginners Guide to Quantum Physics', 
                'thumbnail_url': 'https://placehold.co/600x400/3d4451/ffffff?text=Quantum+Physics', 
                'created_at': datetime.now().isoformat()
            },
            {
                'video_id': 'vid004', 
                'user_id': 'user789', 
                'title': 'Understanding Photosynthesis', 
                'thumbnail_url': 'https://placehold.co/600x400/3d4451/ffffff?text=Photosynthesis', 
                'created_at': datetime.now().isoformat()
            }
        ]
        return jsonify(popular_videos), 200
    
    # Filter videos by query
    filtered_videos = [
        v for v in videos 
        if query in v['title'].lower() or 
           any(query in tag for tag in v.get('topic_tags', [])) or
           query in v.get('caption_content', '').lower()
    ]
    
    return jsonify(filtered_videos), 200

@app.route('/api/videos/<video_id>', methods=['GET'])
def get_video_details(video_id):
    """Get details for a specific video"""
    video = next((v for v in videos if v['video_id'] == video_id), None)
    
    if not video:
        return jsonify({'error': 'Video not found'}), 404
    
    return jsonify({'video': video}), 200

@app.route('/api/videos/<video_id>/quiz', methods=['GET'])
def get_video_quiz(video_id):
    """Get quiz for a specific video"""
    if video_id in quizzes:
        return jsonify(quizzes[video_id]), 200
    else:
        # Generate a quiz if not already exists
        video = next((v for v in videos if v['video_id'] == video_id), None)
        if video:
            quiz = generate_quiz_with_gemini(video['caption_content'], video_id)
            quizzes[video_id] = quiz
            return jsonify(quiz), 200
        else:
            return jsonify({'error': 'Video not found'}), 404

@app.route('/api/videos/<video_id>/summary', methods=['GET'])
def get_video_summary(video_id):
    """Get summary for a video's transcript"""
    video = next((v for v in videos if v['video_id'] == video_id), None)
    
    if not video:
        return jsonify({'error': 'Video not found'}), 404
    
    summary = summarize_transcript_with_gemini(video['caption_content'])
    return jsonify({'summary': summary}), 200

@app.route('/api/quiz/<quiz_id>/submit', methods=['POST'])
def submit_quiz(quiz_id):
    """Submit quiz answers and get results"""
    data = request.get_json()
    answers = data.get('answers', {})
    
    # Find the quiz
    quiz = next((q for q in quizzes.values() if q['quiz_id'] == quiz_id), None)
    
    if not quiz:
        return jsonify({'error': 'Quiz not found'}), 404
    
    # Calculate score
    correct_count = 0
    for question in quiz['questions']:
        if answers.get(str(question['id'])) == question['answer']:
            correct_count += 1
    
    total_questions = len(quiz['questions'])
    percentage = (correct_count / total_questions) * 100 if total_questions > 0 else 0
    
    return jsonify({
        'correct': correct_count,
        'total': total_questions,
        'percentage': percentage,
        'passed': percentage >= 70
    }), 200

@app.route('/media/videos/<filename>')
def serve_video(filename):
    """Serve video files"""
    try:
        return send_file(os.path.join(app.config['VIDEO_FOLDER'], filename))
    except FileNotFoundError:
        abort(404)

if __name__ == '__main__':
    app.run(debug=True, port=5000)