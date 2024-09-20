from flask import Flask, render_template, request, jsonify
import subprocess
import json

app = Flask(__name__)

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
    include_sentiment = data['includeSentiment']
    include_word_cloud = data['includeWordCloud']

    try:
        result = subprocess.run(
            ['python', 'comment.py', api_key, channel_input, str(num_videos), str(max_comments), str(include_sentiment), str(include_word_cloud)],
            capture_output=True,
            text=True,
            check=True
        )
        return jsonify(json.loads(result.stdout))
    except subprocess.CalledProcessError as e:
        return jsonify({'error': f'An error occurred: {str(e)}\n{e.stderr}'}), 500

if __name__ == '__main__':
    app.run(debug=True)