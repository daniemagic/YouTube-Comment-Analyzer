from flask import Flask, render_template, request, jsonify
import subprocess
import json
import logging
import traceback

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.DEBUG)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.json
    api_key = data['apiKey']
    channel_input = data['channelInput']
    num_videos = data['numVideos']
    max_comments = data['maxComments']

    app.logger.info(f"Analyzing channel: {channel_input}, num_videos: {num_videos}, max_comments: {max_comments}")

    try:
        result = subprocess.run(
            ['python', 'comment.py', api_key, channel_input, str(num_videos), str(max_comments)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        app.logger.info("YouTube analyzer script executed")
        
        if result.returncode != 0:
            app.logger.error(f"Script error: {result.stderr}")
            return jsonify({'error': 'Error running analysis script', 'details': result.stderr}), 500

        try:
            parsed_result = json.loads(result.stdout)
            app.logger.info(f"Results parsed successfully: {parsed_result}")
            return jsonify(parsed_result)
        except json.JSONDecodeError as json_error:
            app.logger.error(f"Failed to parse JSON: {json_error}")
            app.logger.error(f"Raw output: {result.stdout}")
            return jsonify({'error': 'Failed to parse results', 'details': str(json_error)}), 500
    except Exception as e:
        app.logger.error(f"Unexpected error: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'error': 'An unexpected error occurred', 'details': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)